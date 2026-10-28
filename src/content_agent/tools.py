"""Local synthetic tools. These compute outcomes, never select the next action."""
from dataclasses import asdict

from .domain import Artifact, Candidate, Estimate, digest, money, project, quote_context, uid
from .content import check_delivery, render_delivery
from .providers import DRAFT_SCHEMA, validate_schema


class Rejected(Exception):
    pass


class ToolFailure(Exception):
    def __init__(self, code, partial=None):
        super().__init__(code)
        self.code, self.partial = code, partial


class ToolExecutor:
    def __init__(self, data):
        self.data = data
        self.rules = data['rules']
        self.rules_digest = digest(self.rules)

    def candidate(self, run, candidate_id):
        if candidate_id != run.current_candidate_id:
            raise Rejected('candidate_not_current')
        c = run.candidate
        if c is None: raise Rejected('candidate_missing')
        return c

    def check_quote(self, run, candidate, estimate_id):
        q = next((e for e in run.estimates if e['estimate_id'] == estimate_id), None)
        if (q is None or candidate['estimate_id'] != estimate_id or q['candidate_id'] != candidate['candidate_id']
                or q['context_digest'] != quote_context(run, candidate, self.rules_digest)):
            raise Rejected('stale_estimate')
        current = project(run, candidate, self.rules)
        if not q['feasible'] or not current['feasible']:
            raise Rejected(','.join(current['violations']) or 'estimate_infeasible')

    def check_draft(self, run, candidate, draft):
        if not validate_schema(draft,DRAFT_SCHEMA):raise Rejected('invalid_script_structure')
        error=check_delivery(draft,candidate,run.materials,self.rules['variants'][candidate['variant']])
        if error:raise Rejected(error)

    def validate(self, run, name, args):
        """Pure preflight: rejection/reuse must not execute a business tool."""
        if run.saved: raise Rejected('already_saved_only_finish_allowed')
        if name=='search_materials':
            if not args['query'].strip(): raise Rejected('empty_query')
        elif name=='estimate_cost':
            ids=args['material_ids']
            if not ids or len(set(ids))!=len(ids) or any(i not in run.materials for i in ids):
                raise Rejected('materials_not_retrieved')
            if not self.rules['variants'].get(args['variant'],{}).get('available',False):
                raise Rejected('variant_unavailable')
            if not args['goal'].strip() or not args['audience'].strip(): raise Rejected('empty_goal_or_audience')
        else:
            c=self.candidate(run,args['candidate_id'])
            script=run.scripts.get(c['candidate_id'])
            if name=='generate_script':
                if sorted(args['material_ids'])!=c['material_ids']: raise Rejected('material_mismatch')
                if script:
                    return {'status':'success','result':script,'artifact_ids':[script['artifact_id']],
                            'candidate_id':c['candidate_id'],'reused':True}
                self.check_draft(run,c,args['script_draft'])
            elif not script or script['artifact_id']!=args['script_id']: raise Rejected('script_missing')
            self.check_quote(run,c,args['estimate_id'])
        return None

    def execute(self, run, name, args):
        if run.saved: raise Rejected('already_saved_only_finish_allowed')
        return getattr(self, name)(run, args)

    def search_materials(self, run, args):
        query = args['query'].strip().casefold()
        if not query: raise Rejected('empty_query')
        ranked=[]
        for m in self.data['materials']['materials']:
            topic=m['topic'].casefold()
            score=3 if query in topic or topic in query else sum(t.casefold() in query for t in m['tags'])
            if score:ranked.append((score,m))
        best=max((score for score,m in ranked),default=0)
        matches=[{**m,'text':m['text'][:1000]} for score,m in ranked if score==best][:3]
        run.materials.update({m['material_id']:m for m in matches})
        return {'status':'success' if matches else 'empty', 'result':{'materials':matches,
                'gap':None if matches else 'no_matching_materials'}, 'artifact_ids':[m['material_id'] for m in matches]}

    def estimate_cost(self, run, args):
        ids = sorted(set(args['material_ids']))
        if not ids or len(ids) != len(args['material_ids']) or any(i not in run.materials for i in ids):
            raise Rejected('materials_not_retrieved')
        variant = args['variant']
        if not self.rules['variants'].get(variant, {}).get('available', False):
            raise Rejected('variant_unavailable')
        goal, audience = args['goal'].strip(), args['audience'].strip()
        if not goal or not audience: raise Rejected('empty_goal_or_audience')
        assumptions = sorted(set(a.strip() for a in args['assumptions'] if a.strip()))
        identity = {'variant':variant,'goal':goal,'audience':audience,'assumptions':assumptions,
                    'material_ids':ids,'rules_digest':self.rules_digest}
        cid = 'candidate_' + digest(identity)[:24]
        c = next((c for c in run.candidates if c['candidate_id']==cid), None)
        if c is None:
            c = asdict(Candidate(cid,variant,goal,audience,assumptions,ids,len(run.candidates)+1))
            run.candidates.append(c)
        run.current_candidate_id = cid
        for step in run.steps:
            if step['candidate_revision'] is not None:
                step['reusable'] = step['candidate_revision'] == c['revision']
        p = project(run,c,self.rules)
        q = asdict(Estimate(uid('estimate'),c['revision'],self.rules_digest,
                   [run.scripts[cid]['artifact_id']] if cid in run.scripts else ids,
                   run.spent,**p,context_digest=quote_context(run,c,self.rules_digest),candidate_id=cid))
        run.estimates.append(q)
        c['estimate_id'] = q['estimate_id']
        return {'status':'success','candidate_id':cid,'estimate_id':q['estimate_id'],
                'result':{**q,'candidate':c.copy(),'gap_scope':'current_candidate','assumptions_are_user_facts':False}, **p}

    def generate_script(self, run, args):
        c = self.candidate(run,args['candidate_id'])
        if sorted(args['material_ids']) != c['material_ids']:
            raise Rejected('material_mismatch')
        draft = args['script_draft']
        existing = run.scripts.get(c['candidate_id'])
        if existing:
            return {'status':'success','result':existing,'artifact_ids':[existing['artifact_id']],
                    'candidate_id':c['candidate_id'],'reused':True}
        self.check_quote(run,c,args['estimate_id'])
        self.check_draft(run,c,draft)
        script = asdict(Artifact(uid('script'),run.request.request_id,'script',
                        {**render_delivery(draft,self.rules['variants'][c['variant']]['delivery']),
                         'goal':c['goal'], 'audience':c['audience'],
                         'assumptions':c['assumptions'], 'assumptions_are_user_facts':False},
                        c['material_ids'], c['revision']))
        run.scripts[c['candidate_id']] = script
        return {'status':'success','result':script,'artifact_ids':[script['artifact_id']], 'candidate_id':c['candidate_id'],
                'next_requirements':{'before_save':'estimate_cost',
                    'candidate_arguments':{k:c[k] for k in ('variant','material_ids','goal','audience','assumptions')},
                    'reason':'脚本已生成，账本与产物改变；使用相同业务字段重估。运行状态写 decision_summary，不加入 assumptions。'}}

    def save_plan(self, run, args):
        c = self.candidate(run,args['candidate_id'])
        script = run.scripts.get(c['candidate_id'])
        if not script or script['artifact_id'] != args['script_id']: raise Rejected('script_missing')
        self.check_quote(run,c,args['estimate_id'])
        artifact = asdict(Artifact(uid('plan'),run.request.request_id,'plan',{
            'theme':run.request.input['theme'], 'candidate':c.copy(), 'script':script,
            'materials':[run.materials[i] for i in c['material_ids']],
            'budget':run.request.input['budget'], 'spent_total':money(run.spent),
            'deadline':run.request.input['deadline'], 'estimate':run.estimates[-1],
            'task_plan':[{'action':'素材检索','state':'succeeded'}, {'action':'脚本生成','state':'succeeded'},
                         {'action':'费用复核','state':'succeeded'}, {'action':'方案保存','state':'succeeded'}],
            'assumptions_are_user_facts':False}, [script['artifact_id'],*c['material_ids']], c['revision']))
        run.saved = artifact
        return {'status':'success','result':{'artifact_id':artifact['artifact_id'],
                'location':'artifacts/'+artifact['artifact_id']}, 'artifact_ids':[artifact['artifact_id']],
                'candidate_id':c['candidate_id']}

    def rule(self, name, run):
        return self.rules['variants'][run.candidate['variant']] if name=='generate_script' else self.rules['tools'][name]
