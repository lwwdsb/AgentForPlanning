#!/usr/bin/env python3
"""Reproduce review finding A with explicit offline actions and actual tool results."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from uuid import uuid4

from content_agent.cli import load_data
from content_agent.content import mock_draft
from content_agent.providers import action
from content_agent.runner import run_request
from content_agent.store import Store, export_evidence


class DependencyProbe:
    def __init__(self, material_ids): self.material_ids=material_ids

    def decide(self, context, messages):
        round=context['rounds_used']
        candidate=context['candidates'][-1] if context['candidates'] else None
        if round<=2:
            name='search_materials';args={'query':'校园读书周' if round==1 else '校园环保'}
        elif round in (3,5):
            name='estimate_cost';args=dict(variant='standard',material_ids=self.material_ids,
                goal='主题活动方案',audience='校园读者',assumptions=['目标和受众待运营确认'])
        elif round==4:
            name='generate_script';args=dict(candidate_id=candidate['candidate_id'],
                estimate_id=candidate['estimate_id'],material_ids=self.material_ids,
                script_draft=mock_draft(candidate,context['materials']))
        elif round==6:
            name='save_plan';args=dict(candidate_id=candidate['candidate_id'],estimate_id=candidate['estimate_id'],
                script_id=context['scripts'][candidate['candidate_id']]['artifact_id'])
        else:
            name='finish';args=dict(outcome='completed',reason_code=None,remaining_work=[])
        return action(name,{**args,'decision_summary':'离线固定动作反例，仅验证实际产物依赖，不证明模型决策。'},round)


def main():
    state=Path('.state')/('dependency-review-'+uuid4().hex+'.db')
    store=Store(state)
    try:
        for case,ids in [('reading-only',['reading-1','reading-2']),('mixed-sources',['reading-1','green-1'])]:
            raw=dict(theme='校园读书周',budget='10.00',preferred_variant='standard',
                deadline=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
            result=run_request(raw,'dependency-'+case,
                dict(mode='mock',max_rounds=12,fault='none',mock_strategy='dependency-review-v1'),
                load_data('data'),store,DependencyProbe(ids))
            steps=result['steps']
            expected={s['step_id'] for s in steps[:2] if set(s['artifact_ids']) & set(ids)}
            assert result['status']=='completed' and result['costs']['spent_total']=='8.00'
            assert set(steps[2]['depends_on'])==expected
            assert set(steps[3]['depends_on'])==expected|{steps[2]['step_id']}
            assert set(steps[4]['depends_on'])==expected|{steps[3]['step_id']}
            dest=Path('examples/review-fixes/dependencies')/case
            export_evidence(store.snapshot(result['request_id']),dest)
            record={'command':['python','scripts/run_dependency_examples.py'],'case':case,
                    'mode':'mock','verified':'actual referenced producers and post-generation estimate dependencies',
                    'status':result['status'],'spent':result['costs']['spent_total']}
            (dest/'execution.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps(record,ensure_ascii=False))
    finally:store.close()


if __name__=='__main__':main()
