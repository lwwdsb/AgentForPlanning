"""Domain records and exact, independently testable invariants."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import re
import socket
import time
from uuid import uuid4

SCHEMA_VERSION = '1.0.0'
VARIANTS = ('premium', 'standard', 'lean')
TERMINAL = {'completed', 'incomplete', 'awaiting_input'}


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()


def uid(prefix):
    return f'{prefix}_{uuid4().hex}'


def money_minor(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+(?:\.\d{1,2})?', value) or len(value) > 20:
        raise ValueError('金额须为非负且最多两位小数的十进制字符串')
    try:
        amount = Decimal(value)
        if not amount.is_finite() or amount < 0:
            raise ValueError('invalid amount')
        result = int(amount * 100)
        if result > 2**63 - 1:
            raise ValueError('amount exceeds storage range')
        return result
    except InvalidOperation as exc:
        raise ValueError('invalid amount') from exc


def money(value):
    return None if value is None else f'{value // 100}.{value % 100:02d}'


def utc(value):
    if not isinstance(value, str):
        raise ValueError('时间必须为含时区的 ISO 8601 字符串')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError('时间必须含 UTC 偏移量')
    return dt.astimezone(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


class Clock:
    def now_utc(self):
        return datetime.now(timezone.utc)

    def monotonic(self):
        return time.monotonic()


def normalize_input(raw):
    """Return all problems in one pass; invalid values have distinct fingerprint markers."""
    normalized, issues = {}, []
    allowed = {'theme', 'budget', 'deadline', 'preferred_variant'}
    for key in sorted(set(raw) - allowed):
        issues.append({'field': key, 'code': 'unknown_field'})
        normalized[key] = {'invalid': raw[key]}
    for key in ('theme', 'budget', 'deadline', 'preferred_variant'):
        value = raw.get(key, 'premium' if key == 'preferred_variant' else None)
        if value is None:
            issues.append({'field': key, 'code': 'missing' if key not in raw else 'invalid'})
            normalized[key] = {'missing': True} if key not in raw else {'invalid': None}
            continue
        try:
            if key == 'theme':
                if not isinstance(value, str) or not value.strip() or len(value) > 500:
                    raise ValueError('主题须为 1–500 字符')
                value = value.strip()
            elif key == 'budget':
                value = money(money_minor(value))
            elif key == 'deadline':
                value = iso(utc(value))
            elif value not in VARIANTS:
                raise ValueError('unknown variant')
            normalized[key] = value
        except (ValueError, TypeError):
            issues.append({'field': key, 'code': 'invalid'})
            normalized[key] = {'invalid': value}
    return normalized, issues


@dataclass
class Request:
    request_id: str
    fingerprint: str
    raw_input: dict
    input: dict
    execution_config: dict
    mode: str
    material_digest: str
    rules_digest: str
    config_digest: str


@dataclass
class Candidate:
    candidate_id: str
    variant: str
    goal: str
    audience: str
    assumptions: list
    material_ids: list
    revision: int
    estimate_id: str | None = None


@dataclass
class Step:
    step_id: str
    kind: str
    candidate_revision: int | None = None
    depends_on: list = field(default_factory=list)
    status: str = 'pending'
    artifact_ids: list = field(default_factory=list)
    reusable: bool = True


@dataclass
class Attempt:
    attempt_id: str
    step_id: str
    round: int
    action: str
    arguments: dict
    status: str = 'running'
    quality: str = 'none'
    result: dict = field(default_factory=dict)
    error: str | None = None
    duration_seconds: int = 0
    actual_duration_seconds: float = 0.0


@dataclass
class Estimate:
    estimate_id: str
    candidate_revision: int
    rules_digest: str
    required_artifacts: list
    spent_at_quote: int
    remaining_cost_minor: int | None
    projected_total_minor: int | None
    remaining_seconds: int | None
    feasible: bool
    violations: list
    context_digest: str
    candidate_id: str
    estimated_finish_utc: str | None
    budget_gap: str | None


@dataclass
class Artifact:
    artifact_id: str
    request_id: str
    kind: str
    content: dict
    source_ids: list
    candidate_revision: int
    validity: str = 'valid'


@dataclass
class LedgerEntry:
    attempt_id: str
    request_id: str
    amount_minor: int
    rule_version: str
    artifact_id: str


@dataclass
class Event:
    run_id: str
    sequence: int
    round: int
    event_type: str
    payload: dict
    timestamp: str
    mode: str
    request_id: str
    schema_version: str = SCHEMA_VERSION


@dataclass
class Run:
    request: Request
    run_id: str
    started_at: str
    max_rounds: int = 12
    status: str = 'running'
    reason_code: str | None = None
    owner_pid: int = field(default_factory=os.getpid)
    owner_host: str = field(default_factory=socket.gethostname)
    rounds_used: int = 0
    simulated_elapsed_seconds: int = 0
    actual_elapsed_seconds: float = 0.0
    simulation_extra_seconds: float = 0.0
    logical_now: str = ''
    effective_now: str = ''
    input_issues: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    estimates: list = field(default_factory=list)
    steps: list = field(default_factory=list)
    attempts: list = field(default_factory=list)
    materials: dict = field(default_factory=dict)
    scripts: dict = field(default_factory=dict)
    ledger: list = field(default_factory=list)
    observations: list = field(default_factory=list)
    messages: list = field(default_factory=list)
    saved: dict | None = None
    current_candidate_id: str | None = None
    remaining_work: list = field(default_factory=list)
    result: dict = field(default_factory=dict)

    def __post_init__(self):
        if type(self.max_rounds) is not int or not 1 <= self.max_rounds <= 100:
            raise ValueError('max_rounds must be an integer in 1..100')
        self.logical_now = self.logical_now or self.started_at
        self.effective_now = self.effective_now or self.started_at

    @classmethod
    def from_dict(cls, data):
        data = dict(data)
        data['request'] = Request(**data['request'])
        return cls(**data)

    @property
    def spent(self):
        return sum(e['amount_minor'] for e in self.ledger)

    @property
    def candidate(self):
        return next((c for c in self.candidates if c['candidate_id'] == self.current_candidate_id), None)

    def tick(self, clock, monotonic_started):
        self.actual_elapsed_seconds = max(self.actual_elapsed_seconds, clock.monotonic() - monotonic_started)
        logical = utc(self.started_at) + timedelta(seconds=self.actual_elapsed_seconds + self.simulation_extra_seconds)
        self.logical_now = iso(logical)
        self.effective_now = iso(max(clock.now_utc(), logical))

    def settle_time(self, rule_seconds, actual_seconds):
        if rule_seconds < 0 or actual_seconds < 0:
            raise ValueError('negative duration')
        self.simulated_elapsed_seconds += rule_seconds
        self.simulation_extra_seconds += max(0, rule_seconds - actual_seconds)


def quote_context(run, candidate, rules_digest):
    return digest({'candidate': {k: v for k, v in candidate.items() if k != 'estimate_id'},
                   'spent': run.spent, 'scripts': run.scripts, 'rules': rules_digest})


def project(run, candidate, rules):
    """Cost/time guards are independent of model decisions and previous quotes."""
    generated = candidate['candidate_id'] in run.scripts
    remaining = [] if run.saved else [rules['tools']['save_plan']]
    if not generated:
        remaining.append(rules['variants'][candidate['variant']])
    costs = [r.get('success_cost_minor') for r in remaining]
    seconds = [r.get('success_duration_seconds') for r in remaining]
    unknown_cost = any(type(x) is not int or x < 0 for x in costs)
    unknown_time = any(type(x) is not int or x < 0 for x in seconds)
    total = None if unknown_cost else run.spent + sum(costs)
    duration = None if unknown_time else sum(seconds)
    finish = None if duration is None else utc(run.effective_now) + timedelta(seconds=duration)
    budget = money_minor(run.request.input['budget'])
    violations = []
    if unknown_cost: violations.append('unknown_cost')
    elif total > budget: violations.append('budget_exceeded')
    if unknown_time: violations.append('unknown_duration')
    elif finish > utc(run.request.input['deadline']): violations.append('deadline_exceeded')
    return {'remaining_cost_minor': None if unknown_cost else sum(costs), 'projected_total_minor': total,
            'remaining_seconds': duration, 'estimated_finish_utc': None if finish is None else iso(finish),
            'budget_gap': None if total is None else money(max(0, total - budget)),
            'feasible': not violations, 'violations': violations}
