"""Read actual owned statuses; the manager is shared by allies and enemies."""
import math
import json
import sqlite3
import struct
import time
from .skill_effects import EFFECT_NAMES

TITLES = dict(EFFECT_NAMES, MindEye='心眼', Fragile='脆弱', Funnel='连击', BuffCharge='充能 / 蓄力',
    ThunderMark='雷之印', FireMark='火之印', IceMark='冰之印',
    CriticalRateUp='暴击率提升', CriticalDamageUp='暴击伤害提升',
    ReduceSp='SP 消耗减少', SpLimitOverwrite='SP 上限',
    SkillLimitCountUp='技能次数增加', AdditionalTurn='追加回合',
    AdditionalElementOnlyNormal='普攻附加属性', ZoneUpEternal='场地强化')
TITLES.update(AttackUpIncludeNormal='加攻（含普攻）', AttackUpOnlyNormal='普攻加攻',
              FearOfDevil='大灾厄', Misfortune='灾厄', BIYamawakiServant='魔界骑兵',
              Zone='场地', RiceFieldZone='稻场', SandStormZone='沙暴场地', ResistUp='抗性提升', ResistDown='抗性降低',
              ResistDownOverwrite='抗性覆盖', CriticalRateDown='暴击率降低', CriticalDamageDown='暴伤降低')
ELEMENT_NAMES = dict(Fire='火', Ice='冰', Thunder='雷', Light='光', Dark='暗', Slash='斩', Stab='突', Strike='打')


def status_value(kind, values):
    """Only decode verified fixed-point fields; retain all other values in details."""
    if kind in ('FearOfDevil','Misfortune'):
        return '全属性 -'+('100' if kind=='FearOfDevil' else '20')+'（同类取最高）'
    if kind=='BIYamawakiServant' and isinstance(values.get('rateValueInt'),int):
        return f'弱点技能增伤 +{values["rateValueInt"]/100:g}%（可与心眼叠加）'
    if kind == 'BuffCharge':
        dp, hp = values.get('amountOnDpDamageInt'), values.get('amountOnHpDamageInt')
        damage = '技能伤害提升（数值待核实）'
        if isinstance(dp, int) and isinstance(hp, int):
            damage = (f'技能伤害 {dp/100:+g}%' if dp == hp else
                      f'技能伤害 DP {dp/100:+g}% / HP {hp/100:+g}%')
        # This class has its own rate scale: observed 200000, not the scale
        # used by CriticalRateSpecialStatus. Do not apply a generic divisor.
        return damage + ' · 暴击率提升（数值待核实）'
    if kind == 'Zone' and isinstance(values.get('rateValueInt'),int):
        return f'{values["rateValueInt"]/100-100:+g}%（系数 {values["rateValueInt"]/10000:g}）'
    if kind in ('ResistDown','ResistUp') and isinstance(values.get('rateValueInt'),int):
        return f'{abs(values["rateValueInt"])/100:g}%'
    if kind in ('RiceFieldZone','SandStormZone','Zone'):
        return ''
    if kind in ('MindEye', 'Fragile', 'CriticalRateUp', 'CriticalDamageUp'):
        n = values.get('rateValueInt')
        if n is not None:
            return f'{n / 100:+g}%'
    if kind in ('AttackUp', 'AttackUpIncludeNormal', 'AttackUpOnlyNormal', 'AttackDown', 'DefenseUp', 'DefenseDown'):
        dp, hp = values.get('amountOnDpDamageInt'), values.get('amountOnHpDamageInt')
        if dp is not None and hp is not None:
            return f'{abs(dp)/100:g}%' if dp == hp else f'DP {abs(dp)/100:g}% / HP {abs(hp)/100:g}%'
    if kind == 'Funnel' and 'numValue' in values and 'rateValueInt' in values:
        return f'{values["numValue"]} Hit · {values["rateValueInt"]/100:g}%'
    if 'numValue' in values:
        return str(values['numValue'])
    return ''


