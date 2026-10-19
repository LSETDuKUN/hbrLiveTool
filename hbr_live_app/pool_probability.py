"""Mixture over the first shield-breaking hit, using independent uniform hits.

K depends only on the prefix uniforms. Conditional on K, suffix uniforms remain
independent: shield overflow is discarded, so prefix damage contributes exactly
the shield amount. No Monte Carlo or normal approximation is required.
"""
import math
from .damage_probability import distribution


def law(weights):
    total=sum(weights)
    if total<=0:
        return lambda x: float(x>=0),0.,0.
    d=distribution(weights);left=d['x'][0]-d['step']/2
    prefix=[0.]
    for y in d['density']:prefix.append(prefix[-1]+y*d['step'])
    def raw_cdf(x):
        pos=(x/total-left)/d['step'];i=int(pos)
        if i<0:return 0.
        if i>=len(d['density']):return 1.
        return min(1.,max(0.,prefix[i]+(pos-i)*d['density'][i]*d['step']))
    # Grid cells straddle true support edges. Renormalize the truncated grid
    # instead of introducing tiny CDF jumps that lose mass after translation.
    start,end=raw_cdf(.9*total),raw_cdf(1.1*total)
    def cdf(x):
        if x<=.9*total:return 0.
        if x>=1.1*total:return 1.
        return min(1.,max(0.,(raw_cdf(x)-start)/(end-start)))
    return cdf,.9*total,1.1*total


def pool_distribution(detail, bins=512):
    """Distribution of effective DP+HP loss, with capped-HP point masses."""
    if not isinstance(bins,int) or not 16<=bins<=8192:
        raise ValueError('概率绘图网格数须为 16–8192 的整数')
    weights=[r['weight'] for r in detail['rows']]
    increments=detail['potential_increments']
    dp,hp=detail['initial_dp'],detail['initial_hp']
    bases=detail['bases'];initial=detail['initial'];maximum=detail['maximum']
    branches=[];components=[];atoms={}
    def atom(x,p):
        if p>0:atoms[x]=atoms.get(x,0)+p
    def component(cdf,lo,hi,offset,prob,cap=None):
        if prob<=0:return
        if hi==lo:
            atom(offset+(min(lo,cap) if cap is not None else lo),prob)
            return
        if cap is not None:
            atom(offset+cap,prob*(1-cdf(cap)))
            hi=min(hi,cap)
        if hi>lo:components.append((cdf,lo,hi,offset,prob))
        elif cap is None:atom(offset+lo,prob)
    if hp==0:
        atom(0,1)
    elif detail.get('shield_locked'):
        cdf,lo,hi=law([bases['dp']*w for w in weights])
        component(cdf,lo,hi,0,1.,max(0,dp-1))
        branches.append(dict(hit=None,probability=1.))
    else:
        previous=0. if dp>0 else 1.
        candidates=[(0,1.)] if dp<=0 else []
        prefix=[]
        for k,w in enumerate(weights,1):
            if dp<=0:break
            prefix.append(bases['dp']*w)
            total=sum(prefix)
            if dp>=1.1*total:crossed=0.
            elif dp<=.9*total:crossed=1.
            else:
                cdf,lo,hi=law(prefix)
                crossed=max(previous,1-cdf(dp))
            prob=crossed-previous
            if prob>0:candidates.append((k,prob))
            previous=crossed
            if crossed>=1:break
        if dp>0 and previous<1:
            cdf,lo,hi=law([bases['dp']*w for w in weights])
            # Unconditional prefix density truncated at the shield boundary.
            component(cdf,lo,min(hi,dp),0,1.)
            branches.append(dict(hit=None,probability=1-previous))
        for k,prob in candidates:
            next_dp=detail.get('next_shield_dp')
            if next_dp is not None:
                suffix=[bases['dp']*w for w in weights[k:]]
                cdf,lo,hi=law(suffix)
                branches.append(dict(hit=k,probability=prob))
                if not suffix or hi==0:atom(dp,prob)
                else:component(cdf,lo,hi,dp,prob,max(0,next_dp-1))
                continue
            rate=initial
            if k:rate+=min(increments[k-1],max(0,maximum-rate))
            suffix=[]
            for j in range(k,len(weights)):
                suffix.append(bases['hp']*weights[j]*rate/100)
                rate+=min(increments[j],max(0,maximum-rate))
            branches.append(dict(hit=k,probability=prob))
            cdf,lo,hi=law(suffix)
            if not suffix or hi==0:atom(dp,prob)
            else:component(cdf,lo,hi,dp,prob,hp)
    bounds=[x for x in atoms]+[v+offset for _,lo,hi,offset,_ in components for v in (lo,hi)]
    low,high=min(bounds),max(bounds)
    if high==low:
        padding=max(1,abs(low)*.01);low-=padding;high+=padding
    step=(high-low)/bins
    xs=[low+(i+.5)*step for i in range(bins)];mass=[0.]*bins
    for cdf,lo,hi,offset,prob in components:
        for i in range(bins):
            a=max(lo,low+i*step-offset);b=min(hi,low+(i+1)*step-offset)
            if b>a:mass[i]+=prob*max(0,cdf(b)-cdf(a))
    total=sum(mass)+sum(atoms.values())
    if not math.isclose(total,1,abs_tol=2e-5):raise ValueError('跨池概率质量校验失败')
    def cdf_total(x):
        return sum(p for a,p in atoms.items() if a<=x)+sum(
            p*max(0,cdf(min(hi,x-offset))-cdf(lo)) for cdf,lo,hi,offset,p in components if x-offset>lo)
    def quantile(q):
        a,b=low,high
        for _ in range(60):
            mid=(a+b)/2
            if cdf_total(mid)>=q:b=mid
            else:a=mid
        return b
    # Integrate each component on its own support. A remote narrow branch must
    # not have its mean shifted by a wide plotting bin spanning other modes.
    mean=sum(x*p for x,p in atoms.items())
    for cdf,lo,hi,offset,p in components:
        n=1024;dx=(hi-lo)/n;end=cdf(hi);start=cdf(lo)
        integral=dx*(.5*(cdf(lo)+cdf(hi))+sum(cdf(lo+j*dx) for j in range(1,n)))
        mean+=p*(offset*(end-start)+hi*end-lo*start-integral)
    return dict(x=xs,density=[p/step for p in mass],step=step,low=quantile(.05),high=quantile(.95),
                mean=mean,
                atoms=sorted(atoms.items()),branches=branches,domain=(low,high),absolute=True,
                kill_probability=(0. if detail.get('shield_locked') or detail.get('next_shield_dp') is not None else atoms.get(dp+hp,0)) if hp is not None and hp>0 else None,
                hits=len(weights),mass=total)
