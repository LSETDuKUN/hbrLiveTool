"""UI-independent damage calculation service (roadmap B2).

This module owns the non-UI workflow that previously lived in
``hbr_live_app.damage_window``:

* :func:`prepare` -- resolve switch-skill forms, apply the shared boss stat,
  overlay sequential steps, detect combat modes, run ``autofill``, auto-precast
  confirmed attack-skill effects, and merge pending status proposals;
* :func:`apply_pending` / :func:`pre_cast_support` -- add, remove or bulk
  pre-cast status proposals while preserving unrelated manual multiplier edits;
* :func:`compute` -- validate overrides, reconcile chain expressions /
  equipment deltas / DP scaling / skill base power, run single-pool or
  segmented cross-pool simulation, and build probability distributions;
* :func:`sequence_add` / :func:`sequence_undo` / :func:`sequence_clear` --
  manage the 3-step deterministic damage sequence.

No UI toolkit (``tkinter`` etc.) may ever be imported here.
"""
from copy import deepcopy
from dataclasses import asdict, replace
import math

from hbr_live_app.damage_autofill import WEIGHTS, autofill, style_elements
from hbr_live_app.damage_inputs import STATS
from hbr_live_app.damage_math import (
    DamageInputs,
    calculate,
    enemy_attribute_reduction,
    skill_base,
)
from hbr_live_app.damage_probability import distribution
from hbr_live_app.damage_sequence import DamageSequence
from hbr_live_app.destruction import apply_to_result, dp_factor, simulate_pools
from hbr_live_app.funnels import describe as describe_funnels, parse as parse_funnels
from hbr_live_app.orb_defaults import enabled as orb_default_enabled
from hbr_live_app.passive_audit import audit_text
from hbr_live_app.pool_probability import pool_distribution
from hbr_live_app.raw_probability import raw_distribution
from hbr_live_app.shield_layers import shield_text
from hbr_live_app.skill_forms import forms as skill_forms, with_form
from hbr_live_app.sp_scaling import sp_factor

NAMES = dict(
    attack='加攻（含充能／适用心眼）',
    defense='减防（含适用脆弱）',
    affinity='相性',
    critical='暴伤',
    chain='连击',
    destruction='破坏率',
    od='OD',
    token='Token',
    specialization='DP/HP 特攻',
    health='血量条件',
    down='倒地条件',
    other='其他',
)

VALUE_KEYS = (
    'base', 'chain', 'attack', 'element_attack', 'mind_eye', 'servant_mind_eye',
    'field', 'charge', 'token_bonus', 'dp_bonus', 'hp_bonus', 'health_factor',
    'down_factor', 'other_factor', 'critical_bonus', 'element_critical_bonus',
    'defense_down', 'element_defense_down', 'fragile', 'weapon_bonus',
    'element_bonus', 'weakness_deepen', 'resistance', 'destruction', 'od',
)
FLAG_KEYS = ('critical', 'penetration_critical', 'absorbed')
PARAM_KEYS = (
    'sp_consumed', 'sp_cap', 'own_dp', 'own_dp_max', 'dp_zero_factor', 'dp_full_factor',
    'min_power', 'max_power', 'difference', 'level', 'enemy', 'orb', 'growth_min', 'growth_max',
    *WEIGHTS, *('weight_' + k for k in WEIGHTS),
    'calamity', 'fear_of_devil', 'critical_rate_bonus', 'element_critical_rate_bonus',
    'morale_level', 'od_gain_bonus', 'enemy_dp', 'enemy_hp', 'skill_dr', 'main_hits',
    'enemy_dr', 'max_dr', 'destruction_bonus',
)

ELEMENT_CODES = {
    '火': 1, 'Fire': 1, 'fire': 1, 1: 1,
    '冰': 2, 'Ice': 2, 'ice': 2, 2: 2,
    '雷': 3, 'Thunder': 3, 'thunder': 3, 3: 3,
    '光': 4, 'Light': 4, 'light': 4, 4: 4,
    '暗': 5, 'Dark': 5, 'dark': 5, 5: 5,
}
CODE_ELEMENTS = {1: 'Fire', 2: 'Ice', 3: 'Thunder', 4: 'Light', 5: 'Dark'}


def parse_enemy_stat(text):
    """Parse the shared boss stat input string; return float or None."""
    if text is None or isinstance(text, (int, float)) and not isinstance(text, bool):
        value = None if text is None else float(text)
    else:
        cleaned = str(text).strip().replace(',', '')
        value = float(cleaned) if cleaned else None
    if value is not None and (value < 0 or not math.isfinite(value)):
        raise ValueError('敌方属性必须为非负有限数')
    return value


def apply_shared_enemy(enemy, enemy_stat_override=None):
    """Apply the shared boss stat to one enemy snapshot (or mirror the read value).

    Returns ``(enemy_dict, live_stat_value)``.
    """
    inputs = enemy.get('combat_inputs', enemy.get('inputs', {}))
    live = inputs.get('_defenseRefParam')
    if enemy_stat_override is None:
        return enemy, live
    inputs = dict(inputs, _defenseRefParam=enemy_stat_override)
    return dict(enemy, combat_inputs=inputs, inputs=inputs), live


