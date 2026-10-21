"""Raw hit totals, including shield overflow, under random pool transitions.

Unlike effective loss, the breaking prefix cannot be replaced by shield HP.
Seeded sampling retains that conditional prefix and the resulting correlations.
"""
import random
import math


def raw_distribution(detail, samples=65536, seed=73021):
    rng=random.Random(seed)
    weights=[r['weight'] for r in detail['rows']]
    increments=detail['potential_increments']
    bases=detail['bases']
    totals=[]
    for _ in range(samples):
        dp=detail['initial_dp'];hp=detail['initial_hp']
        rate=detail['initial'];maximum=detail['maximum']
        locked=detail.get('shield_locked',False);next_dp=detail.get('next_shield_dp')
        total=0.
        for weight,increment in zip(weights,increments):
            if hp is not None and hp<=0:break
            pool='dp' if dp>0 else 'hp'
            raw=bases[pool]*weight*(rate/100 if pool=='hp' else 1)*rng.uniform(.9,1.1)
            total+=raw
            if pool=='dp':
                dp-=min(max(0,dp-(1 if locked else 0)),raw)
                if dp<=0 and next_dp is not None:
                    dp=next_dp;next_dp=None;locked=True
            elif hp is not None:
                hp-=min(hp,raw)
            if dp<=0:rate+=min(increment,max(0,maximum-rate))
        totals.append(total)
    totals.sort()
    mean=sum(totals)/samples
    lo,hi=totals[0],totals[-1]
    atoms=[]
    if lo==hi:
        atoms=[(lo,1.)]
        pad=max(1,abs(lo)*.01);lo-=pad;hi+=pad
    bins=128;step=(hi-lo)/bins;counts=[0]*bins
    if not atoms:
        for value in totals:counts[min(bins-1,int((value-lo)/step))]+=1
    variance=sum((v-mean)**2 for v in totals)/samples
    return dict(x=[lo+(i+.5)*step for i in range(bins)],
                density=[n/samples/step for n in counts],step=step,
                low=totals[int(.05*(samples-1))],high=totals[int(.95*(samples-1))],
                mean=mean,atoms=atoms,domain=(lo,hi),absolute=True,hits=len(weights),
                samples=samples,mean_error=math.sqrt(variance/samples),raw=True)
