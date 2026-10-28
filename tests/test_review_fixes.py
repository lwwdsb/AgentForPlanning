import pytest

from conftest import SequenceProvider
from content_agent.providers import MockProvider
from content_agent.runner import run_request
from content_agent.tools import ToolExecutor, Rejected


@pytest.mark.parametrize('material_ids', [['reading-1', 'reading-2'], ['reading-1', 'green-1']])
def test_dependencies_follow_all_actual_material_producers(raw, config, data, store, clock, material_ids):
    estimate = dict(variant='standard', material_ids=material_ids, goal='主题活动',
                    audience='校园读者', assumptions=['受众待确认'])
    def generate(c, messages):
        chosen = MockProvider().decide(c, messages)['tool_calls'][0]['function']
        import json
        return chosen['name'], json.loads(chosen['arguments'])
    def save(c, messages):
        candidate = c['candidates'][-1]
        return 'save_plan', dict(candidate_id=candidate['candidate_id'], estimate_id=candidate['estimate_id'],
                                script_id=c['scripts'][candidate['candidate_id']]['artifact_id'])
    provider = SequenceProvider([
        ('search_materials', {'query': '校园读书周'}),
        ('search_materials', {'query': '校园环保'}),
        ('estimate_cost', estimate), generate, ('estimate_cost', estimate), save,
        ('finish', dict(outcome='completed', reason_code=None, remaining_work=[]))])
    result = run_request(raw, 'sources', config, data, store, provider, clock)
    assert result['status'] == 'completed'
    steps = result['steps']
    sources = {s['step_id'] for s in steps[:2] if set(s['artifact_ids']) & set(material_ids)}
    assert set(steps[2]['depends_on']) == sources
    assert set(steps[3]['depends_on']) == sources | {steps[2]['step_id']}
    assert set(steps[4]['depends_on']) == sources | {steps[3]['step_id']}
    assert set(steps[5]['depends_on']) == {steps[3]['step_id'], steps[4]['step_id']}
    _, _, artifact = store.snapshot('sources')
    assert artifact['content']['execution_steps'] == steps


def draft(format='image_text'):
    return dict(format=format, title='校园读书周',
                source_facts=[dict(material_id='reading-1', quote='活动地点与具体日期待运营确认。')],
                copy='分享一本推荐书和推荐理由。', scenes=[],
                operational_suggestions=['建议在评论区分享，参与渠道待运营确认'])


def prepared(run_state, data, variant='standard'):
    executor = ToolExecutor(data)
    executor.execute(run_state, 'search_materials', {'query': '校园读书周'})
    quote = executor.execute(run_state, 'estimate_cost', dict(variant=variant,
        material_ids=['reading-1', 'reading-2'], goal='推广阅读', audience='校园读者', assumptions=['受众待确认']))
    return executor, dict(candidate_id=run_state.candidate['candidate_id'], estimate_id=quote['estimate_id'],
                         material_ids=run_state.candidate['material_ids'])


@pytest.mark.parametrize('bad,code', [
    ({'format': 'video_script'}, 'delivery_format_mismatch'),
    ({'scenes': [{'visual': '镜头', 'narration': '旁白'}]}, 'delivery_scope_exceeded'),
    ({'copy': '正文' * 81}, 'delivery_scope_exceeded'),
    ({'copy': '第一段\n第二段'}, 'delivery_scope_exceeded'),
    ({'copy': '图文稿：校园读书周，分享推荐书。短视频稿：0—3秒展示书架；3—10秒展示推荐语。精简文案：一本书，一句理由。'}, 'delivery_scope_exceeded'),
    ({'copy': '0—3秒展示书架；3—10秒展示推荐语。'}, 'delivery_scope_exceeded'),
    ({'copy': '画面1：展示书架。旁白：分享推荐书。'}, 'delivery_scope_exceeded'),
    ({'source_facts': [{'material_id': 'reading-1', 'quote': '不设排名，不评奖项。'}]}, 'unsupported_source_fact'),
    ({'source_facts': [{'material_id': 'green-1', 'quote': '活动规则需运营审核。'}]}, 'unsupported_source_fact'),
])
def test_lean_rejects_extra_deliverables_and_unsupported_facts(run_state, data, bad, code):
    executor, args = prepared(run_state, data, 'lean')
    args['script_draft'] = {**draft('short_copy'), **bad}
    with pytest.raises(Rejected, match=code):
        executor.validate(run_state, 'generate_script', args)
    assert not run_state.scripts and run_state.spent == 0


