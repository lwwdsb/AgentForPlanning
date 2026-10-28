"""Bounded observation/decision/execution loop shared by real and mock models."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

from .domain import (Attempt, Clock, LedgerEntry, Request, Run, Step, digest, iso,
                     money, money_minor, normalize_input, project, uid, utc)
from .providers import ModelError, parse_action, validate_arguments
from .tools import Rejected, ToolExecutor, ToolFailure


def result_for(run, rules, state_path):
    inp = run.request.input
    budget = money_minor(inp['budget']) if isinstance(inp.get('budget'),str) else None
    projection = project(run,run.candidate,rules) if run.candidate and not run.input_issues else {}
    assessed=[project(run,c,rules).get('projected_total_minor') for c in run.candidates] if not run.input_issues else []
    known_totals=[value for value in assessed if value is not None]
    minimum_known=min(known_totals) if known_totals else None
    try: state_path=str(Path(state_path).relative_to(Path.cwd()))
    except ValueError: pass
    history = []
    for name in ('search_materials','estimate_cost','generate_script','save_plan'):
        steps = [s for s in run.steps if s['kind']==name and s['reusable']]
        status = steps[-1]['status'] if steps else ('pending' if run.status=='running' else 'skipped')
        history.append({'action':name,'status':status})
    return {'schema_version':'1.0.0','request_id':run.request.request_id,'run_id':run.run_id,
        'mode':run.request.mode,'status':run.status,'reused':False,'reason_code':run.reason_code,
        'input_issues':run.input_issues,
        'plan':{'current_candidate':run.candidate,'candidates':run.candidates,'task_plan':history,
                'assumptions_are_user_facts':False},
        'steps':run.steps,'attempts':run.attempts,'tool_results':run.observations,
        'reusable_artifacts':{'materials':list(run.materials.values()),
                              'scripts':{cid:s for cid,s in run.scripts.items() if cid==run.current_candidate_id}},
        'artifact_history':[{'candidate_id':cid,'artifact':s,'reusable':cid==run.current_candidate_id}
                            for cid,s in run.scripts.items()],
        'costs':{'budget':money(budget),'spent_total':money(run.spent),
                 'remaining_estimate':money(projection.get('remaining_cost_minor')),
                 'remaining_budget':None if budget is None else money(max(0,budget-run.spent)),
                 'projected_total':money(projection.get('projected_total_minor')),
                 'budget_gap':projection.get('budget_gap'),'gap_scope':'current_candidate',
                 'minimum_known_required':money(minimum_known),'minimum_scope':'assessed_candidates',
                 'unknown_reason':None if projection else 'no_valid_candidate_or_input'},
        'time':{'deadline_utc':inp.get('deadline') if isinstance(inp.get('deadline'),str) else None,
                'estimated_finish_utc':projection.get('estimated_finish_utc'),
                'simulated_elapsed_seconds':run.simulated_elapsed_seconds,
                'actual_elapsed_seconds':run.actual_elapsed_seconds,
                'simulation_extra_seconds':run.simulation_extra_seconds,
                'logical_now_utc':run.logical_now,
                'deadline_met':None if projection.get('estimated_finish_utc') is None else
                    utc(projection['estimated_finish_utc'])<=utc(inp['deadline'])},
        'execution':{'rounds_used':run.rounds_used,'max_rounds':run.max_rounds,
                     'tool_calls':len(run.attempts),'fault':run.request.execution_config.get('fault','none')},
        'saved_plan':None if run.saved is None else {'artifact_id':run.saved['artifact_id'],
                      'state_path':state_path,'location':'artifacts/'+run.saved['artifact_id']},
        'remaining_work':run.remaining_work,'trace_ref':{'run_id':run.run_id},'evidence_export_error':None}


def observation(run, name, outcome):
    budget = money_minor(run.request.input['budget'])
    return {'status':'success','quality':'complete','result':{},'error':None,'artifact_ids':[],
            'candidate_id':None,'estimate_id':None,'cost_delta':'0.00',
            'spent_total':money(run.spent),'remaining_budget':money(max(0,budget-run.spent)),
            'projected_total':money(outcome.get('projected_total_minor')),
            'estimated_finish_utc':None,'feasible':None,'violations':[],
            'steps':deepcopy(run.steps),'rounds_used':run.rounds_used,'max_rounds':run.max_rounds,
            'action':name, **outcome}


def context_for(run, data):
    return {'input':run.request.input,'rules':data['rules'],'materials':run.materials,
            'candidates':run.candidates,'current_candidate_id':run.current_candidate_id,
            'estimates':run.estimates,'scripts':run.scripts,'saved':run.saved,
            'steps':run.steps,'observations':run.observations,'spent_total':money(run.spent),
            'effective_now':run.effective_now,'rounds_used':run.rounds_used,'max_rounds':run.max_rounds}


def dependencies(run, name, revision):
    kinds = {'search_materials':[], 'estimate_cost':['search_materials'],
             'generate_script':['search_materials','estimate_cost'],
             'save_plan':['generate_script','estimate_cost']}[name]
    deps=[]
    for kind in kinds:
        candidates=[s for s in run.steps if s['kind']==kind and s['status']=='succeeded'
                    and (kind=='search_materials' or revision is None or s['candidate_revision']==revision)]
        if candidates: deps.append(candidates[-1]['step_id'])
    return deps


def run_request(raw, request_id, config, data, store, provider=None, clock=None, provider_factory=None):
    clock=clock or Clock()
    normalized, issues=normalize_input(raw)
    material_digest, rules_digest=digest(data['materials']),digest(data['rules'])
    fingerprint=digest({'input':normalized,'config':config,'materials':material_digest,'rules':rules_digest})
    request=Request(request_id,fingerprint,raw,normalized,config,config['mode'],material_digest,rules_digest,digest(config))
    run=Run(request,uid('run'),iso(clock.now_utc()),config.get('max_rounds',12),input_issues=issues)
    if issues:
        run.status='awaiting_input'
        run.reason_code='input_required' if any(i['code']=='missing' for i in issues) else 'invalid_input'
        run.remaining_work=['补齐或修正输入后使用新请求标识提交']
    run.result=result_for(run,data['rules'],store.path)
    # Check reuse before provider configuration; claim below is the atomic race boundary.
    existing=store.get(request_id)
    def reuse(old):
        result=deepcopy(old.result)
        if old.request.fingerprint != fingerprint:
            result.update(status='input_conflict',reason_code='request_conflict',reused=False)
        else:
            result['reused']=True
            if old.status=='running': result['reason_code']='in_progress'
        return result
    if existing: return reuse(existing)
    if not issues and provider is None and provider_factory is not None:
        provider=provider_factory()
    run, claimed=store.claim(run)
    if not claimed: return reuse(run)
    start=clock.monotonic()
    executor=ToolExecutor(data)
    def persist(events=(), ledger=None, artifact=None):
        run.tick(clock,start)
        run.result=result_for(run,data['rules'],store.path)
        store.commit(run,events,ledger,artifact)
    def terminal(reason):
        run.status='incomplete'; run.reason_code=reason
        if not run.remaining_work: run.remaining_work=['审阅已有成果及未完成原因；必要时提交新请求']
        persist([{'event_type':'terminal','payload':{'status':run.status,'reason_code':reason}}])
    persist([{'event_type':'started','payload':{'config':config,'input_issues':issues}}])
    if issues: return run.result
    if provider is None: raise ValueError('provider required')
    used_ids=set()
    try:
        while run.status=='running' and run.rounds_used<run.max_rounds:
            run.rounds_used+=1
            persist([{'event_type':'model_requested','payload':{'rounds_used':run.rounds_used}}])
            try:
                message=provider.decide(context_for(run,data),deepcopy(run.messages))
                clean,call_id,name,args=parse_action(message,used_ids)
                used_ids.add(call_id)
            except ModelError as exc:
                import re
                code=str(exc)
                allowed={'invalid_assistant','expected_one_tool_call','invalid_tool_call','invalid_tool_call_id',
                         'invalid_function','response_too_large','invalid_choices','refused_or_truncated',
                         'credential_in_response','model_transport_or_protocol_error'}
                safe_code=code if code in allowed or re.fullmatch(r'model_http_[0-9]{3}',code) else 'model_error'
                run.tick(clock,start)
                persist([{'event_type':'model_failed','payload':{'error_type':safe_code}}])
                terminal('model_error')
                break
            run.tick(clock,start)
            metadata=getattr(provider,'last_response_metadata',None)
            if metadata is not None:persist([{'event_type':'model_response','payload':metadata}])
            run.messages.append(clean)
            persist([{'event_type':'decision','payload':{'assistant':clean,'tool_call_id':call_id,
                'decision_summary':args.get('decision_summary') if isinstance(args,dict) else None,
                'observes_round':run.rounds_used-1 if run.rounds_used>1 else None}}])
            if not validate_arguments(name,args):
                outcome={'status':'rejected','quality':'none','error':'invalid_action_or_arguments'}
            elif name=='finish':
                if args['outcome']=='completed':
                    p=project(run,run.candidate,data['rules']) if run.candidate else {'feasible':False}
                    if not run.saved or not p['feasible']:
                        outcome={'status':'rejected','quality':'none','error':'completion_guard_failed',
                                 'violations':p.get('violations',[])}
                    else:
                        run.status='completed'; run.reason_code=None; run.remaining_work=[]
                        outcome={'status':'success','result':{'outcome':'completed'}}
                elif not args['reason_code'] or not args['reason_code'].strip():
                    outcome={'status':'rejected','quality':'none','error':'reason_required'}
                else:
                    allowed={'budget_exceeded','deadline_exceeded','insufficient_materials','tool_failed','stopped'}
                    run.status='incomplete'; run.reason_code=args['reason_code'] if args['reason_code'] in allowed else 'stopped'
                    run.remaining_work=args['remaining_work'] or ['解决未完成原因后提交新请求']
                    outcome={'status':'success','result':{'outcome':'incomplete','reason_code':run.reason_code}}
            elif utc(run.effective_now)>utc(run.request.input['deadline']):
                outcome={'status':'rejected','quality':'none','error':'deadline_exceeded','violations':['deadline_exceeded']}
            else:
                outcome=_execute(run,name,args,executor,store,clock,start,persist)
            obs=observation(run,name,outcome)
            run.observations.append(obs)
            run.messages.append({'role':'tool','tool_call_id':call_id,'content':__import__('json').dumps(obs,ensure_ascii=False)})
            events=[{'event_type':'observation','payload':{'tool_call_id':call_id,'observation':obs}}]
            if run.status!='running': events.append({'event_type':'terminal','payload':{'status':run.status,'reason_code':run.reason_code}})
            persist(events)
            if run.status=='running' and run.rounds_used>=run.max_rounds:
                terminal('limit_reached')
    except Exception:
        # Reload committed truth after any unexpected calculation/transaction failure.
        run=store.get(request_id)
        for a in run.attempts:
            if a['status']=='running': a.update(status='failed',quality='none',error='internal_error')
        for s in run.steps:
            if s['status']=='running': s['status']='failed'
        terminal('internal_error')
    return run.result


def _execute(run,name,args,executor,store,clock,start,persist):
    # Pure guards run before recording a business attempt.
    try:
        outcome=executor.validate(run,name,args)
    except Rejected as exc:
        return {'status':'rejected','quality':'none','error':str(exc),
                'violations':[v for v in ('budget_exceeded','deadline_exceeded') if v in str(exc)]}
    if outcome is not None and outcome.get('reused'):
        return outcome
    revision=run.candidate['revision'] if run.candidate and name!='search_materials' else None
    step=asdict(Step(uid('step'),name,revision,dependencies(run,name,revision),status='running'))
    attempt=asdict(Attempt(uid('attempt'),step['step_id'],run.rounds_used,name,args))
    run.steps.append(step); run.attempts.append(attempt)
    persist([{'event_type':'tool_started','payload':{'attempt_id':attempt['attempt_id'],'step_id':step['step_id'],
                                                'action':name,'arguments':args}}])
    tool_start=clock.monotonic()
    # Calculation is local and has no external side effect. Execute once on committed running state.
    before=deepcopy(run)
    ledger=None; artifact=None
    try:
        outcome=executor.execute(run,name,args)
        if name=='estimate_cost':
            step['candidate_revision']=run.candidate['revision']
            step['reusable']=True
        failure=_fault(run,name)
        if failure:
            partial=outcome['result']['content']['text'][:40] if failure=='partial_result' else None
            raise ToolFailure(failure, {'text':partial,'gap':'script_incomplete'} if partial else None)
    except ToolFailure as exc:
        # Restore successful prior state but retain this failed attempt as an independent record.
        run.candidates=before.candidates; run.estimates=before.estimates
        run.scripts=before.scripts; run.saved=before.saved; run.current_candidate_id=before.current_candidate_id
        outcome={'status':'partial' if exc.partial else 'failed','quality':'partial' if exc.partial else 'none',
                 'error':exc.code,'result':exc.partial or {}}
    actual=max(0,clock.monotonic()-tool_start)
    succeeded=outcome['status'] in ('success','empty')
    rule=executor.rule(name,run)
    duration=rule['success_duration_seconds' if succeeded else 'failure_duration_seconds']
    run.settle_time(duration,actual); run.tick(clock,start)
    attempt.update(status='succeeded' if succeeded else 'failed',quality=outcome.get('quality','complete' if succeeded else 'none'),
                   result=deepcopy(outcome.get('result',{})),error=outcome.get('error'),duration_seconds=duration,actual_duration_seconds=actual)
    step.update(status=attempt['status'],artifact_ids=outcome.get('artifact_ids',[]))
    cost=rule['success_cost_minor'] if succeeded else 0
    if cost:
        ledger=asdict(LedgerEntry(attempt['attempt_id'],run.request.request_id,cost,executor.rules['version'],outcome['artifact_ids'][0]))
        run.ledger.append(ledger)
    if name=='save_plan' and succeeded:
        run.saved['content']['execution_steps']=deepcopy(run.steps)
        run.saved['content']['cost_breakdown']=deepcopy(run.ledger)
        run.saved['content']['time_summary']={'simulated_elapsed_seconds':run.simulated_elapsed_seconds,
             'logical_now_utc':run.logical_now,'deadline_met':utc(run.effective_now)<=utc(run.request.input['deadline'])}
        artifact=run.saved
    outcome['cost_delta']=money(cost)
    # Tool outcome, step, clock, ledger and final artifact share a single transaction.
    persist([{'event_type':'tool_settled','payload':{'attempt_id':attempt['attempt_id'],
            'step_id':step['step_id'],'status':attempt['status'],'outcome':outcome}}],ledger,artifact)
    return outcome


def _fault(run,name):
    fault=run.request.execution_config.get('fault','none')
    count=sum(a['action']==name for a in run.attempts)
    if name=='generate_script':
        if fault=='generate-always' or (fault=='generate-once' and count==1):return 'injected_generation_failure'
        if fault=='partial-generate' and count==1:return 'partial_result'
    if name=='save_plan' and fault=='save-once' and count==1:return 'injected_save_failure'
    return None
