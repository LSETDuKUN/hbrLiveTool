"""Build a battle-shaped snapshot from a saved team and a user-described enemy.

The damage calculator only consumes snapshots, so an offline session is just a
synthetic snapshot: team members become players, the enemy is entered by the
user, and buffs/debuffs are explicit user-added statuses. Nothing here reads
game memory or guesses values that were not entered or saved.
"""
import copy

ELEMENTS = (('', '无属性'), ('Fire', '火'), ('Ice', '冰'), ('Thunder', '雷'), ('Light', '光'), ('Dark', '暗'))
WEAPONS = (('Slash', '斩'), ('Stab', '突'), ('Strike', '打'))
RESIST_KEYS = tuple(key for key, _ in WEAPONS) + tuple(key for key, _ in ELEMENTS if key)
ELEMENT_NAMES = dict(ELEMENTS + WEAPONS)

# kind -> (title, side, value encoding). Encodings mirror what damage_autofill
# reads from live statuses so stacking/competition rules apply unchanged.
STATUS_KINDS = {
    'AttackUp': ('攻击力提升 %', 'player', 'amount'),
    'MindEye': ('心眼 %', 'player', 'rate'),
    'CriticalDamageUp': ('暴击伤害提升 %', 'player', 'rate'),
    'CriticalRateUp': ('暴击率提升 %', 'player', 'rate'),
    'DamageRateUp': ('破坏率提升 %', 'player', 'rate'),
    'BuffCharge': ('充能 %', 'player', 'amount'),
    'Funnel': ('连击（每颗 %）', 'player', 'funnel'),
    'Morale': ('士气（层数）', 'player', 'count'),
    'DefenseDown': ('防御力下降 %', 'enemy', 'amount'),
    'Fragile': ('脆弱 %', 'enemy', 'rate'),
    'ResistDown': ('属性抗性下降 / 弱点加深 %', 'enemy', 'resist'),
}
KIND_TITLES = {kind: info[0] for kind, info in STATUS_KINDS.items()}
ALL_MEMBERS = 'all'
ENEMY = 'enemy'
ENEMY_ADDRESS = 'offline-enemy'


def member_id(index):
    return f'offline-{index}'


def manual_status(kind, value, element='', count=None, serial=0, permanent=False):
    """One user-entered status in the same shape the memory reader produces."""
    if kind not in STATUS_KINDS:
        raise ValueError('不支持的效果类型')
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError('请输入数值') from None
    if value < 0:
        raise ValueError('请输入非负数值')
    title, side, encoding = STATUS_KINDS[kind]
    scaled = round(value * 100)
    values = {}
    if encoding == 'amount':
        sign = -1 if kind == 'DefenseDown' else 1
        values = dict(amountOnDpDamageInt=sign * scaled, amountOnHpDamageInt=sign * scaled)
    elif encoding == 'rate':
        values = dict(rateValueInt=scaled)
    elif encoding == 'resist':
        if not element:
            raise ValueError('属性抗性下降需要选择属性')
        values = dict(rateValueInt=-scaled)
    elif encoding == 'funnel':
        try:
            count = int(count)
        except (TypeError, ValueError):
            raise ValueError('连击需要填写颗数') from None
        if not 0 < count <= 100:
            raise ValueError('连击颗数应为 1–100')
        values = dict(rateValueInt=scaled, numValue=count)
    elif encoding == 'count':
        if value != int(value):
            raise ValueError('士气层数应为整数')
        values = dict(numValue=int(value))
    label_element = ELEMENT_NAMES.get(element, '')
    name = (label_element + ' ' if label_element else '') + title.split(' ')[0]
    return dict(label='SpecialStatus.' + kind, name=name, source=f'Manual.{serial}',
                source_name='手动添加：' + name, element_key=element or None, element_type=0,
                duration_kind='permanent' if permanent else 'turn', remaining=None if permanent else 1,
                buff_limit_type=0, values=values, manual=True)


def describe_status(status):
    v = status.get('values', {})
    kind = status['label'].removeprefix('SpecialStatus.')
    if kind == 'Funnel':
        amount = f"{v['numValue']} 颗 × {v['rateValueInt'] / 100:g}%"
    elif kind == 'Morale':
        amount = f"{v['numValue']} 层"
    elif 'rateValueInt' in v:
        amount = f"{abs(v['rateValueInt']) / 100:g}%"
    else:
        amount = f"{abs(v['amountOnDpDamageInt']) / 100:g}%"
    return f"{status.get('name')} {amount}" + ('（常驻）' if status.get('duration_kind') == 'permanent' else '')


