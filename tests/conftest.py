from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import pytest

from content_agent.domain import Clock
from content_agent.providers import action
from content_agent.store import Store

ROOT = Path(__file__).resolve().parents[1]

class FakeClock(Clock):
    def __init__(self):
        self.start = datetime(2030, 1, 1, tzinfo=timezone.utc)
        self.elapsed = 0.0
    def now_utc(self): return self.start + timedelta(seconds=self.elapsed)
    def monotonic(self): return self.elapsed
    def advance(self, seconds): self.elapsed += seconds

class SequenceProvider:
    def __init__(self, actions): self.actions, self.calls, self.received = actions, 0, []
    def decide(self, context, messages):
        self.received.append(deepcopy(messages))
        index = self.calls
        self.calls += 1
        result = self.actions[index]
        if callable(result): result = result(context, messages)
        if isinstance(result, Exception): raise result
        name, args = result
        return action(name, {'decision_summary':'测试动作，观察实际返回。', **args}, self.calls)

@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs): raise AssertionError('default tests must not use network')
    monkeypatch.setattr(socket, 'create_connection', blocked)

@pytest.fixture
def clock(): return FakeClock()

@pytest.fixture
def raw(): return {'theme':'校园读书周','budget':'10.00','deadline':'2030-01-02T00:00:00Z','preferred_variant':'standard'}

@pytest.fixture
def data(): return {name:json.loads((ROOT/'data'/f'{name}.json').read_text()) for name in ('materials','rules')}

@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path/'state.db')
    yield s
    s.close()

@pytest.fixture
def config(): return {'mode':'mock', 'max_rounds':12, 'fault':'none','mock_strategy':'observation-v1'}

@pytest.fixture
def run_state(raw,config,data,clock):
    from content_agent.domain import Run,Request,digest,iso,normalize_input
    inp,issues=normalize_input(raw)
    req=Request('unit','fingerprint',raw,inp,config,'mock',digest(data['materials']),digest(data['rules']),digest(config))
    return Run(req,'unit-run',iso(clock.now_utc()))
