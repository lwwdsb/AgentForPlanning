"""Explicit deliverable scope and deterministic separation of facts from proposals."""
from copy import deepcopy
import re

FORMATS={'premium':'video_script','standard':'image_text','lean':'short_copy'}
LABELS={'video_script':'短视频分镜脚本','image_text':'图文正文','short_copy':'精简文案'}


def has_extra_deliverables(draft):
    """Conservative structural checks; mentioning a medium is not a deliverable."""
    text='\n'.join([draft['title'],draft['copy'],
                    *[s[k] for s in draft['scenes'] for k in ('visual','narration')]])
    headings={
        'video_script':r'(?:短?视频(?:稿|脚本)|分镜脚本|video\s+script|storyboard)',
        'image_text':r'(?:图文(?:稿|正文|预告|文案|脚本)|image\s+(?:copy|text))',
        'short_copy':r'(?:精简文案|短文案|short\s+copy)',
    }
    for format,label in headings.items():
        matches=re.findall(r'(?:^|[。！？；;\n【\[])\s*'+label+r'\s*[:：】\]]',text,re.I)
        if matches and format!=draft['format']:return True
        if len(matches)>1:return True
    if draft['format']!='video_script':
        if re.search(r'(?:^|[。！？；;\n])\s*(?:画面|镜头|分镜)\s*[0-9一二三四五六七八九十]+\s*[:：]',text):
            return True
        ranges=re.findall(r'\d{1,2}\s*(?:[-—–~]|至)\s*\d{1,2}\s*(?:秒|s\b)',text,re.I)
        if len(ranges)>=2 and re.search(r'画面|镜头|展示|旁白|shot|scene',text,re.I):return True
    return False


def check_delivery(draft, candidate, materials, rule):
    scope=rule.get('delivery')
    if not scope or scope.get('format')!=FORMATS[candidate['variant']]:
        return 'delivery_contract_missing'
    if draft['format']!=scope['format']:return 'delivery_format_mismatch'
    if has_extra_deliverables(draft):return 'delivery_scope_exceeded'
    copy=draft['copy'].strip()
    scenes=draft['scenes']
    if draft['format']=='video_script':
        if copy or not 1<=len(scenes)<=scope['max_scenes']:return 'delivery_scope_exceeded'
    elif scenes or not copy or len(copy)>scope['max_copy_chars']:
        return 'delivery_scope_exceeded'
    if draft['format']=='short_copy' and any(c in copy for c in '\n\r\u2028\u2029'):
        return 'delivery_scope_exceeded'
    if not draft['source_facts']:return 'unsupported_source_fact'
    for fact in draft['source_facts']:
        material_id=fact['material_id']
        if (material_id not in candidate['material_ids'] or not fact['quote'].strip()
                or fact['quote'] not in materials[material_id]['text']):
            return 'unsupported_source_fact'
    return None


def render_delivery(draft, scope):
    # Every free-form model field is presented as a proposal, never a verified fact.
    lines=['素材事实（逐字引用）']
    lines += [f"[{f['material_id']}] {f['quote']}" for f in draft['source_facts']]
    lines += ['', '创意草稿（待运营审核）', f"交付形式：{LABELS[draft['format']]}",
              '以下标题、正文或分镜均为创意建议；新增事实、渠道和参与规则须运营确认。', draft['title']]
    if draft['format']=='video_script':
        for i,scene in enumerate(draft['scenes'],1):
            lines += [f"分镜 {i}：{scene['visual']}", f"旁白建议：{scene['narration']}"]
    else:lines.append(draft['copy'])
    lines += ['', '运营建议（待确认，不属于已确认活动规则）']
    lines += draft['operational_suggestions'] or ['活动地点、日期和发布渠道仍须运营确认。']
    lines += ['本次报价仅涵盖所列单份脚本草稿；新增物料须另行规划估价，不包含实际拍摄、设计或投放。']
    return {'text':'\n'.join(lines), 'delivery':deepcopy(draft), 'pricing_scope':deepcopy(scope),
            'publication_status':'requires_operator_review',
            'fact_policy':'Only source_facts are exact retrieved quotations; all creative and operational text is unconfirmed.'}


def mock_draft(candidate, materials):
    format=FORMATS[candidate['variant']]
    return {'format':format,'title':'主题活动策划草稿',
            'source_facts':[{'material_id':i,'quote':materials[i]['text']} for i in candidate['material_ids']],
            'copy':'' if format=='video_script' else '欢迎了解主题活动，按运营确认的规则参与并分享体验。',
            'scenes':[{'visual':'展示主题素材','narration':'欢迎了解主题活动，具体安排以运营确认信息为准。'}] if format=='video_script' else [],
            'operational_suggestions':['建议先确认日期、地点和发布渠道，再发布审核后的内容。']}
