#!/usr/bin/env python3
"""Reproduce installation and CLI/tests in a fresh virtual environment."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--wheelhouse',type=Path)
    args=parser.parse_args()
    begin=datetime.now(timezone.utc);records=[]
    env={k:v for k,v in os.environ.items() if not k.startswith('MODEL_') and k not in ('VIRTUAL_ENV','PYTHONPATH','PYTHONHOME')}
    env['PIP_DISABLE_PIP_VERSION_CHECK']='1';env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
    with tempfile.TemporaryDirectory(prefix='content-agent-clean-') as temp:
        root=Path(temp);venv=root/'venv'
        def invoke(command,expected=0):
            start=time.monotonic();p=subprocess.run(list(map(str,command)),cwd=ROOT,env=env,text=True,capture_output=True)
            duration=time.monotonic()-start
            def redact(text):return text.replace(str(ROOT),'<PROJECT>').replace(str(root),'<CLEAN_ENV>')
            records.append({'command':[redact(str(c)) for c in command], 'elapsed_seconds':duration,
                            'exit_code':p.returncode,'stdout':redact(p.stdout),'stderr':redact(p.stderr)})
            if p.returncode!=expected:raise RuntimeError(f'command failed: {redact(p.stderr)}')
            return p
        invoke([sys.executable,'-m','venv',venv])
        python=venv/'bin/python';cli=venv/'bin/content-agent'
        install=[python,'-m','pip','install','--no-cache-dir']
        if args.wheelhouse:install+=['--no-index','--find-links',args.wheelhouse]
        invoke([*install,'-r','requirements-dev.txt'])
        invoke([python,'-m','pip','install','--no-cache-dir','--no-build-isolation','--no-deps','-e','.'])
        inp=ROOT/'.state/clean-input.json';inp.parent.mkdir(exist_ok=True)
        inp.write_text(json.dumps({'theme':'校园读书周','budget':'10.00','deadline':(begin+timedelta(days=1)).isoformat(),'preferred_variant':'standard'},ensure_ascii=False))
        db=Path('.state')/('clean-'+uuid4().hex+'.db')
        command=[cli,'run','--mode','mock','--input','.state/clean-input.json','--request-id','clean-normal','--state',db]
        first=json.loads(invoke(command).stdout)
        second=json.loads(invoke(command).stdout)
        assert first['status']=='completed' and first['costs']['spent_total']=='8.00'
        assert second=={**first,'reused':True}
        fault=[cli,'run','--mode','mock','--input','.state/clean-input.json','--request-id','clean-fail','--state',db,
               '--fault','generate-always','--data-dir','examples/fixtures/tool-failure']
        failed=json.loads(invoke(fault,3).stdout)
        assert failed['status']=='incomplete' and failed['costs']['spent_total']=='0.00'
        invoke([python,'-m','pytest','-q','--junitxml=examples/test-results/clean-pytest.xml'])
    result={'started_at':begin.isoformat(),'finished_at':datetime.now(timezone.utc).isoformat(),
            'python':platform.python_version(),'platform':platform.platform(),
            'dependency_source':'preexisting local wheel cache, exact pinned versions' if args.wheelhouse else 'pip index',
            'result':'passed','records':records}
    (ROOT/'examples/test-results/clean-reproduction.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('Clean environment: installation, normal, repeat, failure and tests passed.')

if __name__=='__main__':main()
