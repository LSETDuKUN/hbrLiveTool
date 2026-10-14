"""Exact enemy catalog enrichment; AI rules are reference, not a predicted turn axis."""
import json
import sqlite3


def rules_text(data):
    skills = {s['id']: s for s in data.get('skills', [])}
    lines = ['行动规则（资料参考）', '序号是规则顺序，不等同于战斗 Turn；条件和随机分支会改变实际行动。']
    patterns = data.get('pattern') or {}
    if not patterns:
        return ''
    for phase, group in patterns.items():
        lines.append('\n' + {'dp': 'DP 阶段', 'hp': 'HP 阶段'}.get(phase, phase))
        for rule in group.get('p', []):
            titles = []
            for key in rule.get('skill_list', []):
                skill = skills.get(key, {})
                title = skill.get('name') or skill.get('label') or str(key)
                titles.append(title)
            notes = []
            if rule.get('condition'):
                notes.append('条件：' + rule['condition'])
            if rule.get('once'):
                notes.append('仅一次')
            if rule.get('is_preemptive'):
                notes.append('先制')
            if rule.get('weight') is not None:
                notes.append(f'权重 {rule["weight"]}')
            lines.append(f'{rule.get("order", "?")} · {" → ".join(titles) or "未收录技能"}'
                         + ('  [' + '；'.join(notes) + ']' if notes else ''))
    return '\n'.join(lines)


class EnemyCatalog:
    def __init__(self):
        self.cache = {}

    def lookup(self, label='', enemy_id=None):
        key = (label, enemy_id)
        if key not in self.cache:
            result = dict(names=[], rules='', patterns={}, skills={})
            try:
                from hbr_data.store import Catalog
                catalog = Catalog()
                # Prefer the actual battle master label. Never match by fuzzy name,
                # model image or substrings shared across different encounters.
                field, value = ('label', label) if label else ('id', str(enemy_id))
                _, rows, _ = catalog.query(
                    f"SELECT region,id,label,name FROM enemies WHERE {field}=? AND region IN ('cn','en')",
                    (value,), limit=8)
                cn = [r for r in rows if r[0] == 'cn']
                if len(cn) == 1 and (enemy_id is None or str(cn[0][1]) == str(enemy_id)):
                    _, identity, exact_label, _ = cn[0]
                    result['label'] = exact_label
                    result['id'] = identity
                    for region in ('cn', 'en'):
                        matches = [r for r in rows if r[0] == region and r[1:3] == cn[0][1:3]]
                        if len(matches) == 1 and matches[0][3]:
                            result['names'].append(dict(kind=region, name=matches[0][3]))
                    _, details, _ = catalog.query(
                        "SELECT raw_json FROM records WHERE dataset='enemy_details' AND region='cn' AND label=? AND id=?",
                        (exact_label, identity), limit=2)
                    if len(details) == 1:
                        data = json.loads(details[0][0])
                        result['rules'] = rules_text(data)
                        result['patterns'] = data.get('pattern') or {}
                        result['skills'] = {s['id']: s for s in data.get('skills', [])}
            except (OSError, ValueError, RuntimeError, sqlite3.Error, TypeError, KeyError):
                pass
            self.cache[key] = result
        return self.cache[key]


def forecast(info, live, context):
    """Conservative rule preview. Never reuse _selectedCommands from a past turn."""
    if not context or not context.get('selecting'):
        return dict(text='等待指令阶段', blink=False)
    if live['down'] > 0:
        return dict(text='倒地中 · 暂不预判行动', blink=False)
    if live['overridden']:
        return dict(text='特殊行动规则 · 暂无预告', blink=False)
    phase = 'dp' if live['dp'] > 0 else 'hp'
    group = info.get('patterns', {}).get(phase, {})
    if not group or group.get('l') != live[phase + '_pattern']:
        return dict(text='行动规则未匹配', blink=False)
    order = live[phase + '_order']
    if not isinstance(order, int) or order < 0:
        return dict(text='行动进度未确认', blink=False)
    rules = [r for r in group.get('p', []) if r.get('order') == order+1 and not r.get('is_preemptive')]
    # Loop, phase reset and conditional skipping semantics are not yet verified.
    if not rules or any(r.get('once') for r in rules):
        return dict(text='后续分支待确认 · 可查看规则', blink=False)
    alternatives, conditional = [], False
    for rule in rules:
        cond = rule.get('condition', '')
        if cond == 'IsEnemyCharge()':
            if not live['charged']:
                return dict(text='蓄力条件未满足 · 后续待确认', blink=False)
        elif cond:
            conditional = True
        skills = [info.get('skills', {}).get(k, {}) for k in rule.get('skill_list', [])]
        titles = [s.get('name') or s.get('label') or '未命名技能' for s in skills]
        if not titles:
            return dict(text='技能资料未收录', blink=False)
        alternatives.append(' → '.join(titles))
    label = '条件候选' if conditional else '随机候选' if len(rules) > 1 else '规则预告'
    return dict(text=label + '：' + ' 或 '.join(alternatives), blink=not conditional,
                order=order+1, phase=phase,
                note='按当前阶段与进度推算；击破、特殊效果或随机分支可能改变行动。')
