import json
import os
from pathlib import Path
import subprocess
import sys
from conftest import ROOT


def cli(*args, env=None):
    clean = {k:v for k,v in os.environ.items() if not k.startswith('MODEL_')}
    return subprocess.run([sys.executable, '-m','content_agent', *map(str,args)],cwd=ROOT,
                          text=True,capture_output=True,env={**clean,**(env or {})})


def test_normal_and_readonly_reexport(tmp_path, raw):
    inp=tmp_path/'input.json'; inp.write_text(json.dumps(raw))
    db=tmp_path/'db'; out=tmp_path/'out'
    run=cli('run','--mode','mock','--input',inp,'--state',db,'--evidence-dir',out)
    assert run.returncode == 0, run.stderr
    result=json.loads(run.stdout); request_id=result['request_id']
    assert result['status']=='completed' and result['saved_plan']
    assert len(result['tool_results']) == 6
    before=db.read_bytes()
    show=cli('show','--request-id',request_id,'--state',db,'--evidence-dir',tmp_path/'again')
    assert show.returncode==0,show.stderr
    assert db.read_bytes()==before
    for name in ('input.json','output.json','trace.jsonl','manifest.json','artifact.json'):
        assert (out/name).read_bytes() == (tmp_path/'again'/name).read_bytes()
    artifact=cli('show','--request-id',request_id,'--state',db,'--view','artifact')
    assert json.loads(artifact.stdout)['kind']=='plan'


import pytest
@pytest.mark.parametrize('changes,missing',[
    ({'budget':None},['budget']), ({'deadline':None},['deadline']),
    ({'budget':None,'deadline':None},['budget','deadline']), ({'theme':''},['theme']),
    ({'deadline':'2030-01-01T00:00:00'},['deadline']), ({'budget':10},['budget']),
    ({'budget':'NaN'},['budget']), ({'budget':'-1'},['budget']), ({'budget':'1.001'},['budget']),
    ({'unknown':True},['unknown'])])
def test_invalid_input_precedes_real_config(tmp_path,raw,changes,missing):
    raw.update(changes)
    raw={k:v for k,v in raw.items() if v is not None}
    inp=tmp_path/'input.json';inp.write_text(json.dumps(raw))
    r=cli('run','--input',inp,'--mode','real','--state',tmp_path/'db')
    assert r.returncode==2,r.stderr
    result=json.loads(r.stdout)
    assert result['status']=='awaiting_input'
    assert sorted(i['field'] for i in result['input_issues'])==sorted(missing)
    assert result['execution']['rounds_used']==result['execution']['tool_calls']==0
    assert result['costs']['spent_total']=='0.00'
    assert not result['saved_plan']


def test_invalid_json_and_missing_real_config(tmp_path,raw):
    inp=tmp_path/'input';inp.write_text('{')
    assert cli('run','--input',inp,'--mode','mock').returncode==64
    inp.write_text(json.dumps(raw))
    assert cli('run','--input',inp,'--mode','real','--state',tmp_path/'db').returncode==64


def counts(db):
    import sqlite3
    with sqlite3.connect(db) as con:
        return {table:con.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in ('requests','events','ledger','artifacts')}


@pytest.mark.parametrize('field,value',[('theme','环保'),('budget','11.00'),('deadline','2031-01-01T00:00:00Z'),('preferred_variant','lean')])
def test_repeat_and_business_conflict(tmp_path,raw,field,value):
    inp=tmp_path/'input.json';inp.write_text(json.dumps(raw));db=tmp_path/'db'
    args=['run','--input',inp,'--mode','mock','--request-id','same','--state',db]
    first=cli(*args);a=json.loads(first.stdout);before=counts(db)
    repeat=cli(*args);b=json.loads(repeat.stdout)
    assert repeat.returncode==0 and b=={**a,'reused':True} and counts(db)==before
    raw[field]=value;inp.write_text(json.dumps(raw))
    conflict=cli(*args)
    assert conflict.returncode==4 and json.loads(conflict.stdout)['status']=='input_conflict'
    assert counts(db)==before
    assert json.loads(cli('show','--state',db,'--request-id','same').stdout)==a
    new=cli(*args[:-2],'--state',db,'--request-id','different')
    assert json.loads(new.stdout)['run_id']!=a['run_id']


@pytest.mark.parametrize('change',['rule_content','rule_version','material_content','material_version','mode','fault','rounds'])
def test_configuration_changes_conflict(tmp_path,raw,change):
    import shutil
    fixture=tmp_path/'data';shutil.copytree(ROOT/'data',fixture)
    inp=tmp_path/'input.json';inp.write_text(json.dumps(raw));db=tmp_path/'db'
    args=['run','--input',inp,'--mode','mock','--request-id','same','--state',db,'--data-dir',fixture]
    assert cli(*args).returncode==0
    before=counts(db)
    if change.startswith(('rule','material')):
        path=fixture/('rules.json' if change.startswith('rule') else 'materials.json')
        val=json.loads(path.read_text())
        if change.endswith('version'):val['version']='2.0'
        elif change=='rule_content':val['variants']['lean']['success_cost_minor']=400
        else:val['materials'][0]['text']+=' 新合成资料'
        path.write_text(json.dumps(val))
    elif change=='mode':args[4]='real'
    elif change=='fault':args+=['--fault','generate-once']
    else:args+=['--max-rounds','8']
    changed=cli(*args)
    assert changed.returncode==4,changed.stderr
    assert counts(db)==before