def status_line(s):
    pending = '（预添加）' if s.get('pending_add') else '（预移除）' if s.get('pending_remove') else ''
    return ' '.join(x for x in (s['name'], s.get('value'), pending) if x)


def status_details(state):
    if not state.get('statuses_available'):
        return '状态暂不可读'
    lines = []
    for s in state.get('statuses', []):
        lines.append(status_line(s))
        lines.append('  来源：'+(s.get('source_name') or s.get('source') or '未确认'))
        if s.get('source_name') != s.get('source'):
            lines.append('  技能标识：'+s.get('source', ''))
        if s.get('duration'):
            lines.append('  持续：'+s['duration'])
        if s.get('effective_reason'):
            lines.append('  展示筛选：'+s['effective_reason'])
        lines.append('  原始参数：'+str(s.get('values', {})))
    return '\n'.join(lines) or '未观测到所属状态'


def filter_confirmed_only_funnels(statuses):
    """Observed Only=4; no inference for unverified normal stacking categories.

    Equal effects have interchangeable contribution; keep the longest remaining
    duration for display, not a claim about which instance the engine consumes.
    Permanent and finite effects are never placed in the same competition group.
    """
    groups = {}
    for status in statuses:
        if (status['label'] != 'SpecialStatus.Funnel' or status.get('buff_limit_type') != 4
                or status.get('pending_add') or status.get('pending_remove')):
            continue
        values = status.get('values',{})
        hits, rate = values.get('numValue'),values.get('rateValueInt')
        kind = status.get('duration_kind')
        if kind not in ('turn','count','permanent') or not isinstance(hits,int) or not isinstance(rate,int) or hits<0 or rate<0:
            continue
        key = (kind,status.get('element_type'))
        groups.setdefault(key,[]).append(status)
    for group in groups.values():
        # Different hit counts/rates are not ranked by an unverified damage formula.
        comparable = {}
        for status in group:
            v=status['values']
            comparable.setdefault((v['numValue'],v['rateValueInt']),[]).append(status)
        for duplicates in comparable.values():
            if len(duplicates)<2:continue
            winner=max(duplicates,key=lambda s:s.get('remaining') or 0)
            for status in duplicates:
                if status is winner:continue
                status['effective']=False
                status['effective_reason']='同值单独发动连击珠不重复计入；主面板保留剩余时间较长的一份。此为规则筛选，非游戏生效标记。'
    return statuses


