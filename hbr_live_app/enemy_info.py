"""Exact enemy catalog enrichment; AI rules are reference, not a predicted turn axis."""
import json
import sqlite3


def skill_title(skill):
    if skill.get('name'):
        return skill['name']
    parts = skill.get('parts') or []
    if parts and all(p.get('skill_type') == 'AttackSkill' for p in parts):
        target = {'Single': '单体', 'All': '全体'}.get(skill.get('target_type'), '')
        return target + '攻击'
    return skill.get('label') or '未命名技能'


def skill_effects(skill):
    notes = [skill['desc']] if skill.get('desc') else []
    kinds = {'AttackSkill': '攻击', 'Charge': '蓄力', 'AttackUp': '攻击提升',
             'DefenseDown': '防御降低', 'HealDpRate': '按比例回复 DP', 'HealHpRate': '按比例回复 HP'}
    for part in skill.get('parts') or []:
        kind = part.get('skill_type')
        if not kind:
            continue
        target = {'Single': '单体', 'All': '全体', 'Self': '自身'}.get(part.get('target_type'), part.get('target_type') or '')
        damage_type = {'Slash': '斩', 'Stab': '突', 'Strike': '打'}.get(part.get('type'), '')
        elements = ' / '.join({'Fire': '火', 'Ice': '冰', 'Thunder': '雷', 'Light': '光', 'Dark': '暗'}.get(e, e)
                              for e in part.get('elements') or [])
        note = ' · '.join(x for x in (target, kinds.get(kind, kind), damage_type, elements) if x)
        if part.get('cond'):
            note += '（条件：' + part['cond'] + '）'
        if note not in notes:
            notes.append(note)
    return '；'.join(notes)


def rules_text(data):
    skills = {s['id']: s for s in data.get('skills', [])}
    lines = ['行动规则（资料参考）', '序号是规则顺序，不等同于战斗 Turn；条件和随机分支会改变实际行动。']
    patterns = dict(data.get('pattern') or {})
    for phase, groups in ((data.get('extra_gauge') or {}).get('pattern') or {}).items():
        for index, group in enumerate(groups):
            if group and group not in patterns.values():
                patterns[f'{phase.upper()} 第 {index+1} 层'] = group
    if not patterns and not skills:
        return ''
    for phase, group in patterns.items():
        lines.append('\n' + {'dp': 'DP 阶段', 'hp': 'HP 阶段'}.get(phase, phase))
        for rule in group.get('p', []):
            titles = []
            for key in rule.get('skill_list', []):
                skill = skills.get(key, {})
                title = skill_title(skill) if skill else str(key)
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
    if skills:
        lines.append('\n技能效果（资料记录）')
        for skill in skills.values():
            lines.append('\n' + skill_title(skill) + ' [' + str(skill.get('label', '')) + ']')
            lines.append(skill_effects(skill) or '未收录效果说明')
            if skill.get('hit_count', 0) > 0:
                lines.append(f'命中次数：{skill["hit_count"]}')
            for part in skill.get('parts') or []:
                if part.get('power') and any(part['power']):
                    lines.append(f'{part.get("skill_type", "效果")} 原始威力参数：{part["power"]}（非实际伤害）')
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
                        result['bars'] = data.get('bars') or {}
                        result['extra_patterns'] = (data.get('extra_gauge') or {}).get('pattern') or {}
                        result['skills'] = {s['id']: s for s in data.get('skills', [])}
            except (OSError, ValueError, RuntimeError, sqlite3.Error, TypeError, KeyError):
                pass
            self.cache[key] = result
        return self.cache[key]


def forecast(info, live, context):
    from .enemy_prediction import predict
    return predict(info, live, context)
