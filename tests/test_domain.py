from content_agent.domain import money_minor, money, normalize_input


def test_decimal_money():
    assert money(money_minor('0.10') + money_minor('0.20')) == '0.30'
    value, issues = normalize_input({'theme':' 校园读书周 ','budget':'10','deadline':'2030-01-02T08:00:00+08:00'})
    assert not issues
    assert value['budget'] == '10.00' and value['deadline'] == '2030-01-02T00:00:00Z'

import pytest
from content_agent.domain import project,utc
from content_agent.tools import ToolExecutor,Rejected


def prepare(run_state,data):
    executor=ToolExecutor(data)
    executor.execute(run_state,'search_materials',{'query':'读书'})
    args={'variant':'standard','material_ids':list(run_state.materials),'goal':'推广阅读','audience':'校园读者','assumptions':['目标和受众待确认']}
    quote=executor.execute(run_state,'estimate_cost',args)
    return executor,args,quote


def test_history_spend_and_boundary(run_state,data):
    executor,args,q=prepare(run_state,data)
    assert q['projected_total_minor']==800
    run_state.ledger=[{'amount_minor':300}]
    p=project(run_state,run_state.candidate,data['rules'])
    assert p['projected_total_minor']==1100 and not p['feasible'] and p['budget_gap']=='1.00'
    run_state.request.input['budget']='11.00'
    assert project(run_state,run_state.candidate,data['rules'])['feasible']
    run_state.request.input['budget']='0.00'
    assert not project(run_state,run_state.candidate,data['rules'])['feasible']


def test_candidate_identity_script_immutability_and_stale_quote(run_state,data):
    executor,args,q=prepare(run_state,data)
    c=run_state.candidate
    gen={'candidate_id':c['candidate_id'],'estimate_id':q['estimate_id'],'material_ids':c['material_ids'],'script_draft':'原始脚本'}
    script=executor.execute(run_state,'generate_script',gen)['result']
    run_state.ledger=[{'amount_minor':800}]
    with pytest.raises(Rejected,match='stale_estimate'):
        executor.execute(run_state,'save_plan',{'candidate_id':c['candidate_id'],'estimate_id':q['estimate_id'],'script_id':script['artifact_id']})
    assert executor.validate(run_state,'generate_script',{**gen,'script_draft':'不同草稿'})['result']==script
    q2=executor.execute(run_state,'estimate_cost',args)
    assert len(run_state.candidates)==1 and c['revision']==1 and q2['projected_total_minor']==800
    q3=executor.execute(run_state,'estimate_cost',{**args,'audience':'教师群体'})
    assert len(run_state.candidates)==2 and run_state.candidate['revision']==2
    assert script['content']['text']=='原始脚本'
    assert q3['projected_total_minor']==1600 and q3['feasible'] is False
    assert run_state.spent==800


@pytest.mark.parametrize('key,code',[('success_cost_minor','unknown_cost'),('success_duration_seconds','unknown_duration')])
def test_unknown_rules_never_assumed_zero(run_state,data,key,code):
    data['rules']['variants']['standard'].pop(key)
    _,_,q=prepare(run_state,data)
    assert not q['feasible'] and code in q['violations']


def test_sequential_clock_does_not_hide_model_wait(run_state,clock):
    start=clock.monotonic()
    run_state.settle_time(60,0)
    clock.advance(300)
    run_state.tick(clock,start)
    assert (utc(run_state.logical_now)-utc(run_state.started_at)).total_seconds()==360
    run_state.settle_time(30,0)  # a failed tool still takes time
    clock.advance(10);run_state.tick(clock,start)
    assert (utc(run_state.logical_now)-utc(run_state.started_at)).total_seconds()==400


def test_actual_tool_time_not_double_counted(run_state,clock):
    start=clock.monotonic();clock.advance(480)
    run_state.settle_time(600,480);run_state.tick(clock,start)
    assert (utc(run_state.logical_now)-utc(run_state.started_at)).total_seconds()==600
    assert run_state.actual_elapsed_seconds==480 and run_state.simulation_extra_seconds==120


@pytest.mark.parametrize('value',['NaN','Infinity','-1','1.001','1.000','1e2','',10,None,'9'*40])
def test_money_rejects_invalid_and_inexact(value):
    with pytest.raises(ValueError):money_minor(value)


def test_changed_rules_reject_old_quote(run_state,data):
    executor,args,q=prepare(run_state,data)
    data['rules']['version']='new'
    changed=ToolExecutor(data)
    c=run_state.candidate
    with pytest.raises(Rejected,match='stale_estimate'):
        changed.validate(run_state,'generate_script',{'candidate_id':c['candidate_id'],'estimate_id':q['estimate_id'],
                         'material_ids':c['material_ids'],'script_draft':'draft'})