def resolve_skill_forms(data, actor_id, form_choice=None, form_key=None, lookup=None):
    """Resolve concrete form for switch skills: manual for selected actor, auto otherwise."""
    players, notes = [], []
    labels = ['无切换形态']
    selected_label = '无切换形态'
    new_key = form_key
    resolved_index = None
    for player in data.get('players', []):
        choice = None
        if player.get('actor_id') == actor_id:
            selected = player.get('combat_inputs', player.get('inputs', {})).get('selected_skill') or {}
            options = skill_forms(selected.get('label'), lookup=lookup)
            key = (actor_id, selected.get('label'))
            labels = ['自动判断形态'] + [f'形态 {i + 1} · {name}' for i, (_, name, _) in enumerate(options)]
            if not options:
                labels = ['无切换形态']
            if isinstance(form_choice, int) and not isinstance(form_choice, bool):
                choice = form_choice if options and 0 <= form_choice < len(options) else None
                selected_label = labels[choice + 1] if choice is not None else labels[0]
            else:
                if key != form_key or form_choice not in labels:
                    selected_label = labels[0]
                else:
                    selected_label = form_choice
                current = labels.index(selected_label)
                choice = current - 1 if options and current > 0 else None
            new_key = key
            resolved_index = choice
        resolved, note = with_form(player, choice, lookup=lookup)
        if note and player.get('actor_id') == actor_id:
            notes.append(note)
        players.append(resolved)
    return dict(
        data=dict(data, players=players),
        notes=notes,
        labels=labels,
        selected_label=selected_label,
        form_key=new_key,
        form_index=resolved_index,
    )


def _resolve_toggle(choice, automatic_value):
    if choice in (None, '自动', 'auto'):
        return automatic_value, True
    if choice in ('启用', 'on', True):
        return True, False
    if choice in ('禁用', 'off', False):
        return False, False
    return automatic_value, True


def build_modes(data, player, options=None):
    """Compute combat mode flags from snapshot and user mode options."""
    options = options or {}
    inputs = player.get('combat_inputs', player.get('inputs', {}))
    gauge = data.get('element_gauge') or {}
    turn = inputs.get('reinforced_mode_turn')
    automatic = dict(
        transcend=gauge.get('full') is True,
        high_boost=any(
            s.get('label') == 'SpecialStatus.HighBoost'
            and s.get('effective') is not False
            and not s.get('pending_add')
            and not s.get('pending_remove')
            for s in player.get('statuses', [])
        ),
        ghost=isinstance(turn, int) and turn > 0,
        gidou='Passive.Condition_AttackUp11' in inputs.get('passive_labels', []),
    )
    modes = {}
    for key in ('transcend', 'high_boost'):
        val, is_auto = _resolve_toggle(options.get(key, '自动'), automatic[key])
        if key == 'high_boost' and is_auto:
            # Let autofill apply its complete status/expiry/condition filtering in auto mode.
            continue
        modes[key] = val
    modes.update(ghost=automatic['ghost'], gidou=automatic['gidou'])
    modes['enemies'] = data.get('enemies', [])
    od = data.get('od_state') or {}
    modes.update(od_active=od.get('active') if od.get('available') else None, od_level=od.get('level'))
    modes['lightning_style'] = 'Thunder' in style_elements(player.get('style_label', ''))
    raw_element = options.get('transcend_element', '自动属性')
    selected_element = ELEMENT_CODES.get(raw_element, gauge.get('element'))
    if modes.get('transcend'):
        modes['super_break_element'] = CODE_ELEMENTS.get(selected_element)
    # Thunder's stat bonuses are verified separately. Do not apply them to
    # another element merely because its gauge is full.
    modes['transcend'] = bool(modes.get('transcend') and selected_element == 3)
    return modes


def format_pending_rows(pending_effects):
    lines = []
    for row in pending_effects:
        amount = f'{row["amount"]:g}%'
        if row['state']['label'] == 'SpecialStatus.Funnel':
            amount = f'{row["state"]["values"]["numValue"]} 颗 × ' + amount
        lines.append('、'.join(row.get('target_names', [])) + ' ← ' + row['item']['title'] + ' ' + amount)
    return lines


def format_chain_expression(filled):
    count = filled.get('params', {}).get('main_hits') or 0
    return describe_funnels(filled.get('chain_weights', filled.get('hit_weights', [])[int(count):]))


def format_equipment_text(equipment_notes):
    return (
        '饰品贡献已计入相应乘区，不需要再次相加。\n'
        '按运行时已装备被动匹配；实际状态优先于预填。\n\n'
        + '\n\n'.join(equipment_notes or ['未读到可确认的饰品效果'])
    )


def format_fill_notes(notes, skipped):
    return (
        '自动填充来源与假设：\n'
        + '\n'.join(notes)
        + '\n\n未自动计入 / 待核对：\n'
        + '\n'.join(skipped)
    )


def format_values_dict(values):
    defaults = DamageInputs()
    result = {}
    for key in VALUE_KEYS:
        v = values.get(key, getattr(defaults, key, None))
        result[key] = '' if v is None else str(v) if key == 'destruction' else f'{v:g}'
    return result


def format_params_dict(params):
    result = {}
    for key in PARAM_KEYS:
        v = params.get(key)
        if key == 'orb' and v is None:
            result[key] = '5'
        else:
            result[key] = '' if v is None else str(v) if key in ('enemy_dp', 'enemy_hp') else f'{v:g}'
    return result


def battle_identity(data):
    return data.get('run_id') or tuple(p.get('actor_id') for p in data.get('players', []))


