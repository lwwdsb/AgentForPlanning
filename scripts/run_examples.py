#!/usr/bin/env python3
"""Generate evidence by running the public CLI; never prewrite a result or trace."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
CASES={
 'normal':{}, 'missing-budget':{'remove':['budget']}, 'missing-deadline':{'remove':['deadline']},
 'missing-both':{'remove':['budget','deadline']}, 'insufficient-materials':{'theme':'火星矿场招募'},
 'budget-replan':{'preferred_variant':'premium','available':['premium','standard']},
 'no-feasible':{'preferred_variant':'premium','available':['premium']},
 'tool-failure':{'fault':'generate-once','available':['standard','lean']},
 'tool-failure-stop':{'fault':'generate-always','available':['standard','lean'],'input':'tool-failure'},
 'save-failure-stop':{'fault':'save-once','max-rounds':5,'input':'save-failure'},
 'save-failure':{'fault':'save-once'},
 'partial-result':{'fault':'partial-generate','available':['standard','lean']},
 'limit':{'max-rounds':1},
}

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def invoke(args):
    start=datetime.now(timezone.utc)
    p=subprocess.run([sys.executable,'-m','content_agent',*[str(Path(a).relative_to(ROOT)) if isinstance(a,Path) and a.is_relative_to(ROOT) else str(a) for a in args]],cwd=ROOT,capture_output=True,text=True)
    elapsed=(datetime.now(timezone.utc)-start).total_seconds()
    if p.returncode not in (0,2,3,4):raise RuntimeError(f'CLI exit {p.returncode}: {p.stderr}')
    return json.loads(p.stdout),{'command':['python','-m','content_agent',*[str(Path(a).relative_to(ROOT)) if isinstance(a,Path) and a.is_relative_to(ROOT) else str(a) for a in args]],
           'started_at':start.isoformat(),'elapsed_seconds':elapsed,'exit_code':p.returncode,'stderr':p.stderr}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cases',nargs='*',default=list(CASES))
    args=parser.parse_args()
    db=ROOT/'.state'/('evaluation-'+uuid4().hex+'.db')
    summaries=[]
    for name in args.cases:
        options=CASES[name]
        raw={'theme':options.get('theme','校园读书周'),'budget':'10.00',
             'deadline':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),
             'preferred_variant':options.get('preferred_variant','standard')}
        for key in options.get('remove',[]):raw.pop(key)
        inp=ROOT/'examples/inputs'/(options.get('input',name)+'.json');write(inp,raw)
        command=['run','--input',inp,'--mode','mock','--request-id',name,'--state',db]
        if 'available' in options:
            fixture=ROOT/'examples/fixtures'/('tool-failure' if name=='tool-failure-stop' else name)
            materials=json.loads((ROOT/'data/materials.json').read_text())
            rules=json.loads((ROOT/'data/rules.json').read_text())
            for variant,r in rules['variants'].items(): r['available']=variant in options['available']
            write(fixture/'materials.json',materials);write(fixture/'rules.json',rules)
            command+=['--data-dir',fixture]
        for flag in ('fault','max-rounds'):
            if flag in options:command+=['--'+flag,str(options[flag])]
        dest=ROOT/'examples/mock'/name
        result,record=invoke([*command,'--evidence-dir',dest]);write(dest/'execution.json',record)
        summaries.append({'case':name,'status':result['status'],'reason':result['reason_code'],
                          'spent':result['costs']['spent_total'],**record})
        if name=='normal':
            again=ROOT/'examples/mock/normal-reexport'
            _,r=invoke(['show','--request-id',name,'--state',db,'--evidence-dir',again]);write(again/'execution.json',r)
            for f in ('input.json','output.json','trace.jsonl','manifest.json','artifact.json'):
                assert (dest/f).read_bytes()==(again/f).read_bytes(),f
        if name in ('normal','no-feasible'):
            def counts():
                with sqlite3.connect(db) as con:
                    return {t:con.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('requests','events','ledger','artifacts')}
            before=counts()
            repeated=[]
            for index in range(2):
                repeat,execution=invoke(command)
                assert repeat['reused'] and repeat['run_id']==result['run_id']
                repeated.append({'output':repeat,'execution':execution})
            after=counts();assert before==after
            repeat_dir=ROOT/'examples/mock/repeat'/name
            write(repeat_dir/'input.json',raw)
            write(repeat_dir/'results.json',{'original_run_id':result['run_id'],'calls':repeated,
                                           'counts_before':before,'counts_after':after})
            if name=='normal':
                conflict_dir=ROOT/'examples/mock/repeat-conflict'
                changed={**raw,'budget':'11.00'};changed_path=conflict_dir/'input.json';write(changed_path,changed)
                conflict_command=list(command);conflict_command[2]=changed_path
                conflict,execution=invoke(conflict_command)
                assert conflict['status']=='input_conflict' and counts()==after
                write(conflict_dir/'output.json',conflict)
                write(conflict_dir/'execution.json',{**execution,'counts_before':before,'counts_after':counts(),
                      'trace_note':'没有新执行；trace_ref 指向 normal 的原始记录。'})
        print(name,result['status'],result['costs']['spent_total'],record['exit_code'])
    write(ROOT/'examples/test-results/scenario-runs.json',summaries)

if __name__=='__main__':main()
