"""Reproducible CLI. stdout is machine readable; diagnostics go to stderr."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from .domain import dumps
from .providers import MockProvider, RealProvider, provider_profile, DECISION_POLICY_VERSION
from .runner import run_request
from .store import Store, export_evidence


class UsageError(Exception): pass
class Parser(argparse.ArgumentParser):
    def error(self,message): raise UsageError(message)


def read_json(path):
    def reject_constant(value): raise ValueError('non-finite JSON value')
    with open(path,encoding='utf-8') as f:
        return json.load(f,parse_constant=reject_constant)


def load_data(path):
    data={n:read_json(Path(path)/(n+'.json')) for n in ('materials','rules')}
    mats,rules=data['materials'],data['rules']
    if not mats.get('version') or not isinstance(mats.get('materials'),list) or not rules.get('version'):
        raise ValueError('materials/rules version and content required')
    ids=[]
    for m in mats['materials']:
        if not all(isinstance(m.get(k),str) for k in ('material_id','version','topic','text')) or not isinstance(m.get('tags'),list):
            raise ValueError('invalid material')
        if any(not isinstance(t,str) or not t for t in m['tags']): raise ValueError('invalid tags')
        ids.append(m['material_id'])
    if len(ids)!=len(set(ids)): raise ValueError('duplicate material id')
    if rules.get('failure_cost_minor') != 0: raise ValueError('failure cost must be explicitly zero')
    for name in ('search_materials','estimate_cost','save_plan'):
        rule=rules['tools'][name]
        if rule.get('success_cost_minor') != 0: raise ValueError('non-generation tools must be free')
        for k in ('success_duration_seconds','failure_duration_seconds'):
            if type(rule.get(k)) is not int or rule[k]<0: raise ValueError('invalid tool duration')
    for variant,rule in rules['variants'].items():
        if variant not in ('premium','standard','lean') or type(rule.get('available')) is not bool:
            raise ValueError('invalid variant')
        for key in ('success_cost_minor','success_duration_seconds'):
            if rule.get(key) is not None and (type(rule[key]) is not int or rule[key]<0): raise ValueError('invalid rule')
        if type(rule.get('failure_duration_seconds')) is not int or rule['failure_duration_seconds']<0:
            raise ValueError('invalid failure duration')
    return data


def parser():
    p=Parser(prog='content-agent')
    sub=p.add_subparsers(dest='command',required=True)
    run=sub.add_parser('run'); run.add_argument('--input',required=True)
    run.add_argument('--mode',choices=['mock','real'],required=True)
    run.add_argument('--request-id',default=None); run.add_argument('--data-dir',default='data')
    run.add_argument('--max-rounds',type=int,default=12)
    run.add_argument('--fault',choices=['none','generate-once','generate-always','save-once','partial-generate'],default='none')
    show=sub.add_parser('show'); show.add_argument('--request-id',required=True)
    show.add_argument('--view',choices=['result','trace','artifact'],default='result')
    recover=sub.add_parser('recover'); recover.add_argument('--request-id',required=True)
    for command in (run,show,recover): command.add_argument('--state',default='.state/content-agent.db')
    for command in (run,show): command.add_argument('--evidence-dir')
    return p


def config_for(args):
    config={'mode':args.mode,'max_rounds':args.max_rounds,'fault':args.fault}
    if args.mode=='mock': config['mock_strategy']='observation-v1'
    else:
        # Key is only read when a new, valid real request actually needs a provider.
        endpoint=os.environ.get('MODEL_ENDPOINT','')
        try:
            parts=urlsplit(endpoint)
            host=parts.hostname or ''
            if ':' in host:host='['+host+']'
            authority=host+(':'+str(parts.port) if parts.port else '')
            safe_endpoint=urlunsplit((parts.scheme,authority,parts.path,'',''))
        except ValueError:safe_endpoint='<invalid_endpoint>'
        config.update(model=os.environ.get('MODEL_NAME',''),endpoint=safe_endpoint,provider_profile=provider_profile(safe_endpoint),decision_policy_version=DECISION_POLICY_VERSION)
    return config


def main(argv=None):
    store=None
    try:
        args=parser().parse_args(argv)
        if args.command=='run':
            if not 1<=args.max_rounds<=100: raise UsageError('max-rounds must be 1..100')
            raw=read_json(args.input)
            if not isinstance(raw,dict): raise UsageError('input JSON must be an object')
            data=load_data(args.data_dir)
            config=config_for(args)
            def provider_factory():
                if args.mode=='mock': return MockProvider()
                return RealProvider(os.environ.get('MODEL_ENDPOINT',''),os.environ.get('MODEL_NAME',''),os.environ.get('MODEL_API_KEY',''))
            store=Store(args.state)
            result=run_request(raw,args.request_id or str(uuid4()),config,data,store,provider_factory=provider_factory)
            code={'completed':0,'awaiting_input':2,'incomplete':3,'running':3,'input_conflict':4}[result['status']]
            if result.get('reason_code')=='internal_error': code=70
            if args.evidence_dir and result['status']!='input_conflict':
                try: export_evidence(store.snapshot(result['request_id']),args.evidence_dir)
                except OSError:
                    result={**result,'evidence_export_error':'export_failed'}
                    diagnostic('evidence_export_error'); code=74
            print(dumps(result)); return code
        if not Path(args.state).is_file(): diagnostic('not_found'); return 66
        store=Store(args.state,readonly=args.command=='show')
        if args.command=='recover':
            print(dumps(store.recover(args.request_id))); return 0
        snapshot=store.snapshot(args.request_id)
        run,events,artifact=snapshot
        if args.view=='artifact' and artifact is None: diagnostic('not_found'); return 66
        code=0
        if args.evidence_dir:
            try: export_evidence(snapshot,args.evidence_dir)
            except OSError: diagnostic('evidence_export_error'); code=74
        if args.view=='trace':
            for event in events: print(dumps(event))
        else: print(dumps(artifact if args.view=='artifact' else run.result))
        return code
    except KeyError:
        diagnostic('not_found_or_invalid_data'); return 66
    except (UsageError,ValueError,TypeError,OSError) as exc:
        # Avoid reflecting URLs, raw inputs or vendor text into diagnostics.
        diagnostic('invalid_input_file_or_configuration',type(exc).__name__); return 64
    except Exception as exc:
        diagnostic('internal_error',type(exc).__name__); return 70
    finally:
        if store: store.close()


def diagnostic(code, detail=None):
    print(dumps({'error':code,'detail':detail}),file=sys.stderr)