def prepare(
    snapshot,
    actor_id,
    enemy_address,
    options=None,
    *,
    sequence=None,
    sequence_battle=None,
    pending_effects=None,
    dismissed_effects=None,
    pending_battle=None,
    form_key=None,
    autofill_fn=None,
):
    """Prepare autofilled calculation state for ``(actor_id, enemy_address)``.

    Returns a plain ``PreparedCalc`` dictionary. Does not mutate ``snapshot``.
    """
    options = dict(options or {})
    run_autofill = autofill_fn or autofill
    if not snapshot.get('connected'):
        return dict(
            ok=False,
            connected=False,
            reason='disconnected',
            fill_notes='未连接战斗，未覆盖表单',
        )
    enemy_stat_override = parse_enemy_stat(options.get('enemy_stat'))
    form_choice = options.get('form_index') if 'form_index' in options and options.get('form_index') is not None else options.get('form_choice')
    form_info = resolve_skill_forms(snapshot, actor_id, form_choice=form_choice, form_key=form_key)
    data = form_info['data']
    form_notes = form_info['notes']
    if enemy_stat_override is not None:
        data = dict(data, enemies=[apply_shared_enemy(e, enemy_stat_override)[0] for e in data.get('enemies', [])])
    player = next((p for p in data.get('players', []) if p.get('actor_id') == actor_id), None)
    enemy = next((e for e in data.get('enemies', []) if e.get('address') == enemy_address), None)
    if player is None or enemy is None:
        return dict(
            ok=False,
            connected=True,
            reason='missing_target',
            fill_notes='所选角色/敌人已变化，请刷新列表',
            form_info=form_info,
        )
    identity = battle_identity(data)
    sequence_reset = False
    if sequence is not None:
        if sequence_battle is not None and sequence_battle != identity:
            sequence.clear()
            sequence_reset = True
        try:
            enemy = sequence.overlay(enemy)
        except ValueError as exc:
            return dict(
                ok=False,
                connected=True,
                reason='sequence_conflict',
                sequence_error=str(exc),
                sequence_battle=identity,
                sequence_reset=sequence_reset,
                form_info=form_info,
            )
    enemy, live_enemy_stat = apply_shared_enemy(enemy, enemy_stat_override)
    modes = build_modes(data, player, options)
    filled = run_autofill(player, enemy, data.get('field_state'), modes=modes, party=data.get('players', []))

    from hbr_live_app.effect_pending import PREVIEW_KEYS, skill_rows, with_pending
    from hbr_live_app.damage_autofill import catalog_skill
    from hbr_data.skill_tree import effects
    from hbr_data.battle_conditions import context_for

    if pending_battle is not None and pending_battle != identity:
        pending_list = []
        dismissed_set = set()
    else:
        pending_list = list(pending_effects or [])
        dismissed_set = set(dismissed_effects or ())
    pending_delta = {}
    damage_orb = orb_default_enabled(player, 'damage')
    pending_context = (player, enemy, data.get('field_state'), modes, data.get('players', []))
    pending_base = filled

    selected = player.get('combat_inputs', player.get('inputs', {})).get('selected_skill', {})
    skill = catalog_skill(selected.get('label')) if selected.get('label') else {}
    if (data.get('turn_context') or {}).get('selecting') is not False and any(
        str(p.get('skill_type', '')).startswith('Attack')
        and p.get('skill_type') not in ('AttackUp', 'AttackUpIncludeNormal')
        for p in effects(skill, context_for(player, enemy, modes), include_unknown=False)
    ):
        rows, skipped = skill_rows(player, enemy, data.get('players', []), data.get('enemies', []), modes, pending_list)
        rows = [r for r in rows if (r['item'].get('caster'), r['item']['part'].get('label')) not in dismissed_set]
        pending_list.extend(rows)
        filled['skipped'].extend(skipped)
    if pending_list:
        p, e = with_pending(player, enemy, pending_list)
        filled = run_autofill(p, e, data.get('field_state'), modes=modes, party=data.get('players', []))
        pending_delta = {k: filled['values'][k] - pending_base['values'][k] for k in PREVIEW_KEYS}

    gauge = data.get('element_gauge') or {}
    filled['notes'][:0] = form_notes
    filled['notes'].append(
        '模式判断：'
        + str({k: v for k, v in modes.items() if k != 'enemies'})
        + '；自动依据雷量表、风格资料、强化剩余回合及运行时天赋列表，可手动纠正。'
    )
    if not gauge:
        filled['skipped'].append('元素量表未读取：超越可手动启用，仍需确认是雷属性风格')

    shield = enemy.get('enemy_progress', {}).get('shield')
    auto_pool_blocked = bool(enemy.get('enemy_progress', {}).get('dp_extra')) and not (
        shield and shield.get('limit_per_turn') == 1
    )
    if shield:
        filled['notes'].append(shield_text(shield) + '；下一层 DP 容量来自本地资料')

    values_str = format_values_dict(filled['values'])
    params_str = format_params_dict(filled.get('params', {}))
    flags = {k: bool(filled['values'].get(k, False)) for k in FLAG_KEYS}
    hit_weights_str = ', '.join(f'{w:.8g}' for w in filled.get('hit_weights', []))
    chain_expr = format_chain_expression(filled)
    fill_notes = format_fill_notes(filled['notes'], filled['skipped'])

    return dict(
        ok=True,
        connected=True,
        actor_id=actor_id,
        enemy_address=enemy_address,
        player=player,
        enemy=enemy,
        party=data.get('players', []),
        enemies=data.get('enemies', []),
        modes=modes,
        form_info=form_info,
        live_enemy_stat=live_enemy_stat,
        enemy_stat_override=enemy_stat_override,
        identity=identity,
        sequence_battle=identity,
        sequence_reset=sequence_reset,
        pending_battle=identity,
        pending_context=pending_context,
        pending_base=pending_base,
        pending_effects=pending_list,
        dismissed_effects=dismissed_set,
        pending_delta=pending_delta,
        pending_lines=format_pending_rows(pending_list),
        filled=filled,
        values=values_str,
        params=params_str,
        flags=flags,
        pool='auto',
        damage_metric=options.get('damage_metric', 'raw'),
        use_skill=True,
        damage_orb_enabled=damage_orb,
        use_destruction=bool(filled.get('destruction_ready', False)),
        use_dp_scaling=bool(filled.get('dp_scaling', False)),
        sp_scaling=bool(filled.get('sp_scaling', False)),
        sp_dr_scaling=False,
        hp_adjustments=dict(filled.get('hp_adjustments', {})),
        shield_state=shield,
        auto_pool_blocked=auto_pool_blocked,
        hit_weights_str=hit_weights_str,
        hit_note=filled.get('hit_note', '权重未确认'),
        filled_chain=filled['values']['chain'],
        pending_chain_weights=list(filled.get('chain_weights', [])),
        chain_expression=chain_expr,
        skill_title=filled.get('skill', ''),
        equipment_details=list(filled.get('equipment_details', [])),
        equipment_owned=list(filled.get('equipment_owned', [])),
        equipment_notes=list(filled.get('equipment_notes', [])),
        equipment_text=format_equipment_text(filled.get('equipment_notes', [])),
        fill_notes=fill_notes,
        notes=list(filled['notes']),
        skipped=list(filled['skipped']),
    )