def infer_suppressed_attacks(statuses):
    """Conservative display inference; never remove or consume a stored status.

    Only an exact-kind/element finite Only attack buff can cover a weaker
    finite attack buff. Permanent effects and ambiguous conditions stay separate.
    Recompute on every sample so an expired covering buff releases the old one.
    """
    from .status_rules import independent
    for status in statuses:
        if status.get('effective_basis') in ('attack_only_rule','debuff_top_two_rule'):
            for key in ('effective', 'effective_reason', 'effective_basis'):
                status.pop(key, None)

    def key(s):
        if (independent(s) or s.get('label') not in ('SpecialStatus.AttackUp',
                'SpecialStatus.AttackUpIncludeNormal', 'SpecialStatus.AttackUpOnlyNormal')
                or s.get('duration_kind') not in ('turn', 'count')
                or (s.get('remaining') or 0) <= 0 or s.get('hidden')
                or s.get('pending_add') or s.get('pending_remove')
                or s.get('element_type') is None
                or s.get('source_effect', {}).get('target_condition')):
            return None
        v = s.get('values', {})
        if not all(isinstance(v.get(k), int) and v[k] >= 0
                   for k in ('amountOnDpDamageInt', 'amountOnHpDamageInt')):
            return None
        return s['label'], s['element_type'], s.get('element_key')

    for status in statuses:
        group = key(status)
        if group is None:
            continue
        v = status['values']
        for other in statuses:
            if other is status or other.get('buff_limit_type') != 4 or key(other) != group:
                continue
            w = other['values']
            if all(w[k] > v[k] for k in ('amountOnDpDamageInt', 'amountOnHpDamageInt')):
                status['effective'] = False
                status['effective_basis'] = 'attack_only_rule'
                status['effective_reason'] = ('暂被更强的同类单独发动加攻覆盖（规则推断，非游戏直接标记）；'
                    '原状态及剩余次数保留，覆盖效果结束后重新判断。覆盖来源：'
                    + (other.get('source_name') or other.get('source') or '未确认'))
                break
    groups={}
    for s in statuses:
        if (s.get('label') not in ('SpecialStatus.DefenseDown','SpecialStatus.Fragile')
                or s.get('duration_kind') not in ('turn','count') or (s.get('remaining') or 0)<=0
                or s.get('effective') is False or s.get('pending_add') or s.get('pending_remove')
                or any(s.get('source_effect',{}).get(k) for k in ('condition','target_condition','hit_condition'))):continue
        element=s.get('element_key') or {0:'Normal',1:'Fire',2:'Ice',3:'Thunder',4:'Light',5:'Dark'}.get(s.get('element_type'))
        if element is None:continue
        v=s.get('values',{})
        nums=[v.get('rateValueInt')]*2 if s['label']=='SpecialStatus.Fragile' else [v.get('amountOnDpDamageInt'),v.get('amountOnHpDamageInt')]
        if not all(isinstance(n,(int,float)) for n in nums):continue
        groups.setdefault((s['label'],element),[]).append((s,[abs(n) for n in nums]))
    for group in groups.values():
        winners=set()
        for pool in (0,1):
            regular=sorted((i for i,(s,v) in enumerate(group) if s.get('buff_limit_type')!=4),key=lambda i:group[i][1][pool],reverse=True)[:2]
            only=max((i for i,(s,v) in enumerate(group) if s.get('buff_limit_type')==4),key=lambda i:group[i][1][pool],default=None)
            winners.update([only] if only is not None and group[only][1][pool]>=sum(group[i][1][pool] for i in regular) else regular)
        for i,(s,_) in enumerate(group):
            if i not in winners:
                s.update(effective=False,effective_basis='debuff_top_two_rule',effective_reason='同类有限期减益只取最高两层（规则推断）；永久效果另计，状态保留。')
    return statuses


