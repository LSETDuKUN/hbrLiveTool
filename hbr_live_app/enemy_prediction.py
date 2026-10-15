"""Conditional rule branches and a bounded, explicitly hypothetical lookahead."""
from copy import deepcopy
from .enemy_conditions import evaluate


def branches(info, rules, state):
    from .enemy_info import skill_title
    from .skill_effects import preview_effects
    result = []
    for rule in rules:
        weight = rule.get('weight', 0)
        if not isinstance(weight, (int, float)) or weight <= 0:
            continue
        verdict = evaluate(rule.get('condition', ''), state)
        if verdict is False:
            continue
        if rule.get('once'):
            used = state.get('used_rule_ids')
            verdict = None if used is None else False if rule.get('id') in used else verdict
        if verdict is False:
            continue
        skills = [info.get('skills', {}).get(k, {}) for k in rule.get('skill_list', [])]
        if not skills or any(not s for s in skills):
            verdict = None
        result.append(dict(id=rule.get('id'), condition=rule.get('condition', ''),
                           status='matched' if verdict is True else 'unknown', weight=weight,
                           observed=bool('PlayedSkillCount' in rule.get('condition', '') and state.get('played_source')),
                           skills=[skill_title(s) for s in skills] or ['未收录技能'],
                           effects=[preview_effects(s) for s in skills],
                           skill_ids=rule.get('skill_list', []), share=None, once=bool(rule.get('once'))))
    # These are conditional weight shares, not measured in-game probabilities.
    if result and all(b['status'] == 'matched' for b in result):
        total = sum(b['weight'] for b in result)
        for b in result:
            b['share'] = b['weight']/total
    return result


def find_next(info, group, start, state):
    orders = sorted({r.get('order') for r in group.get('p', [])
                     if isinstance(r.get('order'), int) and r['order'] >= start and not r.get('is_preemptive')})
    skipped = []
    for order in orders[:128]:
        rules = [r for r in group['p'] if r.get('order') == order and not r.get('is_preemptive')]
        options = branches(info, rules, state)
        if options:
            return dict(order=order, branches=options, skipped=skipped)
        skipped.append(order)
    return None


def branch_text(branch):
    text = ' → '.join(branch['skills'])
    if branch['share'] is not None and branch['share'] < 1:
        text += f'（权重占比 {branch["share"]:.0%}）'
    elif branch['status'] == 'unknown':
        text += '（条件待确认）'
    return text


def prediction_details(preview):
    lines = [preview.get('text', '行动预告未取得'), preview.get('note', '')]
    for b in preview.get('branches', []):
        lines.append('\n→ ' + branch_text(b))
        lines.append(('条件满足' if b['status'] == 'matched' else '条件待确认') +
                     '：' + (b['condition'] or '无条件') + f'；权重 {b["weight"]}')
        if b['once']:
            lines.append('仅一次规则：尚未确认是否已经触发')
    if preview.get('fallback'):
        row = preview['fallback']
        lines.append('\n若上面的未知条件均不成立，后续候选（顺序推演）：')
        lines.extend('→ ' + branch_text(b) for b in row['branches'])
    for row in preview.get('future', []):
        lines.append(f'\n后续规则 {row["order"]}（假设当前分支执行且阶段、敌人数不变）：')
        lines.extend('→ ' + branch_text(b) for b in row['branches'])
    return '\n'.join(lines)


def predict(info, live, context):
    if not context:
        return dict(text='回合状态未确认', blink=False)
    if live['overridden']:
        return dict(text='特殊行动规则 · 暂无预告', blink=False)
    # A shieldless enemy still uses its main AI; zero DP alone is not a break.
    bars = info.get('bars', {}).get('main', [])
    shieldless = live['dp_max'] == 0 if 'dp_max' in live else (bars and all(b.get('v') == 0 for b in bars))
    phase = 'dp' if live['dp'] > 0 or shieldless or not live.get('hp_pattern') else 'hp'
    group = info.get('patterns', {}).get(phase, {})
    pattern = live[phase+'_pattern']
    if live.get(phase+'_extra'):
        pattern = live.get(phase+'_active_pattern')
        if not pattern:
            return dict(text='当前盾层／血条行动阶段未确认', blink=False)
        candidates = [group] + info.get('extra_patterns', {}).get(phase, [])
        group = next((g for g in candidates if g.get('l') == pattern), {})
    if not group or group.get('l') != pattern:
        return dict(text='行动规则未匹配', blink=False)
    order = live[phase+'_order']
    if not isinstance(order, int) or order < 0:
        return dict(text='行动进度未确认', blink=False)
    state = dict(live, turn=context.get('turn'))
    current = find_next(info, group, order+1, state)
    if not current:
        return dict(text='后续分支待确认 · 可查看规则', blink=False, phase=phase)
    options = current['branches']
    unknown = any(b['status'] == 'unknown' for b in options)
    title = '条件候选' if unknown else '随机候选' if len(options)>1 else '规则预告'
    note = '按当前状态及规则顺序推演；分支权重占比不是已验证的实际概率。后续假设敌人数与阶段不变。'
    if live.get(phase+'_extra'):
        note += f' 当前第 {live[phase+"_index"]+1} 层，已匹配实际行动表。'
    if current['skipped']:
        note += ' 已跳过当前条件不满足的规则，跳过语义仍需实测。'
    if live.get('played_source'):
        note += ' 技能次数来自本次采集观测；漏采时保留未知。'
    if live.get('recent_break'):
        note += ' 已观测到击破（DP 耗尽）；行动表按当前阶段选择，特殊反击仍以其条件为准。'
    future = []
    simulated = deepcopy(state)
    step = current
    for _ in range(2):
        opts = step['branches']
        if len(opts) != 1 or opts[0]['status'] != 'matched':
            break
        for key in opts[0]['skill_ids']:
            skill = info.get('skills', {}).get(key, {})
            label = skill.get('label')
            counts = simulated.setdefault('played_counts', {})
            if label and (label in counts or simulated.get('played_complete')):
                counts[label] = counts.get(label, 0)+1
            kinds = {p.get('skill_type') for p in skill.get('parts', [])}
            if 'Charge' in kinds:
                simulated['charged'] = True
            elif 'AttackSkill' in kinds:
                simulated['charged'] = None
        # Global Turn is not incremented: extra turns and OD make that uncertain.
        simulated['turn'] = None
        step = find_next(info, group, step['order']+1, simulated)
        if not step:
            break
        future.append(step)
    # A known eligible branch prevents falling through to the next order even
    # when another branch in the same lottery has an unknown condition.
    fallback = find_next(info, group, current['order']+1, state) if all(b['status'] == 'unknown' for b in options) else None
    from .enemy_info import skill_title
    by_label = {s.get('label'): s for s in info.get('skills', {}).values()}
    previous = [skill_title(by_label.get(label, dict(label=label))) for label in live.get('last_actions', [])]
    text = title + '：' + ' 或 '.join(branch_text(b) for b in options)
    if live['down'] > 0:
        text = '倒地中 · 恢复后候选：' + ' 或 '.join(branch_text(b) for b in options)
    return dict(text=text, blink=not unknown and live['down'] <= 0 and bool(context.get('selecting')), phase=phase, order=current['order'],
                pattern=pattern, gauge_index=live.get(phase+'_index'),
                branches=options, future=future, fallback=fallback, previous=previous,
                progress_order=order, skipped=current['skipped'], note=note, down=live['down'])
