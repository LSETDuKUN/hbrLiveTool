"""Raw damage via conditional first-break prefixes and independent HP suffixes.

Each branch retains the actual random breaking prefix, including overflow.
HP suffix laws retain every hit and its destruction growth after lethal damage.
All branches use deterministic numerical convolution, never histogram sampling.
"""
import math
from .damage_probability import distribution
from .probability_grid import advance, split, add, convolve


def fixed(amounts):
    amounts=[v for v in amounts if v>0];total=sum(amounts)
    if not amounts:
        return dict(x=[-1.,0.,1.],density=[0.,0.,0.],step=1,low=0.,high=0.,mean=0.,atoms=[(0.,1.)],domain=(-1,1),absolute=True,raw=True,method='convolution',hits=0,mass=1.)
    d=distribution(amounts)
    return dict(x=[x*total for x in d['x']],density=[p/total for p in d['density']],
                step=d['step']*total,low=d['low']*total,high=d['high']*total,
                mean=total,atoms=[],domain=(.9*total,1.1*total),absolute=True,raw=True,
                method='convolution',hits=len(amounts),mass=1.)


def raw_distribution(detail,bins=4096):
    if not isinstance(bins,int) or not 256<=bins<=16384:raise ValueError('跨池概率网格须为 256–16384')
    weights=[r['weight'] for r in detail['rows']];inc=detail['potential_increments']
    dp=detail['initial_dp'];bases=detail['bases']
    initial,maximum=detail['initial'],detail['maximum']
    dp_amounts=[bases['dp']*w for w in weights]
    # A final-hit break changes no raw hit coefficient. Locked shields likewise
    # keep all attacks in DP, regardless of the actual loss cap.
    if dp>0 and (detail.get('shield_locked') or detail.get('next_shield_dp') is not None or
                 1.1*sum(dp_amounts[:-1])<=dp):
        return fixed(dp_amounts)
    def suffix(k):
        rate=initial
        if k:rate+=min(inc[k-1],max(0,maximum-rate))
        result=[]
        for j in range(k,len(weights)):
            result.append(bases['hp']*weights[j]*rate/100)
            rate+=min(inc[j],max(0,maximum-rate))
        return result
    def suffix_law(k,step):
        mass=[1.]
        for amount in suffix(k):mass=advance(mass,amount,step)
        return mass
    if dp<=0:
        amounts=suffix(0)
        return fixed(amounts)
    upper=1.1*sum(weights)*max(bases['dp'],bases['hp']*max(initial,maximum)/100)
    if upper==0:return fixed([])
    step=upper/bins
    alive=[1.];mass=[]
    for k,amount in enumerate(dp_amounts,1):
        alive=advance(alive,amount,step)
        alive,crossed=split(alive,dp,step)
        if sum(crossed)>1e-14:
            tail=suffix_law(k,step)
            add(mass,convolve(crossed,tail) if len(tail)>1 else [p*tail[0] for p in crossed])
        if sum(alive)<1e-14:break
    add(mass,alive)
    area=sum(mass)
    if not math.isclose(area,1,abs_tol=1e-6):raise ValueError('打出伤害概率质量校验失败')
    mass=[p/area for p in mass]
    def quantile(q):
        accum=0.
        for i,p in enumerate(mass):
            if p and accum+p>=q:return (i-.5+(q-accum)/p)*step
            accum+=p
        return (len(mass)-1)*step
    support=[i for i,p in enumerate(mass) if p>1e-12]
    a=max(0,min(support)-1);b=min(len(mass),max(support)+2)
    return dict(x=[i*step for i in range(a,b)],density=[p/step for p in mass[a:b]],step=step,
                low=quantile(.05),high=quantile(.95),mean=sum(i*step*p for i,p in enumerate(mass)),
                atoms=[],domain=(a*step,(b-1)*step),absolute=True,raw=True,
                method='branch_convolution',hits=len(weights),mass=area,grid=bins)