def pre_cast_support(prepared, caster_index=None, caster_id=None):
    """Collect supported skill effect rows for the chosen party caster."""
    if not prepared or 'pending_context' not in prepared:
        raise ValueError('请先自动填充伤害角色和敌人')
    from hbr_live_app.effect_pending import skill_rows

    player, enemy, fields, modes, party = prepared['pending_context']
    if caster_id is not None:
        player = next((p for p in party if p.get('actor_id') == caster_id), player)
    elif caster_index is not None and 0 <= caster_index < len(party):
        player = party[caster_index]
    modes = dict(modes, lightning_style='Thunder' in style_elements(player.get('style_label', '')))
    existing = list(prepared.get('pending_effects', []))
    rows, skipped = skill_rows(player, enemy, party, modes.get('enemies') or [enemy], modes, existing)
    existing.extend(rows)
    updated = dict(prepared, pending_effects=existing, pending_lines=format_pending_rows(existing))
    message = f'已预发动 {len(rows)} 项效果；按对象保存。' + '\n'.join(skipped)
    return updated, rows, skipped, message


def apply_pending(
    prepared,
    action,
    payload,
    current_values=None,
    current_hit_weights=None,
    *,
    autofill_fn=None,
):
    """Add or remove a pending status proposal and reconcile multiplier deltas."""
    if not prepared or 'pending_context' not in prepared:
        raise ValueError('请先自动填充伤害角色和敌人')
    from hbr_live_app.effect_pending import PREVIEW_KEYS, targeted_row, with_pending

    run_autofill = autofill_fn or autofill
    player, enemy, fields, modes, party = prepared['pending_context']
    rows = list(prepared.get('pending_effects', []))
    dismissed = set(prepared.get('dismissed_effects', ()))
    if action == 'add':
        item, amount = payload
        if item.get('passive') and any(
            r['item'].get('source') == item.get('source')
            and r['item'].get('caster') == item.get('caster')
            and r['item']['part'].get('label') == item['part'].get('label')
            for r in rows
        ):
            raise ValueError('该来源被动已预添加；请删除后再修改，避免重复计入')
        recipient = next((p for p in party if p.get('actor_id') == item.get('recipient_id')), player)
        row = targeted_row(item, amount, party or [player], modes.get('enemies') or [enemy], recipient, enemy)
        if item.get('part', {}).get('_branch_path') and any(
            r['item'].get('source') == item.get('source')
            and r['item']['part'].get('_branch_path') != item['part']['_branch_path']
            for r in rows
        ):
            raise ValueError('同一技能已有另一个条件分支，请先删除再切换场景')
        rows.append(row)
    elif action == 'remove':
        removed = rows.pop(payload)
        dismissed.add((removed['item'].get('caster'), removed['item']['part'].get('label')))
    else:
        raise ValueError(f'未知预添加操作：{action}')

    p, e = with_pending(player, enemy, rows)
    computed = run_autofill(p, e, fields, modes=modes, party=party)
    keys = PREVIEW_KEYS
    pending_base = prepared['pending_base']
    old_delta = prepared.get('pending_delta', {})
    delta = {k: computed['values'][k] - pending_base['values'][k] for k in keys}

    base_values = dict(prepared.get('values', {}))
    if current_values:
        base_values.update(current_values)
    updates = {k: float(base_values[k]) - old_delta.get(k, 0) + delta[k] for k in keys}
    for k, v in updates.items():
        base_values[k] = f'{v:.10g}'

    beads = computed.get('chain_weights', [])
    prev_beads = prepared.get('pending_chain_weights', pending_base.get('chain_weights', []))
    chain_changed = delta['chain'] != old_delta.get('chain', 0) or beads != prev_beads

    hit_weights_str = current_hit_weights if current_hit_weights is not None else prepared.get('hit_weights_str', '')
    filled_chain = prepared.get('filled_chain')
    chain_expression = prepared.get('chain_expression', '0 × 25%')
    if chain_changed:
        count = int(computed.get('params', {}).get('main_hits') or 0)
        raw = str(hit_weights_str).replace('，', ',').replace(' ', ',')
        current = [float(w) for w in raw.split(',') if w.strip()]
        new = computed.get('hit_weights', [])
        weights = current[:count] + beads if count and len(current) >= count else new
        hit_weights_str = ', '.join(f'{w:.8g}' for w in weights)
        filled_chain = computed['values']['chain']
        chain_expression = format_chain_expression(dict(computed, hit_weights=weights))

    status_text = (
        '已按施加对象保存，并重新筛选覆盖；切换角色自动填充后仍保留。当前乘区净变化：'
        + ', '.join(f'{k} {v:+.3f}%' for k, v in delta.items() if v)
    )
    return dict(
        prepared,
        values=base_values,
        updates=updates,
        hp_adjustments=dict(computed.get('hp_adjustments', {})),
        pending_chain_weights=list(beads),
        pending_effects=rows,
        dismissed_effects=dismissed,
        pending_delta=delta,
        pending_lines=format_pending_rows(rows),
        hit_weights_str=hit_weights_str,
        filled_chain=filled_chain,
        chain_expression=chain_expression,
        chain_changed=chain_changed,
        pending_status_text=status_text,
    )