@pytest.mark.parametrize('status',['incomplete','awaiting_input','running'])
def test_repeat_failure_or_progress_subprocess(tmp_path,raw,status):
    inp=tmp_path/'input.json';db=tmp_path/'db'
    if status=='awaiting_input':raw.pop('budget')
    inp.write_text(json.dumps(raw))
    args=['run','--input',inp,'--mode','mock','--request-id','same','--state',db,'--max-rounds','1']
    a=json.loads(cli(*args).stdout)
    if status=='running':
        from content_agent.store import Store
        s=Store(db);r=s.get('same');r.status='running';r.result.update(status='running',reason_code=None);s.commit(r);s.close()
    before=counts(db);b=json.loads(cli(*args).stdout)
    assert b['status']==status and b['reused'] is True and b['run_id']==a['run_id']
    assert counts(db)==before


def test_export_failure_retry_and_views(tmp_path,raw):
    inp=tmp_path/'input.json';inp.write_text(json.dumps(raw));db=tmp_path/'db'
    dest=tmp_path/'blocked';dest.write_text('file, not directory')
    r=cli('run','--input',inp,'--mode','mock','--request-id','export','--state',db,'--evidence-dir',dest)
    assert r.returncode==74
    result=json.loads(r.stdout)
    assert result['status']=='completed' and result['evidence_export_error']=='export_failed'
    before=db.read_bytes()
    for view in ('result','trace','artifact'):
        fail=cli('show','--request-id','export','--state',db,'--view',view,'--evidence-dir',dest)
        normal=cli('show','--request-id','export','--state',db,'--view',view)
        assert fail.returncode==74 and fail.stdout==normal.stdout
    retry=cli('show','--request-id','export','--state',db,'--evidence-dir',tmp_path/'ok')
    assert retry.returncode==0 and json.loads(retry.stdout)['evidence_export_error'] is None
    assert db.read_bytes()==before


@pytest.mark.parametrize('status',['incomplete','awaiting_input','running'])
def test_show_snapshot_has_own_exit_code(tmp_path,raw,status):
    from content_agent.store import Store
    inp=tmp_path/'input.json';db=tmp_path/'db'
    if status=='awaiting_input':raw.pop('budget')
    inp.write_text(json.dumps(raw))
    cli('run','--input',inp,'--mode','mock','--request-id','show','--state',db,'--max-rounds','1')
    if status=='running':
        s=Store(db);run=s.get('show');run.status='running';run.result.update(status='running');s.commit(run);s.close()
    before=db.read_bytes()
    out=tmp_path/'out';r=cli('show','--request-id','show','--state',db,'--evidence-dir',out)
    assert r.returncode==0 and json.loads(r.stdout)['status']==status
    manifest=json.loads((out/'manifest.json').read_text())
    assert manifest['final_snapshot']==(status!='running')
    assert cli('show','--request-id','show','--state',db,'--view','artifact').returncode==66
    assert db.read_bytes()==before


def test_mock_and_show_do_not_read_model_secrets(tmp_path,raw,monkeypatch,capsys):
    from content_agent.cli import main
    from unittest.mock import patch
    inp=tmp_path/'input.json';inp.write_text(json.dumps(raw));db=tmp_path/'db'
    original=os.environ.get
    def guard(key,*args):
        if key.startswith('MODEL_'):raise AssertionError('unexpected model configuration access')
        return original(key,*args)
    with patch.object(os.environ,'get',guard):
        assert main(['run','--input',str(inp),'--mode','mock','--request-id','safe','--state',str(db)])==0
        assert main(['show','--request-id','safe','--state',str(db),'--evidence-dir',str(tmp_path/'out')])==0
    assert 'MODEL_API_KEY' not in capsys.readouterr().out


def test_input_problems_precede_malformed_endpoint(tmp_path,raw):
    raw.pop('budget');inp=tmp_path/'input';inp.write_text(json.dumps(raw))
    r=cli('run','--input',inp,'--mode','real','--state',tmp_path/'db',env={'MODEL_ENDPOINT':'https://[bad'})
    assert r.returncode==2,r.stderr


def test_show_does_not_use_clock(tmp_path,raw,monkeypatch,capsys):
    from content_agent.cli import main
    from content_agent.domain import Clock
    inp=tmp_path/'input';inp.write_text(json.dumps(raw));db=tmp_path/'db'
    assert main(['run','--input',str(inp),'--mode','mock','--request-id','history','--state',str(db)])==0
    def forbidden(*args):raise AssertionError('show must not reinterpret historical deadline')
    monkeypatch.setattr(Clock,'now_utc',forbidden)
    assert main(['show','--request-id','history','--state',str(db),'--evidence-dir',str(tmp_path/'bundle')])==0
