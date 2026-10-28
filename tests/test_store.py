from dataclasses import asdict
from copy import deepcopy
import json
import os
import socket
import pytest
from content_agent.domain import LedgerEntry
from content_agent.runner import run_request
from content_agent.providers import MockProvider


def test_save_transaction_rolls_back_preserving_script_and_ledger(raw,config,data,store,clock,monkeypatch):
    commit=store.commit
    def failing(run,events=(),ledger=None,artifact=None,**kwargs):
        def fail():raise RuntimeError('injected before commit')
        return commit(run,events,ledger,artifact,before_commit=fail if artifact else None)
    monkeypatch.setattr(store,'commit',failing)
    result=run_request(raw,'rollback',config,data,store,MockProvider(),clock)
    run,events,artifact=store.snapshot('rollback')
    assert result['status']=='incomplete' and result['reason_code']=='internal_error'
    assert artifact is None and run.saved is None
    assert len(run.scripts)==1 and run.spent==800
    assert store.db.execute('SELECT count(*) FROM ledger').fetchone()[0]==1
    assert store.db.execute('SELECT count(*) FROM artifacts').fetchone()[0]==0
    assert run.attempts[-1]['status']=='failed'


def test_dead_process_recover(run_state,store,monkeypatch):
    run_state.result={'status':'running','attempts':[],'steps':[]}
    store.claim(run_state)
    def dead(pid,signal): raise ProcessLookupError()
    monkeypatch.setattr(os,'kill',dead)
    result=store.recover('unit')
    assert result['status']=='incomplete' and result['reason_code']=='interrupted'
    assert store.get('unit').rounds_used==0


@pytest.mark.parametrize('kind',['alive','foreign','unknown'])
def test_refuse_uncertain_recovery(run_state,store,monkeypatch,kind):
    if kind=='foreign':run_state.owner_host='other-host'
    run_state.result={'status':'running'}
    store.claim(run_state)
    def check(pid,signal):
        if kind=='unknown':raise PermissionError()
    monkeypatch.setattr(os,'kill',check)
    before=asdict(store.get('unit'))
    with pytest.raises(ValueError):store.recover('unit')
    assert asdict(store.get('unit'))==before


def test_claim_atomic_and_running_reuse(run_state,store):
    from content_agent.store import Store
    first,created=store.claim(run_state)
    other=Store(store.path)
    try:
        second,claimed=other.claim(deepcopy(run_state))
        assert created and not claimed and second.run_id==first.run_id
        assert store.db.execute('SELECT count(*) FROM requests').fetchone()[0]==1
    finally:other.close()


def test_unique_ledger_and_artifact(raw,config,data,store,clock):
    import sqlite3
    run_request(raw,'unique',config,data,store,MockProvider(),clock)
    run,_,artifact=store.snapshot('unique')
    before=asdict(store.get('unique'))
    with pytest.raises(sqlite3.IntegrityError):store.commit(run,ledger=run.ledger[0])
    with pytest.raises(sqlite3.IntegrityError):store.commit(run,artifact={**artifact,'artifact_id':'different'})
    assert asdict(store.get('unique'))==before


@pytest.mark.parametrize('status',['completed','incomplete','awaiting_input'])
def test_terminal_reuse_never_calls_provider(raw,config,data,store,clock,status):
    if status=='incomplete':config['max_rounds']=1
    if status=='awaiting_input':raw.pop('budget')
    original=run_request(raw,'same',config,data,store,MockProvider(),clock)
    def forbidden():raise AssertionError('provider initialization on duplicate')
    result=run_request(raw,'same',config,data,store,clock=clock,provider_factory=forbidden)
    assert result=={**original,'reused':True}
    assert original['status']==status