class StatusReader:
    def __init__(self, runtime):
        self.r = runtime
        self.layouts = {}
        self.names = {}
        self.effects = {}
        self.cache = {}
        self.input_cache = {}
        self.stamp = 0

    def fields(self, address):
        key = self.r.q(address)
        if not key:
            raise ValueError('对象不可读')
        if key not in self.layouts:
            self.layouts[key] = {f['name']: (f['offset'], f['type']) for f in self.r.fields(address)['fields']}
        return self.layouts[key]

    def get(self, address, name, default=None):
        field = self.fields(address).get(name)
        if not field:
            return default
        offset, kind = field
        fmt = {2:'?',8:'i',9:'I',10:'q',11:'Q',12:'f',13:'d'}.get(kind)
        if fmt:
            data = self.r.read(address+offset, struct.calcsize('<'+fmt))
            if len(data) != struct.calcsize('<'+fmt):
                raise ValueError('字段不可读')
            value = struct.unpack('<'+fmt, data)[0]
            return value if not isinstance(value,float) or math.isfinite(value) else default
        if kind == 14:
            return self.r.string(self.r.q(address+offset)) or ''
        if kind in (18,21,28):
            return self.r.q(address+offset)
        return default

    def prop(self, address, name, default=None):
        return self.get(address, '<'+name+'>k__BackingField', default)

    def skill_name(self, label):
        if label not in self.names:
            name = label
            try:
                from hbr_data.store import Catalog
                _, rows, _ = Catalog().query("SELECT DISTINCT name FROM skills WHERE region='cn' AND label=?", (label,), limit=2)
                if len(rows) == 1:
                    name = rows[0][0] or label
            except (OSError, ValueError, RuntimeError, sqlite3.Error):
                pass
            self.names[label] = name
        return self.names[label]

    def source_effect(self,label,kind):
        key=(label,kind)
        if key not in self.effects:
            result={}
            try:
                from hbr_data.store import Catalog
                _,rows,_=Catalog().query("SELECT raw_json FROM skills WHERE region='cn' AND label=?",(label,),limit=30)
                candidates={}
                for row in rows:
                    for part in json.loads(row[0]).get('parts',[]):
                        if part.get('skill_type')==kind:
                            item=dict(elements=part.get('elements',[]), effect=part.get('effect',{}),
                                      target_condition=part.get('target_condition',''),
                                      condition=part.get('cond',''), hit_condition=part.get('hit_condition',''))
                            candidates[json.dumps(item,sort_keys=True)]=item
                if len(candidates)==1:result=next(iter(candidates.values()))
            except (OSError,ValueError,RuntimeError,sqlite3.Error,TypeError,KeyError):
                pass
            self.effects[key]=result
        return self.effects[key]

    def owned(self, actor):
        manager = self.prop(actor, 'specialStatusManager')
        owner = self.prop(actor, 'instanceId')
        if not manager or not owner or self.r.cls(manager) != 'SpecialStatusManager':
            raise ValueError('状态归属不可读')
        self.read_manager(manager)
        return self.cache[manager].get(owner, [])

    def read_manager(self, manager):
        if manager not in self.cache:
            from .source import members
            pointer = self.get(manager, 'specialStatusList')
            if not pointer or self.r.cls(pointer) != 'List`1':
                raise ValueError('状态列表不可读')
            grouped = {}
            for address in members(self.r, pointer):
                target = self.prop(address, 'owner')
                domain = self.prop(address, 'domainSpecialStatus')
                master = self.get(domain, 'master') if domain else None
                label = self.get(master, 'Label', '') if master else ''
                kind = label.removeprefix('SpecialStatus.')
                values = {}
                for field, (_, typ) in self.fields(address).items():
                    if typ in (8,9,12,13) and any(x in field.lower() for x in ('value','amount','power')):
                        values[field.removeprefix('<').removesuffix('>k__BackingField')] = self.get(address, field)
                source = self.prop(address, 'reasonMasterLabel', '')
                source_info = self.source_effect(source,kind)
                elements = source_info.get('elements',[])
                element_key = elements[0] if len(elements)==1 and elements[0] in ELEMENT_NAMES else None
                element_field = self.fields(address).get('<elementType>k__BackingField')
                element_type = self.r.i(address+element_field[0]) if element_field and element_field[1] == 17 else None
                exit_condition = self.prop(address, 'exitCondition')
                limit_field = self.fields(address).get('<buffLimitType>k__BackingField')
                limit_type = self.r.i(address+limit_field[0]) if limit_field and limit_field[1] == 17 else None
                duration = ''
                duration_kind = 'unknown'
                remaining = 0
                if exit_condition and self.r.cls(exit_condition) == 'EternalExitCondition':
                    duration = '永久'
                    duration_kind = 'permanent'
                elif exit_condition and self.r.cls(exit_condition) == 'TurnEndExitCondition':
                    total = self.prop(exit_condition, 'totalTurn')
                    used = self.prop(exit_condition, 'progressedTurn')
                    if isinstance(total,int) and isinstance(used,int):
                        remaining = max(0,total-used)
                        duration = f'剩余 {remaining} 回合'
                        duration_kind = 'turn'
                elif exit_condition:
                    total = self.prop(exit_condition, 'totalCount')
                    used = self.prop(exit_condition, 'usedCount')
                    if isinstance(total,int) and isinstance(used,int):
                        remaining = max(0,total-used)
                        duration = f'剩余计数 {remaining}（消耗规则待核实）'
                        duration_kind = 'count'
                name = TITLES.get(kind, kind or self.r.cls(address))
                if kind == 'Zone' and element_key:
                    name = ELEMENT_NAMES[element_key]+'属性场地'
                if kind == 'ResistDown' and 'IsWeakElement' in source_info.get('target_condition',''):
                    name = '弱点加深'
                grouped.setdefault(target, []).append(dict(label=label, name=name,
                    value=status_value(kind, values), values=values, source=source, source_name=self.skill_name(source),
                    element_type=element_type,
                    element_key=element_key, element_name=ELEMENT_NAMES.get(element_key), source_effect=source_info,
                    buff_limit_type=limit_type, remaining=remaining,
                    duration=duration, duration_kind=duration_kind, hidden=bool(self.prop(address,'isHideIcon',False)),
                    pending_add=bool(self.prop(address,'expectedToAdd',False)),
                    pending_remove=bool(self.prop(address,'expectedToRemove',False))))
            self.cache[manager] = {owner:infer_suppressed_attacks(filter_confirmed_only_funnels(values))
                                   for owner,values in grouped.items()}

    def refresh(self):
        now = time.monotonic()
        if now-self.stamp >= .4:
            self.cache.clear()
            self.input_cache.clear()
            self.stamp = now

    def sample(self, actor, resources=False):
        self.refresh()
        result = {}
        try:
            from .damage_inputs import read_inputs
            if actor not in self.input_cache:
                self.input_cache[actor] = read_inputs(self, actor)
            result['combat_inputs'] = self.input_cache[actor]
        except (ValueError, RuntimeError, TypeError, KeyError):
            result['combat_inputs'] = dict(unavailable=True)
        if resources:
            for pool in ('hp','dp'):
                field = self.fields(actor).get(pool+'Internal')
                if field and field[1] == 17:
                    raw = self.r.read(actor+field[0], 8)
                    if len(raw) == 8:
                        value = struct.unpack('<q', raw)[0]
                        if value >= 0:
                            result[pool] = value
                result[pool+'_max'] = self.prop(actor, 'defaultMax'+pool.capitalize())
                result['expected_'+pool] = self.prop(actor, 'expected'+pool.capitalize())
        try:
            result.update(statuses=self.owned(actor), statuses_available=True)
        except (ValueError, RuntimeError, TypeError, KeyError):
            result.update(statuses=[], statuses_available=False)
        return result

    def sample_fields(self, module):
        self.refresh()
        try:
            manager = self.prop(module, 'specialStatusManager')
            if not manager or self.r.cls(manager) != 'SpecialStatusManager':
                raise ValueError('全局状态不可读')
            self.read_manager(manager)
            fields = [s for s in self.cache[manager].get(0, [])
                      if s['label'] in ('SpecialStatus.Zone','SpecialStatus.RiceFieldZone','SpecialStatus.SandStormZone')]
            return dict(available=True, statuses=fields)
        except (ValueError, RuntimeError, TypeError, KeyError):
            return dict(available=False,statuses=[])

    def element_gauge(self, module):
        try:
            address = self.prop(module, 'elementGaugeManager')
            if not address or self.r.cls(address) != 'BattleElementGaugeManager':
                return None
            value = self.get(address, '_currentPoint')
            maximum = self.get(address, 'maxPoint')
            field = self.fields(address).get('<elementType>k__BackingField')
            element = self.r.i(address+field[0]) if field and field[1] == 17 else None
            if not isinstance(value,int) or not isinstance(maximum,int) or maximum <= 0:
                return None
            return dict(value=value, maximum=maximum, element=element,
                        name='雷' if element == 3 else '元素', full=value >= maximum)
        except (ValueError, RuntimeError, TypeError):
            return None