def resistance_from_rate(rate):
    """Game-facing damage rate % (150 weak, 50 resist) -> catalog encoding."""
    rate = float(rate)
    return 100 - rate


def manual_enemy(name='自定义敌人', dp=0, hp=1, defense=None, damage_rate=100,
                 destruction_coefficient=None, destruction_max=None, rates=None, down=0,
                 statuses=()):
    for label, value in (('DP', dp), ('HP', hp)):
        if not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f'{label} 应为非负数')
    if dp == 0 and hp == 0:
        raise ValueError('DP 与 HP 不能同时为 0')
    if not isinstance(damage_rate, (int, float)) or damage_rate < 100:
        raise ValueError('当前破坏率应不低于 100%')
    resistances = {}
    for key, rate in (rates or {}).items():
        if rate is None:
            continue
        resistances[key.lower()] = resistance_from_rate(rate)
    progress = dict(damage_rate=damage_rate, down=down)
    if destruction_coefficient is not None:
        progress['destruction_coefficient'] = destruction_coefficient
    if destruction_max is not None:
        progress['destruction_max'] = destruction_max
    inputs = {} if defense is None else {'_defenseRefParam': defense}
    return dict(address=ENEMY_ADDRESS, name=name or '自定义敌人', active=True,
                dp=dp, hp=hp, dp_max=dp, hp_max=hp, base_resistances=resistances,
                enemy_progress=progress, statuses=list(statuses), statuses_available=True,
                combat_inputs=inputs, inputs=inputs)


def team_players(payload, skill_choices=None, statuses=None):
    """Turn saved members into live-shaped players with a chosen skill each.

    skill_choices maps member index -> skill index (into member['skills']).
    statuses maps member index -> list of manual statuses.
    """
    skill_choices = skill_choices or {}
    statuses = statuses or {}
    players = []
    for index, member in enumerate(payload.get('members', [])):
        skills = [dict(s) for s in member.get('skills', []) if s.get('label')]
        choice = skill_choices.get(index, 0)
        selected = copy.deepcopy(skills[choice]) if 0 <= choice < len(skills) else {}
        if selected:
            selected.setdefault('parts', [])
        audit = copy.deepcopy(member.get('passives', []))
        inputs = dict(stats=copy.deepcopy(member.get('stats', {})), equipped_skills=skills,
                      selected_skill=selected, passive_audit=audit,
                      passive_labels=[p['label'] for p in audit if p.get('label')])
        position = member.get('position')
        if not isinstance(position, int):
            position = index
        players.append(dict(actor_id=member_id(index), actor=member.get('actor'),
                            name=member.get('actor') or member.get('style_name') or member.get('style_label'),
                            style_label=member.get('style_label'), style_name=member.get('style_name'),
                            actor_position=position, dp=member.get('dp'), hp=member.get('hp'),
                            dp_max=member.get('dp_max'), hp_max=member.get('hp_max'),
                            statuses=list(statuses.get(index, [])), statuses_available=True,
                            combat_inputs=inputs, inputs=inputs))
    return players


def zone_state(element, bonus):
    """Field bonus % on top of 100%, encoded as the runtime final coefficient."""
    if not element or bonus in (None, ''):
        return {'statuses': []}
    bonus = float(bonus)
    return {'statuses': [dict(label='SpecialStatus.Zone', name=ELEMENT_NAMES.get(element, element) + '场地',
                              element_key=element, element_type=0, duration_kind='turn', remaining=1,
                              values=dict(rateValueInt=round((100 + bonus) * 100)))]}


def snapshot(team_key, payload, enemy, skill_choices=None, statuses=None, field=None,
             od_level=0, revision=0):
    from hbr_live_core.snapshot import stamp
    players = team_players(payload, skill_choices, statuses)
    return stamp(dict(connected=True, offline=True, run_id=f'offline:{team_key}', execution_revision=revision,
                turn_context=dict(selecting=True, turn=None), players=players,
                enemies=[enemy] if enemy else [], field_state=field or {'statuses': []},
                element_gauge=dict(full=False), od_state=dict(available=True, active=od_level > 0,
                                                              level=od_level or None)))
