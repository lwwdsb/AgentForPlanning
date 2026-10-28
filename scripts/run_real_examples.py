#!/usr/bin/env python3
"""Explicit, bounded real-model evaluation. Reads a local env file without executing it."""
import argparse
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]


def configuration(path):
    allowed={'MODEL_ENDPOINT','MODEL_NAME','MODEL_API_KEY'}
    values={}
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        key,separator,value=line.partition('=')
        if not separator or key.strip() not in allowed:raise ValueError('unsupported local configuration entry')
        values[key.strip()]=value.strip()
    if set(values)!=allowed or not all(values.values()):raise ValueError('three model variables are required')
    return values


def check_path(case,result):
    observations=result['tool_results']
    if case=='budget-replan':
        quotes=[o for o in observations if o['action']=='estimate_cost' and o['status']=='success']
        pairs=[(q['result']['candidate']['variant'],q['result']['projected_total_minor'],q['feasible']) for q in quotes]
        hit=any(a==('premium',1200,False) and b==('standard',800,True)
                for i,a in enumerate(pairs) for b in pairs[i+1:])
        return hit and result['status']=='completed' and result['costs']['spent_total']=='8.00'
    failures=[a for a in result['attempts'] if a['action']=='generate_script' and a['status']=='failed']
    if not failures:return False
    first=failures[0]
    candidates=result['plan']['candidates'];initial=first['arguments']['candidate_id']
    later=any(c['candidate_id']!=initial for c in candidates)
    stopped=result['status']=='incomplete' and any(o['action']=='finish' and o['status']=='success'
                                                and o['rounds_used']>first['round'] for o in observations)
    return bool(result['reusable_artifacts']['materials']) and ((later and result['status']=='completed') or stopped)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--env-file',type=Path,required=True)
    parser.add_argument('--case',choices=['budget-replan','tool-failure'],required=True)
    args=parser.parse_args()
    values=configuration(args.env_file)
    case=args.case;stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:6]
    request_id='real-'+case+'-'+stamp
    input_path=Path('.state/real-inputs')/(request_id+'.json');input_path.parent.mkdir(parents=True,exist_ok=True)
    raw={'theme':'校园读书周','budget':'10.00','deadline':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),
         'preferred_variant':'premium' if case=='budget-replan' else 'standard'}
    input_path.write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n')
    dest=Path('examples/real/attempts')/request_id
    state=Path('.state/real-evaluation.db')
    command=[sys.executable,'-m','content_agent','run','--input',str(input_path),'--mode','real',
             '--request-id',request_id,'--state',str(state),'--data-dir','examples/fixtures/'+case,
             '--max-rounds','12','--evidence-dir',str(dest)]
    if case=='tool-failure':command+=['--fault','generate-once']
    started=datetime.now(timezone.utc);start=time.monotonic()
    print(json.dumps({'case':case,'started':started.isoformat(),'request_id':request_id}),flush=True)
    proc=subprocess.run(command,cwd=ROOT,env={**os.environ,**values},text=True,capture_output=True)
    elapsed=time.monotonic()-start
    if values['MODEL_API_KEY'] in proc.stdout+proc.stderr:raise RuntimeError('credential detected; output withheld')
    try:result=json.loads(proc.stdout)
    except ValueError:result={'status':'invalid_cli_output','tool_results':[],'attempts':[]}
    passed=check_path(case,result) if proc.returncode in (0,3) else False
    execution={'case':case,'request_id':request_id,'started_at':started.isoformat(),'elapsed_seconds':elapsed,
               'exit_code':proc.returncode,'acceptance_path_passed':passed,
               'command':['python',*command[1:]],'stderr':proc.stderr,'provider_profile':'deepseek-beta-nonthinking-v1'}
    dest.mkdir(parents=True,exist_ok=True)
    (dest/'execution.json').write_text(json.dumps(execution,ensure_ascii=False,indent=2)+'\n')
    if passed:
        canonical=Path('examples/real')/case
        if not canonical.exists():shutil.copytree(dest,canonical)
    print(json.dumps({'case':case,'status':result['status'],'reason':result.get('reason_code'),
                      'path_passed':passed,'rounds':result.get('execution',{}).get('rounds_used'),
                      'spent':result.get('costs',{}).get('spent_total'),'seconds':round(elapsed,2),
                      'evidence':str(dest)},ensure_ascii=False),flush=True)
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
