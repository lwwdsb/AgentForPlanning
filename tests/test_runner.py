from content_agent.runner import run_request
from content_agent.providers import MockProvider
from conftest import SequenceProvider


def test_normal_run(raw, config, data, store, clock):
    result = run_request(raw, 'normal', config, data, store, MockProvider(), clock)
    assert result['status'] == 'completed'
    assert result['costs']['spent_total'] == '8.00'
    assert result['execution']['rounds_used'] == 6
    assert result['time']['simulated_elapsed_seconds'] == 720
    run, events, artifact = store.snapshot('normal')
    assert artifact['content']['script']['content']['text']
    assert len(run.ledger) == 1
    assert len(run.estimates) == 2
    assert run.estimates[1]['remaining_cost_minor'] == 0
    assert all(s['status'] == 'succeeded' for s in result['steps'])
    assert [a['action'] for a in run.attempts] == ['search_materials','estimate_cost','generate_script','estimate_cost','save_plan']
    assert all(d in {s['step_id'] for s in run.steps if s['status']=='succeeded'} for s in run.steps for d in s['depends_on'])
    assert events[-1]['event_type'] == 'terminal'


def test_cannot_finish_without_save(raw, config, data, store, clock):
    provider = SequenceProvider([('finish',{'outcome':'completed','reason_code':None,'remaining_work':[]})])
    result = run_request(raw, 'premature', {**config,'max_rounds':1}, data, store, provider, clock)
    assert result['status'] == 'incomplete'
    assert result['tool_results'][0]['status'] == 'rejected'
    assert result['costs']['spent_total'] == '0.00'


def test_no_materials_observed_before_stopping(raw,config,data,store,clock):
    raw['theme']='火星矿场招募'
    result=run_request(raw,'empty',config,data,store,MockProvider(),clock)
    assert result['status']=='incomplete' and result['reason_code']=='insufficient_materials'
    assert result['tool_results'][0]['status']=='empty'
    assert result['execution']['rounds_used']==2
    run=store.get('empty')
    assert not run.scripts and not run.saved and run.spent==0
    assert run.messages[1]['role']=='tool' and 'empty' in run.messages[1]['content']

from datetime import timedelta
from content_agent.domain import iso
import pytest


def test_budget_12_to_8(raw,config,data,store,clock):
    raw['preferred_variant']='premium';data['rules']['variants']['lean']['available']=False
    result=run_request(raw,'replan',config,data,store,MockProvider(),clock)
    run=store.get('replan')
    assert result['status']=='completed' and run.spent==800
    assert [q['projected_total_minor'] for q in run.estimates]==[1200,800,800]
    assert [q['feasible'] for q in run.estimates]==[False,True,True]
    assert len(run.candidates)==2
    assert '1200' in run.messages[3]['content']


def test_no_feasible_gap(raw,config,data,store,clock):
    raw['preferred_variant']='premium'
    for v in ('standard','lean'): data['rules']['variants'][v]['available']=False
    result=run_request(raw,'none',config,data,store,MockProvider(),clock)
    assert result['status']=='incomplete' and result['reason_code']=='budget_exceeded'
    assert result['costs']['budget_gap']=='2.00' and result['costs']['spent_total']=='0.00'
    assert result['saved_plan'] is None


@pytest.mark.parametrize('seconds,status',[(720,'completed'),(719,'incomplete'),(-1,'incomplete')])
def test_exact_deadline(raw,config,data,store,clock,seconds,status):
    raw['deadline']=iso(clock.now_utc()+timedelta(seconds=seconds))
    for v in ('premium','lean'):data['rules']['variants'][v]['available']=False
    result=run_request(raw,'deadline',config,data,store,MockProvider(),clock)
    assert result['status']==status
    if status=='completed':assert result['time']['deadline_met'] is True
    else:assert not result['saved_plan']


def test_time_causes_model_alternative(raw,config,data,store,clock):
    raw['budget']='100.00';raw['deadline']=iso(clock.now_utc()+timedelta(seconds=420))
    result=run_request(raw,'time',config,data,store,MockProvider(),clock)
    assert result['status']=='completed' and result['plan']['current_candidate']['variant']=='lean'
    assert store.get('time').estimates[0]['violations']==['deadline_exceeded']


def test_model_delay_counts_and_expiry_blocks_generation(raw,config,data,store,clock):
    raw['deadline']=iso(clock.now_utc()+timedelta(seconds=721))
    class Slow(MockProvider):
        def decide(self,context,messages):
            if context['rounds_used']==3:clock.advance(700)
            return super().decide(context,messages)
    result=run_request(raw,'slow',config,data,store,Slow(),clock)
    assert result['status']=='incomplete' and result['costs']['spent_total']=='0.00'
    assert result['time']['actual_elapsed_seconds']==700
    assert result['time']['simulated_elapsed_seconds']==60