def _merge_state_and_overrides(prepared, overrides):
    defaults = DamageInputs()
    base = prepared or {}
    ov = dict(overrides or {})

    values = {k: ('' if getattr(defaults, k) is None else str(getattr(defaults, k))) for k in VALUE_KEYS}
    values.update(base.get('values', {}))
    if isinstance(ov.get('values'), dict):
        for k, v in ov['values'].items():
            values[k] = '' if v is None else str(v)

    params = {k: ('5' if k == 'orb' else '') for k in PARAM_KEYS}
    params.update(base.get('params', {}))
    if isinstance(ov.get('params'), dict):
        for k, v in ov['params'].items():
            params[k] = '' if v is None else str(v)

    flags = {k: getattr(defaults, k) for k in FLAG_KEYS}
    flags.update(base.get('flags', {}))
    if isinstance(ov.get('flags'), dict):
        for k, v in ov['flags'].items():
            flags[k] = bool(v)

    # Support flat overrides for convenience in headless/API calls.
    for k in VALUE_KEYS:
        if k in ov:
            values[k] = '' if ov[k] is None else str(ov[k])
    for k in PARAM_KEYS:
        if k in ov:
            params[k] = '' if ov[k] is None else str(ov[k])
    for k in FLAG_KEYS:
        if k in ov:
            flags[k] = bool(ov[k])

    pool = ov.get('pool', ov.get('target_pool', base.get('pool', 'hp')))
    damage_metric = ov.get('damage_metric', base.get('damage_metric', 'raw'))
    use_skill = bool(ov.get('use_skill', base.get('use_skill', False)))
    damage_orb_enabled = bool(ov.get('damage_orb_enabled', base.get('damage_orb_enabled', False)))
    use_destruction = bool(ov.get('use_destruction', base.get('use_destruction', False)))
    use_dp_scaling = bool(ov.get('use_dp_scaling', base.get('use_dp_scaling', False)))
    sp_scaling = bool(ov.get('sp_scaling', base.get('sp_scaling', False)))
    sp_dr_scaling = bool(ov.get('sp_dr_scaling', base.get('sp_dr_scaling', False)))
    hit_weights = ov.get('hit_weights', base.get('hit_weights_str', ''))
    if isinstance(hit_weights, (list, tuple)):
        hit_weights = ', '.join(f'{float(w):.8g}' for w in hit_weights)
    else:
        hit_weights = str(hit_weights or '')
    chain_expression = str(ov.get('chain_expression', base.get('chain_expression', '0 × 25%')))
    chain_dirty = bool(ov.get('chain_dirty', False))
    filled_chain = ov.get('filled_chain', base.get('filled_chain'))
    hp_adjustments = dict(ov.get('hp_adjustments', base.get('hp_adjustments', {})))
    shield_state = ov.get('shield_state', base.get('shield_state'))
    auto_pool_blocked = bool(ov.get('auto_pool_blocked', base.get('auto_pool_blocked', False)))
    equipment_callback = ov.get('equipment_apply')

    return dict(
        values=values,
        params=params,
        flags=flags,
        pool=pool,
        damage_metric=damage_metric,
        use_skill=use_skill,
        damage_orb_enabled=damage_orb_enabled,
        use_destruction=use_destruction,
        use_dp_scaling=use_dp_scaling,
        sp_scaling=sp_scaling,
        sp_dr_scaling=sp_dr_scaling,
        hit_weights=hit_weights,
        chain_expression=chain_expression,
        chain_dirty=chain_dirty,
        filled_chain=filled_chain,
        hp_adjustments=hp_adjustments,
        shield_state=shield_state,
        auto_pool_blocked=auto_pool_blocked,
        equipment_callback=equipment_callback,
    )


def _single_pool_probability(damage, hit_weights_str, effective_weights, filled_chain, chain_value):
    try:
        raw = str(hit_weights_str).replace('，', ',').replace(' ', ',')
        weights = [float(w) for w in raw.split(',') if w.strip()]
        data = distribution(effective_weights if effective_weights is not None else weights)
        scale = damage if damage is not None else 1
        unit = '伤害' if damage is not None else '倍率'
        text = (
            f"{data['hits']} Hit · 中央 90% {unit}区间："
            f"{data['low'] * scale:,.4g} – {data['high'] * scale:,.4g} · 浮动标准差 {data['sigma']:.2%}"
        )
        if filled_chain is not None and float(chain_value) != filled_chain:
            text += '\n连击合计已修改：请同步修改上方追击权重，曲线仍按当前权重列表计算。'
        return data, damage, text
    except ValueError as exc:
        return None, damage, '曲线未生成：' + str(exc)


