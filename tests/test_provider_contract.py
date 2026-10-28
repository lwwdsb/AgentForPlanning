import json
from content_agent.providers import TOOLS, RealProvider


def test_strict_tool_schemas():
    assert len(TOOLS) == 5
    for tool in TOOLS:
        function=tool['function']; schema=function['parameters']
        assert function['strict'] is True
        assert schema['additionalProperties'] is False
        assert set(schema['properties']) == set(schema['required'])
        assert 'decision_summary' in schema['properties']


def test_http_protocol_and_observation_link():
    calls=[]
    class Response:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self, limit):
            return json.dumps({'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
                 'tool_calls':[{'id':'c1','type':'function','function':{'name':'search_materials','arguments':'{}'}}]}}]}).encode()
    class Transport:
        def open(self,req,timeout): calls.append((req,timeout)); return Response()
    provider=RealProvider('https://example.test/v1/chat/completions','test-model','test-secret',opener=Transport())
    messages=[{'role':'assistant','content':None,'tool_calls':[{'id':'previous','type':'function','function':{'name':'estimate_cost','arguments':'{}'}}]},
              {'role':'tool','tool_call_id':'previous','content':'{"feasible":false,"projected_total":"12.00"}'}]
    response=provider.decide({'budget':'10.00'}, messages)
    req,timeout=calls[0]; body=json.loads(req.data)
    assert body['messages'][-2:] == messages
    assert body['tool_choice']=='required' and body['parallel_tool_calls'] is False and body['stream'] is False
    assert timeout==30 and len(calls)==1
    assert response['tool_calls'][0]['id']=='c1'
    assert 'test-secret' not in req.data.decode()

import pytest
from urllib.error import HTTPError, URLError
from content_agent.providers import action, parse_action, ModelError


def message():return action('search_materials',{'query':'读书','decision_summary':'检索主题素材'})


@pytest.mark.parametrize('kind',['empty','multiple','missing_id','duplicate_id','refusal','nonobject','badfunction'])
def test_malformed_protocol_rejected_without_execution(kind):
    m=message();used=set()
    if kind=='empty':m['tool_calls']=[]
    elif kind=='multiple':m['tool_calls']*=2
    elif kind=='missing_id':m['tool_calls'][0].pop('id')
    elif kind=='duplicate_id':used={'call_1'}
    elif kind=='refusal':m['refusal']='refused'
    elif kind=='nonobject':m=[]
    else:m['tool_calls'][0]['function']=[]
    with pytest.raises(ModelError):parse_action(m,used)


@pytest.mark.parametrize('body',[
    b'bad-json', b'[]', b'{"choices":[]}', b'{"choices":[{}]}',
    b'{"choices":[{"finish_reason":"length","message":{}}]}', b'x'*(1024*1024+1)])
def test_http_invalid_response(body):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,limit):return body
    class Transport:
        def open(self,*args,**kwargs):return Response()
    p=RealProvider('https://example.test/chat','model','test-credential',Transport())
    with pytest.raises(ModelError):p.decide({},[])


@pytest.mark.parametrize('error',[TimeoutError('test-secret'),URLError('test-secret'),HTTPError('https://example.test',500,'test-secret',{},None),HTTPError('https://example.test',302,'redirect',{},None)])
def test_http_error_is_redacted_and_never_retried(error):
    class Transport:
        calls=0
        def open(self,*args,**kwargs):self.calls+=1;raise error
    t=Transport();p=RealProvider('https://example.test/chat','model','test-secret',t)
    with pytest.raises(ModelError) as caught:p.decide({},[])
    assert 'test-secret' not in str(caught.value) and t.calls==1


def test_redirect_handler_rejects_following_auth():
    from urllib.request import HTTPRedirectHandler
    p=RealProvider('https://example.test/chat','model','test-secret')
    handler=next(h for h in p.opener.handlers if isinstance(h,HTTPRedirectHandler))
    assert handler.redirect_request(None,None,302,'redirect',{},'https://other.test') is None


@pytest.mark.parametrize('endpoint',['http://example.test/chat','https://user:password@example.test/chat','https://example.test/chat?api_key=secret','https://example.test/chat#secret'])
def test_auth_in_endpoint_forbidden(endpoint):
    with pytest.raises(ValueError):RealProvider(endpoint,'model','secret')


def test_invalid_single_arguments_remain_associated():
    m=message();m['tool_calls'][0]['function']['arguments']='bad-json'
    clean,cid,name,args=parse_action(m,set())
    assert cid=='call_1' and args is None and name=='search_materials'


def test_deepseek_wire_schema_preserves_local_guards():
    from content_agent.providers import wire_tools,validate_arguments,provider_profile
    wire=wire_tools('deepseek-beta-nonthinking-v1')
    assert wire!=TOOLS
    def walk(node):
        if isinstance(node,dict):
            assert not {'minLength','maxLength','minItems','maxItems'} & node.keys()
            if node.get('type')=='object':
                assert node['additionalProperties'] is False
                assert set(node['required'])==set(node['properties'])
            for v in node.values():walk(v)
        elif isinstance(node,list):
            for v in node:walk(v)
    walk(wire)
    assert all(t['function']['strict'] for t in wire)
    args={'candidate_id':'c','estimate_id':'e','material_ids':['m'],'script_draft':{'format':'image_text','title':'标题','source_facts':[{'material_id':'m','quote':'原文'}],'copy':'x'*601,'scenes':[],'operational_suggestions':[]},'decision_summary':'生成'}
    assert not validate_arguments('generate_script',args)
    assert provider_profile('https://api.deepseek.com/beta/chat/completions')=='deepseek-beta-nonthinking-v1'
    assert provider_profile('https://api.deepseek.com.evil.test/chat')=='chat-completions-v1'


def test_deepseek_nonthinking_payload_and_redacted_http_status():
    calls=[]
    class Transport:
        def open(self,request,timeout):
            calls.append(json.loads(request.data))
            raise HTTPError(request.full_url,400,'private vendor body',{},None)
    provider=RealProvider('https://api.deepseek.com/beta/chat/completions','deepseek-flash','fixture-key',Transport())
    with pytest.raises(ModelError,match='model_http_400'):
        provider.decide({},[])
    assert calls[0]['thinking']=={'type':'disabled'}
    assert calls[0]['tool_choice']=='required' and calls[0]['parallel_tool_calls'] is False
    assert '"maxLength":' not in json.dumps(calls[0]['tools'])