@pytest.mark.parametrize('fault,expected,cost',[('generate-once','completed','3.00'),('generate-always','incomplete','0.00'),('partial-generate','completed','3.00')])
def test_generation_failures_preserve_success(raw,config,data,store,clock,fault,expected,cost):
    data['rules']['variants']['premium']['available']=False
    result=run_request(raw,'fault',{**config,'fault':fault},data,store,MockProvider(),clock)
    run=store.get('fault')
    assert result['status']==expected and result['costs']['spent_total']==cost
    assert run.materials
    attempts=[a for a in run.attempts if a['action']=='generate_script']
    assert attempts[0]['status']=='failed'
    assert attempts[0]['duration_seconds']==60
    assert run.steps[0]['status']=='succeeded'
    if fault=='partial-generate':
        assert attempts[0]['quality']=='partial' and attempts[0]['result']['text']
        assert len(run.scripts)==1
    assert all(l['attempt_id']!=attempts[0]['attempt_id'] for l in run.ledger)


@pytest.mark.parametrize('limit,expected',[(5,'incomplete'),(12,'completed')])
def test_save_failure_stop_or_explicit_retry(raw,config,data,store,clock,limit,expected):
    result=run_request(raw,'save',{**config,'fault':'save-once','max_rounds':limit},data,store,MockProvider(),clock)
    run,events,artifact=store.snapshot('save')
    assert result['status']==expected and run.spent==800 and len(run.scripts)==1
    attempts=[a for a in run.attempts if a['action']=='save_plan']
    assert attempts[0]['status']=='failed'
    if expected=='incomplete': assert artifact is None and len(attempts)==1
    else:
        assert artifact is not None and attempts[1]['status']=='succeeded'
        assert attempts[0]['attempt_id']!=attempts[1]['attempt_id']
    assert len(run.ledger)==1


@pytest.mark.parametrize('limit,status,saved',[(5,'incomplete',True),(6,'completed',True),(1,'incomplete',False)])
def test_limit_finish_order(raw,config,data,store,clock,limit,status,saved):
    result=run_request(raw,'cap',{**config,'max_rounds':limit},data,store,MockProvider(),clock)
    assert result['status']==status and bool(result['saved_plan'])==saved
    assert result['execution']['rounds_used']==limit
    if status=='incomplete':assert result['reason_code']=='limit_reached'


@pytest.mark.parametrize('limit,status',[(11,'incomplete'),(12,'completed')])
def test_twelfth_round_finish_no_hidden_request(raw,config,data,store,clock,limit,status):
    class Delay(MockProvider):
        def decide(self,context,messages):
            from content_agent.providers import action
            if context['rounds_used']<=6:return action('unknown',{'decision_summary':'无效动作测试'},context['rounds_used'])
            return super().decide(context,messages)
    # Ignore the six invalid observations only in the test provider, not in runtime.
    class Scheduled(Delay):
        def decide(self,context,messages):
            context={**context,'observations':[o for o in context['observations'] if o['action']!='unknown']}
            return super().decide(context,messages)
    result=run_request(raw,'last',{**config,'max_rounds':limit},data,store,Scheduled(),clock)
    assert result['status']==status and result['execution']['rounds_used']==limit
    assert result['saved_plan'] is not None


def test_provider_error_preserves_committed_materials(raw,config,data,store,clock):
    from content_agent.providers import ModelError
    p=SequenceProvider([('search_materials',{'query':'读书'}),ModelError('service unavailable')])
    result=run_request(raw,'service',config,data,store,p,clock)
    assert result['reason_code']=='model_error' and result['execution']['rounds_used']==2
    assert store.get('service').materials and result['steps'][0]['status']=='succeeded'


def test_invalid_params_and_unmet_dependencies_are_observations(raw,config,data,store,clock):
    p=SequenceProvider([('generate_script',{'candidate_id':'none','estimate_id':'none','material_ids':['unknown'],'script_draft':'draft'}),
                        ('search_materials',{'query':123}),('finish',{'outcome':'incomplete','reason_code':'tool_failed','remaining_work':['补足依赖']})])
    result=run_request(raw,'reject',config,data,store,p,clock)
    assert result['status']=='incomplete'
    assert [o['status'] for o in result['tool_results']]==['rejected','rejected','success']
    assert result['execution']['tool_calls']==0
    assert p.received[1][-1]['role']=='tool' and 'candidate_not_current' in p.received[1][-1]['content']