def compute(prepared=None, overrides=None):
    """Run damage, per-hit destruction and probability calculations.

    Returns a ``CalcResult`` dictionary with both structured numbers and
    UI-ready text blocks.
    """
    state = _merge_state_and_overrides(prepared, overrides)
    values_str = state['values']
    params_str = state['params']
    flags = state['flags']
    pool = state['pool']
    damage_metric = state['damage_metric']
    use_skill = state['use_skill']
    damage_orb_enabled = state['damage_orb_enabled']
    use_destruction = state['use_destruction']
    use_dp_scaling = state['use_dp_scaling']
    sp_scaling = state['sp_scaling']
    sp_dr_scaling = state['sp_dr_scaling']
    hit_weights_str = state['hit_weights']
    chain_expression = state['chain_expression']
    chain_dirty = state['chain_dirty']
    filled_chain = state['filled_chain']
    hp_adjustments = state['hp_adjustments']
    shield_state = state['shield_state']
    auto_pool_blocked = state['auto_pool_blocked']
    equipment_callback = state['equipment_callback']

    updated_values = {}
    updated_params = {}
    errors = {}
    destruction_report = ''
    calculation_status = None
    plot_data = None
    plot_damage = None
    prob_summary = ''
    detail = None
    result = None
    inputs = None
    candidate = None
    kill_probability = None
    ok = True

    try:
        if chain_dirty:
            beads = parse_funnels(chain_expression)
            values_str['chain'] = f'{sum(beads) * 100:g}'
            updated_values['chain'] = values_str['chain']
            raw = hit_weights_str.replace('，', ',').replace(' ', ',')
            weights = [float(w) for w in raw.split(',') if w.strip()]
            count = int(float(params_str['main_hits'] or 0))
            if count > 0 and len(weights) >= count:
                hit_weights_str = ', '.join(str(w) for w in weights[:count] + beads)
                updated_values['hit_weights'] = hit_weights_str
            chain_dirty = False

        auto = pool == 'auto'
        cross = auto
        if auto and auto_pool_blocked:
            errors['pool'] = '当前为多层盾，自动跨池尚未支持；可选择单池核对'
            raise ValueError(errors['pool'])

        if cross or use_destruction:
            labels = {
                'enemy_dp': '剩余 DP',
                'skill_dr': '技能破坏倍率',
                'main_hits': '本体 Hit 数',
                'enemy_dr': '敌人有效破坏系数',
                'max_dr': '本技能破坏率上限',
                'destruction_bonus': '破坏率获取提升',
            }
            if not cross:
                labels.pop('enemy_dp')
            missing = []
            for key, label in labels.items():
                if not str(params_str.get(key, '')).strip():
                    missing.append(label)
                    errors[key] = f'请填写{label}'
            if not hit_weights_str.strip():
                missing.append('各 Hit 伤害权重（计算明细内）')
                errors['hit_weights'] = '请填写各 Hit 伤害权重'
            calculation_status = (
                '待补齐：' + '、'.join(missing)
                if missing
                else '逐段参数已齐全；连续预演继承上一人的终值。'
            )
            if missing:
                raise ValueError('请自动填充或补齐：' + '、'.join(missing))

        if equipment_callback is not None:
            equipment_callback(values_str, params_str, updated_values, updated_params)

        if use_dp_scaling:
            factor = dp_factor(
                *(float(params_str[k]) for k in ('own_dp', 'own_dp_max', 'dp_zero_factor', 'dp_full_factor'))
            )
            values_str['health_factor'] = f'{factor:.10g}'
            updated_values['health_factor'] = values_str['health_factor']

        values = {}
        for k in VALUE_KEYS:
            if k == 'base':
                continue
            try:
                values[k] = float(values_str[k])
            except (TypeError, ValueError):
                errors[k] = f'{k} 不是有效数字'
                raise ValueError(f'{k} 不是有效数字') from None

        base = str(values_str.get('base', '')).strip()
        if use_skill:
            skill_params = dict(params_str)
            skill_params['sp_scaling'] = sp_scaling
            if not damage_orb_enabled:
                skill_params['orb'] = '0'
            computed, _ = skill_base(skill_params, flags['critical'])
            base = str(computed)
            values_str['base'] = f'{computed:.8g}'
            updated_values['base'] = values_str['base']

        values.update(
            base=float(base) if base else None,
            target_pool=('dp' if float(params_str['enemy_dp']) > 0 else 'hp') if auto else pool,
            **flags,
        )
        inputs = DamageInputs(**values)
        if not cross and inputs.target_pool == 'hp' and hp_adjustments:
            inputs = replace(inputs, **{k: getattr(inputs, k) + v for k, v in hp_adjustments.items()})
        result = calculate(inputs)

        if cross or use_destruction:
            raw = hit_weights_str.replace('，', ',').replace(' ', ',')
            weights = [float(w) for w in raw.split(',') if w.strip()]
            count = float(params_str['main_hits'])
            if not math.isfinite(count) or not count.is_integer():
                errors['main_hits'] = '本体 Hit 数必须为整数'
                raise ValueError('本体 Hit 数必须为整数')
            args = [float(params_str[k]) for k in ('skill_dr', 'enemy_dr', 'destruction_bonus', 'max_dr')]
            if sp_scaling and sp_dr_scaling:
                args[0] *= sp_factor(params_str['sp_consumed'], params_str['sp_cap'])
            if cross:
                hp = str(params_str.get('enemy_hp', '')).strip()
                candidate = dict(
                    inputs=inputs,
                    weights=weights,
                    main_hits=int(count),
                    skill_dr=args[0],
                    enemy_coefficient=args[1],
                    bonus=args[2],
                    maximum=args[3],
                    enemy_dp=float(params_str['enemy_dp']),
                    enemy_hp=float(hp) if hp else None,
                    hp_adjustments=hp_adjustments,
                    shield=shield_state,
                )
                detail = simulate_pools(**candidate)
                result.update(
                    damage=detail['damage'],
                    minimum=None,
                    maximum=None,
                    multiplier=None,
                    note='逐段跨池基准情景；破盾溢出丢弃，不计入 HP。支持已确认的阿蒙锁盾；其他多层盾、动态增减益及伤害衰减未模拟。',
                )
            else:
                result, detail = apply_to_result(result, inputs, weights, int(count), *args)
            lines = [f"破坏率：{inputs.destruction:g}% → {detail['final']:g}%"]
            lines.append(
                f"理论增量 {detail['theoretical_increment']:.3f} 个百分点（不计上限终值 {detail['theoretical_final']:.3f}%）\n"
                f"实际增量 {detail['actual_increment']:.3f} 个百分点 · 被上限截去 {detail['clipped']:.3f} 个百分点"
            )
            if detail.get('segmented'):
                lines.append(
                    f"DP 扣除 {detail['dp_damage']:,.2f} · HP 扣除 {detail['hp_damage']:,.2f} · "
                    f"丢弃破盾溢出 {detail['overflow']:,.2f}"
                )
            for row in detail['rows']:
                if detail.get('segmented'):
                    suffix = (
                        f" · {row['pool'].upper()} 原伤害 {row['raw_damage']:,.2f} / "
                        f"扣除 {row['applied_damage']:,.2f} / 丢弃溢出 {row['overflow']:,.2f}"
                    )
                else:
                    share = (
                        (result['damage'] * row['damage_weight'] / detail['weighted'])
                        if result['damage'] is not None
                        else None
                    )
                    suffix = f" · 基准伤害 {share:,.2f}" if share is not None else ''
                lines.append(
                    f"{row['hit']:>2} {row['kind']} · 破坏率 {row['before']:.3f}% → {row['after']:.3f}% · "
                    f"理论 +{row['theoretical_increment']:.3f} / 实际 +{row['increment']:.3f} 个百分点"
                    + suffix
                )
            destruction_report = '\n'.join(lines)

        if values['absorbed']:
            plot_data = None
            plot_damage = result['damage']
            prob_summary = '吸收情景不输出伤害概率曲线'
        elif detail and detail.get('segmented'):
            data = pool_distribution(detail)
            applied_data = data
            if damage_metric == 'raw':
                data = raw_distribution(detail)
            plot_data = data
            plot_damage = 1
            branches = '；'.join(
                ('未破盾' if b['hit'] is None else '起始已破盾' if b['hit'] == 0 else f"第 {b['hit']} 段破盾")
                + f" {b['probability']:.3%}"
                for b in applied_data['branches']
            )
            if data.get('raw'):
                method = (
                    '固定逐段系数卷积（与单池模型一致）'
                    if data['method'] == 'convolution'
                    else '破盾 / 击杀分支条件卷积（数值网格近似）'
                )
                summary = (
                    f"打出伤害：{method}，含破盾及锁盾溢出；击杀后仍计算后续段与破坏率增长。\n"
                    f"真实分支可能产生折点或多峰；极小尾部概率仍受网格精度限制。\n"
                    f"实际扣除均值 {applied_data['mean']:,.2f}\n" + branches
                )
            else:
                summary = (
                    f"破盾分支数值卷积 · 实际扣除均值 {data['mean']:,.4g} · "
                    f"中央 90%：{data['low']:,.4g} – {data['high']:,.4g}\n" + branches
                )
            kill_probability = applied_data.get('kill_probability')
            if kill_probability is not None:
                summary += f"\n当前模型击杀概率 {kill_probability:.3%}（按实际扣除判断）"
            if data['atoms']:
                summary += '\n集中概率：' + '；'.join(f'{x:,.4g} 伤害 {p:.3%}' for x, p in data['atoms'])
            prob_summary = summary
        else:
            plot_data, plot_damage, prob_summary = _single_pool_probability(
                result['damage'],
                hit_weights_str,
                detail['weights'] if detail else None,
                filled_chain,
                values_str['chain'],
            )
            if damage_metric == 'applied':
                prob_summary += '\n当前为单池参考计算，仅显示打出伤害；实际扣除量需启用自动跨 DP/HP。'

        detail_text = '弱点条件：' + ('满足' if result['weak'] else '不满足（不计心眼／脆弱）') + '\n'
        if detail and detail.get('segmented'):
            detail_text += '跨池各段分别采用 DP/HP 特攻，下面单池乘区仅供参考。\n'
        detail_text += '  ×  '.join(f'{NAMES[k]} {v:.4g}' for k, v in result['factors'].items()) + '\n\n'
        if use_skill:
            detail_text += (
                f"敌方属性下降采用最高值：{enemy_attribute_reduction(params_str, flags['critical']):g} 点\n"
            )
        if result['multiplier'] is not None:
            detail_text += f"总倍率：{result['multiplier']:.6g}\n"
        od_gain = str(params_str.get('od_gain_bonus', '')).strip()
        if od_gain:
            gain = float(od_gain)
            if not math.isfinite(gain) or gain < 0:
                errors['od_gain_bonus'] = 'OD 获取增幅必须为有限非负数'
                raise ValueError('OD 获取增幅必须为有限非负数')
            detail_text += f'OD 饰品获取倍率：×{1 + gain / 100:g}（例如原获取 20% → {20 * (1 + gain / 100):g}%；不影响伤害）\n'
        if result['damage'] is not None:
            if detail and detail.get('segmented'):
                detail_text += (
                    f"无浮动基准打出伤害（含溢出）：{detail['raw_damage']:,.2f}\n"
                    f"实际扣除 DP＋HP：{result['damage']:,.2f}\n"
                )
            else:
                detail_text += f"未衰减试算伤害：{result['damage']:,.2f}\n"
            if result['minimum'] is not None:
                detail_text += f"0.9–1.1 浮动边界：{result['minimum']:,.2f} – {result['maximum']:,.2f}\n"
                detail_text += '这是理论边界，不表示总伤害在区间内均匀分布；多 Hit 独立浮动通常更集中。\n'
            else:
                detail_text += '此处为无浮动基准；随机伤害均值、区间和各破盾段概率见浮动概率曲线。\n'
        if detail:
            detail_text += f"破坏率递推终值：{detail['final']:g}%（逐段明细见下方折叠区）\n"
        else:
            detail_text += '逐段递推未启用：沿用固定破坏率，可启用主页面明细中的单池逐段比较。\n'
        detail_text += result['note'] + '\n充能暂按参考计算器并入加攻。Token 与血量条件需填技能适用的实际增幅。'
    except (ValueError, OverflowError) as exc:
        ok = False
        errors.setdefault('_general', str(exc))
        detail_text = '无法计算：' + str(exc)
        plot_data = None
        prob_summary = detail_text
        candidate = None

    mean = None
    low = None
    high = None
    if plot_data:
        scale = plot_damage if plot_damage is not None else 1
        mean = plot_data['mean'] if plot_data.get('absolute') else plot_damage
        low = plot_data['low'] * scale if mean is not None or plot_data.get('absolute') else plot_data['low']
        high = plot_data['high'] * scale if mean is not None or plot_data.get('absolute') else plot_data['high']
        title = (
            '平均打出伤害'
            if plot_data.get('raw')
            else '平均实际扣除'
            if plot_data.get('absolute')
            else '平均打出伤害'
        )
        summary_text = (
            (f'{title}  {mean:,.2f}' if mean is not None else '平均伤害  待填写基础伤害')
            + f"\n伤害浮动区间（中央 90%）  {plot_data['low'] * scale:,.2f} – {plot_data['high'] * scale:,.2f}"
        )
        if detail:
            extra = f"\n破坏率（无浮动基准）：{inputs.destruction:g}% → {detail['final']:g}% · 已逐段计算"
            if detail.get('segmented') and detail.get('remaining_hp') == 0:
                extra += '；预测击杀后仍计后续伤害与破坏率增长'
            summary_text += extra
    else:
        summary_text = '暂无法生成完整结果：' + prob_summary

    destruction_start = inputs.destruction if inputs is not None else None
    destruction_end = detail['final'] if detail is not None else destruction_start
    damage_val = result['damage'] if (ok and result is not None) else None
    raw_damage_val = (
        detail['raw_damage']
        if (ok and detail is not None and detail.get('segmented'))
        else damage_val
    )

    return dict(
        ok=ok,
        errors=errors,
        damage=damage_val,
        raw_damage=raw_damage_val,
        mean=mean,
        low=low,
        high=high,
        destruction_start=destruction_start,
        destruction_end=destruction_end,
        kill_probability=kill_probability,
        result=result,
        detail=detail,
        plot_data=plot_data,
        plot_damage=plot_damage,
        summary_text=summary_text,
        prob_summary=prob_summary,
        detail_text=detail_text,
        destruction_report=destruction_report,
        calculation_status=calculation_status,
        updated_values=updated_values,
        updated_params=updated_params,
        hit_weights_str=hit_weights_str,
        chain_dirty=chain_dirty,
        sequence_candidate=candidate,
        notes=[result['note']] if (ok and result and result.get('note')) else [],
    )


