"""Inspectable single-effect preview; does not mutate battle state or stack effects."""
import math
from dataclasses import dataclass


@dataclass
class EffectInputs:
    kind: str = 'buff'
    minimum: float = 0
    maximum: float = 0
    threshold: float = 1
    attribute: float = 0
    enemy: float = 0
    level: float = 1
    growth_min: float = 0
    growth_max: float = 0
    orb: float = 0
    enhancement: float = 0
    reduction: float = 0
    over_rate: float = .0002


def calculate_effect(i):
    for key,value in vars(i).items():
        if key=='kind':continue
        if not math.isfinite(value) or value<0:raise ValueError('效果量参数必须为有限非负数')
    if i.level!=int(i.level):
        raise ValueError('请核对效果类型与技能等级')
    if i.kind not in ('buff','debuff','fixed') or i.level<1 or not 0<=i.orb<=5:
        raise ValueError('请核对效果类型、等级及宝珠等级 0–5')
    if i.kind=='fixed':
        base=i.minimum*(1+i.growth_min*(i.level-1));orb=over=0;difference=None
    else:
        if i.threshold<=0 or i.maximum<i.minimum:raise ValueError('变动效果需要正差值阈值及有效上下限')
        low=i.minimum*(1+i.growth_min*(i.level-1));high=i.maximum*(1+i.growth_max*(i.level-1))
        if high<low:raise ValueError('等级成长后上限低于下限，请核对成长参数')
        difference=i.attribute-(max(0,i.enemy-i.reduction) if i.kind=='debuff' else 0)
        ratio=min(1,max(0,difference/i.threshold))
        base=low+(high-low)*ratio
        # Use supplied source bounds rather than the reference UI's zero-stat sentinel.
        orb_ratio=min(1,max(0,difference/(i.threshold+100)))
        orb=(i.minimum+(i.maximum-i.minimum)*orb_ratio)*i.orb*(.04 if i.kind=='buff' else .02)
        over=high*max(0,difference-i.threshold)*i.over_rate
    final=(base+orb+over)*(1+i.enhancement/100)
    if not math.isfinite(final):raise ValueError('效果量计算溢出')
    return dict(base=base,orb=orb,over=over,enhancement=i.enhancement,final=final,difference=difference)