def test_structured_script_separates_sources_and_unconfirmed_proposals(run_state, data):
    executor, args = prepared(run_state, data, 'lean')
    args['script_draft'] = draft('short_copy')
    content = executor.execute(run_state, 'generate_script', args)['result']['content']
    assert content['delivery']['format'] == 'short_copy'
    assert content['delivery']['scenes'] == []
    assert content['publication_status'] == 'requires_operator_review'
    assert '素材事实（逐字引用）' in content['text']
    assert '创意草稿（待运营审核）' in content['text']
    assert '运营建议（待确认，不属于已确认活动规则）' in content['text']
    assert content['pricing_scope']['included_deliverables'] == ['short_copy']


def test_video_cannot_smuggle_an_additional_copy_deliverable(run_state, data):
    run_state.request.input['budget'] = '12.00'
    executor, args = prepared(run_state, data, 'premium')
    args['script_draft'] = {**draft('video_script'), 'scenes': [{'visual': '书架', 'narration': '分享阅读'}]}
    with pytest.raises(Rejected, match='delivery_scope_exceeded'):
        executor.validate(run_state, 'generate_script', args)


def test_invalid_delivery_is_observed_then_model_can_correct(raw, config, data, store, clock):
    from content_agent.providers import action
    import json
    class Correcting(MockProvider):
        def decide(self, context, messages):
            if context['rounds_used'] == 3:
                message = super().decide(context, messages)
                fn = message['tool_calls'][0]['function']
                args = json.loads(fn['arguments'])
                args['script_draft'] = draft('short_copy')  # wrong for standard
                return action('generate_script', args, context['rounds_used'])
            if context['rounds_used'] == 4:
                candidate = context['candidates'][-1]
                return action('generate_script', dict(candidate_id=candidate['candidate_id'],
                    estimate_id=candidate['estimate_id'], material_ids=candidate['material_ids'],
                    script_draft=draft(), decision_summary='按报价修正为图文'), context['rounds_used'])
            return super().decide(context, messages)
    result = run_request(raw, 'correct-draft', config, data, store, Correcting(), clock)
    assert result['tool_results'][2]['error'] == 'delivery_format_mismatch'
    assert result['status'] == 'completed' and result['costs']['spent_total'] == '8.00'
    assert sum(a['action'] == 'generate_script' for a in result['attempts']) == 1


def test_missing_delivery_rules_fail_closed(tmp_path, data):
    import json
    from content_agent.cli import load_data
    del data['rules']['variants']['lean']['delivery']
    for name, value in data.items():
        (tmp_path / (name + '.json')).write_text(json.dumps(value))
    with pytest.raises(ValueError, match='invalid delivery contract'):
        load_data(tmp_path)


def test_topic_can_mention_other_media_without_declaring_deliverables(run_state, data):
    executor, args = prepared(run_state, data, 'lean')
    args['script_draft'] = {**draft('short_copy'), 'copy': '欢迎分享你喜欢的短视频，也可讨论图文传播经验。'}
    assert executor.validate(run_state, 'generate_script', args) is None


def test_image_text_rejects_embedded_video_and_lean_titles(run_state, data):
    executor, args = prepared(run_state, data)
    for copy in ['短视频脚本：画面1展示书架。', '图文正文：读书周。精简文案：分享推荐书。']:
        args['script_draft'] = {**draft(), 'copy': copy}
        with pytest.raises(Rejected, match='delivery_scope_exceeded'):
            executor.validate(run_state, 'generate_script', args)