def sequence_add(sequence, prepared, calc_result, skill_title=None):
    """Append the current calculation result to a :class:`DamageSequence`."""
    if not prepared or 'pending_context' not in prepared:
        raise ValueError('请先自动填充角色与敌人，并使用自动跨 DP/HP')
    player, enemy, *_ = prepared['pending_context']
    candidate = (calc_result or {}).get('sequence_candidate')
    if candidate is None:
        raise ValueError('需成功完成自动跨 DP/HP 逐段试算，才可预添加结果')
    title = skill_title if skill_title is not None else prepared.get('skill_title', '')
    step = sequence.append(
        player.get('actor_id'),
        player.get('actor') or player.get('name') or '角色',
        title,
        enemy.get('address'),
        candidate,
    )
    return dict(
        step=step,
        steps=list(sequence.steps),
        current=sequence.current,
        message='本步已冻结。选择下一位角色并自动填充，将继承上述终值；概率图只表示当前技能，不代表整轮联合分布。',
    )


def sequence_undo(sequence):
    """Undo the last step in a :class:`DamageSequence`."""
    sequence.undo()
    return dict(
        steps=list(sequence.steps),
        current=sequence.current,
        message='已撤销并重新填充当前角色。',
    )


def sequence_clear(sequence):
    """Clear all steps in a :class:`DamageSequence`."""
    sequence.clear()
    return dict(
        steps=[],
        current=None,
        message='已清空伤害步骤及预添加效果，恢复当前实战快照。',
    )


