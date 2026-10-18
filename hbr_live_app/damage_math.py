"""Explicit-input multiplier sandbox, not an automatic battle forecast.

Inputs are already-effective percentages. Selection/stacking and conditional
skill formulas must be resolved by the caller; missing base damage stays missing.
"""
import math
from dataclasses import dataclass


def enemy_attribute_reduction(params, critical=False):
    """Calamities compete with critical's damage-only reduction, never add."""
    reductions=[50 if critical else 0]
    for key in ('calamity', 'fear_of_devil'):
        value=float(params.get(key,0))
        if not math.isfinite(value) or value<0:raise ValueError('敌方属性下降必须为有限非负数')
        reductions.append(value)
    return max(reductions)


def skill_base(params, critical=True):
    """Reference calculator interpolation, using explicit min/max and weights."""
    from .damage_autofill import WEIGHTS
    def number(key):
        value=float(params[key])
        if not math.isfinite(value) or value<0:raise ValueError('技能参数必须为有限非负数：'+key)
        return value
    weights={k:number('weight_'+k) for k in WEIGHTS}
    total=sum(weights.values())
    if total<=0:raise ValueError('技能偏向权重尚未确认')
    weighted=sum(number(k)*v for k,v in weights.items() if v)/total
    lo,hi=number('min_power'),number('max_power')
    level,orb,border=number('level'),number('orb'),number('difference')
    if border<=0 or level<1 or hi<lo:raise ValueError('技能等级、威力或差值不适用基础公式')
    if orb>5:raise ValueError('宝珠等级请输入 0–5')
    low=lo*(1+number('growth_min')*(level-1));high=hi*(1+number('growth_max')*(level-1))
    morale=float(params.get('morale_level',0))
    if not math.isfinite(morale) or not 0<=morale<=10:raise ValueError('士气等级请输入 0–10')
    weighted += morale*5
    diff=weighted+enemy_attribute_reduction(params,critical)-number('enemy')
    current=high if diff>=border else low+(high-low)*diff/border if diff>=0 else max(0,(diff+border)/border)*low
    if diff-border>=orb*20:orb_power=hi*.02*orb
    elif diff>=0:orb_power=(lo+(hi-lo)*diff/(border+orb*20))*.02*orb
    else:orb_power=max(0,(diff+border+orb*20)/(border+orb*20))*lo*.02*orb
    over=current*.0025*max(0,diff-border)
    result=max(1,current+orb_power+over)
    if not math.isfinite(result):raise ValueError('基础伤害计算溢出')
    return result,weighted


@dataclass
class DamageInputs:
    base: float | None = None
    attack: float = 0
    element_attack: float = 0
    field: float = 0
    mind_eye: float = 0
    servant_mind_eye: float = 0
    defense_down: float = 0
    element_defense_down: float = 0
    fragile: float = 0
    weapon_bonus: float = 0
    element_bonus: float = 0
    weakness_deepen: float = 0
    resistance: float = 0
    critical: bool = True
    critical_bonus: float = 50
    element_critical_bonus: float = 0
    charge: float = 0
    chain: float = 0
    destruction: float = 100
    od: float = 1
    token_bonus: float = 0
    dp_bonus: float = 0
    hp_bonus: float = 0
    target_pool: str = 'hp'
    health_factor: float = 1
    down_factor: float = 1
    other_factor: float = 1
    penetration_critical: bool = False
    absorbed: bool = False


def calculate(i: DamageInputs):
    for key, value in vars(i).items():
        if isinstance(value, bool) or key == 'target_pool' or value is None:
            continue
        if not isinstance(value, (float, int)) or not math.isfinite(value):
            raise ValueError('所有数值必须为有限数字')
        if value < 0:
            raise ValueError('本实验计算器仅接受非负增益；抗性请填入抗性栏')
    if not 0 <= i.resistance <= 100:
        raise ValueError('抗性请输入 0–100%；吸收使用独立选项')
    if i.target_pool not in ('dp', 'hp'):
        raise ValueError('请选择 DP 或 HP')
    affinity = ((1+i.weapon_bonus/100) * (1+(i.element_bonus+i.weakness_deepen)/100)
                * (1-i.resistance/100))
    weak = not i.absorbed and (affinity > 1 or (i.penetration_critical and i.critical))
    factors = dict(
        attack=1+(i.attack+i.element_attack+i.field+i.charge+(i.mind_eye+i.servant_mind_eye if weak else 0))/100,
        defense=1+(i.defense_down+i.element_defense_down+(i.fragile if weak else 0))/100,
        affinity=affinity,
        critical=1+(i.critical_bonus+i.element_critical_bonus)/100 if i.critical else 1,
        chain=1+i.chain/100, destruction=i.destruction/100 if i.target_pool=='hp' else 1, od=i.od,
        token=1+i.token_bonus/100,
        specialization=1+(i.dp_bonus if i.target_pool == 'dp' else i.hp_bonus)/100,
        health=i.health_factor, down=i.down_factor, other=i.other_factor)
    multiplier = math.prod(factors.values())
    if not math.isfinite(multiplier):
        raise ValueError('乘区数值过大，无法计算')
    # Absorption needs its own recovery rules; do not present positive damage.
    damage = None if i.base is None or i.absorbed else i.base*multiplier
    if damage is not None and not math.isfinite(damage):
        raise ValueError('伤害数值过大，无法计算')
    return dict(weak=weak, affinity=affinity, factors=factors,
                multiplier=None if i.absorbed else multiplier, damage=damage,
                minimum=None if damage is None else damage*.9,
                maximum=None if damage is None else damage*1.1,
                note='吸收：不计算伤害或回复量' if i.absorbed else
                     '参数试算，未完整模拟逐 Hit、破盾、预施加效果或伤害衰减')