def test_saved_plan_has_dependencies_and_cost_detail(raw,config,data,store,clock):
    run_request(raw,'detail',config,data,store,MockProvider(),clock)
    _,_,artifact=store.snapshot('detail')
    content=artifact['content']
    assert content['execution_steps'][-1]['kind']=='save_plan'
    assert content['execution_steps'][-1]['status']=='succeeded'
    assert content['execution_steps'][-1]['depends_on']
    assert sum(line['amount_minor'] for line in content['cost_breakdown'])==800


def test_generation_reused_does_not_execute_or_charge_again(raw,config,data,store,clock):
    from content_agent.providers import action
    class Reuse(MockProvider):
        def decide(self,c,m):
            if c['rounds_used']==4:
                a={**__import__('json').loads(m[-2]['tool_calls'][0]['function']['arguments']),'script_draft':'另一个草稿不得覆盖'}
                return action('generate_script',a,c['rounds_used'])
            return super().decide(c,m)
    result=run_request(raw,'reuse-script',config,data,store,Reuse(),clock)
    run=store.get('reuse-script')
    assert result['status']=='completed'
    assert len([a for a in run.attempts if a['action']=='generate_script'])==1
    assert run.spent==800 and run.simulated_elapsed_seconds==720
    assert result['tool_results'][3]['reused'] is True
    assert '另一个草稿' not in run.scripts[run.current_candidate_id]['content']['text']


def test_old_success_not_advertised_as_reusable_for_new_candidate(raw,config,data,store,clock):
    from content_agent.providers import action
    class Switch(MockProvider):
        def decide(self,c,m):
            if c['rounds_used']==4:
                old=c['candidates'][0]
                return action('estimate_cost',{'variant':'lean','material_ids':old['material_ids'],
                    'goal':old['goal'],'audience':old['audience'],'assumptions':old['assumptions'],
                    'decision_summary':'比较另一业务形式，保留已有支出。'},c['rounds_used'])
            return super().decide(c,m)
    result=run_request(raw,'switch',config,data,store,Switch(),clock)
    run=store.get('switch')
    assert run.spent==800 and len(run.scripts)==1
    assert result['reusable_artifacts']['scripts']=={}
    old=[s for s in run.steps if s['kind']=='generate_script'][0]
    assert old['status']=='succeeded' and old['reusable'] is False
    assert result['artifact_history'][0]['reusable'] is False


def test_real_adapter_runs_same_loop_with_actual_tool_observations(raw,config,data,store,clock):
    import json
    from content_agent.providers import RealProvider,action
    requests=[]
    draft='真实适配器协议夹具中的模型草稿，不作为真实模型证据。'
    class Response:
        def __init__(self,body):self.body=body
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,limit):return self.body
    class HTTP:
        def open(self,req,timeout):
            body=json.loads(req.data);requests.append(body)
            context=json.loads(body['messages'][1]['content'])
            chosen=MockProvider().decide(context,body['messages'][2:])
            function=chosen['tool_calls'][0]['function']
            if function['name']=='generate_script':
                args=json.loads(function['arguments']);args['script_draft']=draft;function['arguments']=json.dumps(args)
            return Response(json.dumps({'choices':[{'finish_reason':'tool_calls','message':chosen}]}).encode())
    provider=RealProvider('https://example.test/chat','fixture-model','fixture-credential',HTTP())
    result=run_request(raw,'native',{**config,'mode':'real'},data,store,provider,clock)
    assert result['status']=='completed' and len(requests)==6
    run,events,artifact=store.snapshot('native')
    assert artifact['content']['script']['content']['text']==draft
    for i,body in enumerate(requests[1:],start=1):
        assistant,tool=body['messages'][-2:]
        assert tool['tool_call_id']==assistant['tool_calls'][0]['id']
        assert json.loads(tool['content'])['rounds_used']==i
    assert 'fixture-credential' not in json.dumps(events)


def test_time_after_save_can_prevent_completion_preserving_artifact(raw,config,data,store,clock):
    raw['deadline']=iso(clock.now_utc()+timedelta(seconds=725))
    class Late(MockProvider):
        def decide(self,c,m):
            if c['saved']:clock.advance(10)
            return super().decide(c,m)
    result=run_request(raw,'late',config,data,store,Late(),clock)
    assert result['status']=='incomplete' and result['saved_plan']
    assert result['time']['deadline_met'] is False