def format_raw_inspection(snapshot, fill_notes='尚未自动填充'):
    """Format the audit and raw snapshot texts for inspection views."""
    audit = audit_text(snapshot.get('players', []))
    lines = [
        fill_notes,
        '\n已连接战斗' if snapshot.get('connected') else '\n未连接：如有数据，属于保留快照',
    ]
    for player in snapshot.get('players', []):
        inputs = player.get('inputs', player.get('combat_inputs', {}))
        skill = inputs.get('selected_skill', {})
        lines.append('\n' + str(player.get('name') or '角色') + ' · ' + str(skill.get('name') or '预选未读到'))
        lines.append(' / '.join(f'{STATS[k]} {v}' for k, v in inputs.get('stats', {}).items()))
        lines.append('Token：' + str(inputs.get('token', '未读到')))
    for enemy in snapshot.get('enemies', []):
        inputs = enemy.get('inputs', enemy.get('combat_inputs', {}))
        lines.append(
            '\n'
            + str(enemy.get('name') or '敌人')
            + ' · 边界参考 '
            + str(inputs.get('_borderRefParam', '未读到'))
            + ' / 防御参考 '
            + str(inputs.get('_defenseRefParam', '未读到'))
        )
    lines.append('\n以下为技能威力、偏向权重及条件原始参数（未自动代入）：\n')
    return audit, '\n'.join(lines)
