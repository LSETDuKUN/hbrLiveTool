"""Independent weighted U(.9, 1.1) hits, as in hbrtoolbox's float model.

Numerical convolution, not copied reference implementation. Fixed grid and
prefix integrals keep work bounded and avoid cancellation of spline sums.
Weights describe final per-hit damage with all other factors held constant.
"""
import math
from functools import lru_cache


def distribution(weights):
    weights=tuple(float(w) for w in weights)
    if not weights or len(weights)>256 or any(not math.isfinite(w) or w<=0 for w in weights):
        raise ValueError('请提供 1–256 个有限正数作为各 Hit 伤害权重')
    total=sum(weights)
    if not math.isfinite(total):raise ValueError('Hit 权重合计过大')
    return _distribution(tuple(sorted((w/total for w in weights),reverse=True)))


@lru_cache(maxsize=16)
def _distribution(weights):
    n=4096;left=-.11;step=.22/n
    xs=[left+(i+.5)*step for i in range(n)]
    half=.1*weights[0]
    density=[max(0,min(x+step/2,half)-max(x-step/2,-half))/(2*half*step) for x in xs]
    for weight in weights[1:]:
        half=.1*weight
        # Negligible kernels below grid precision are effectively a point mass.
        if half<step*1e-3:continue
        prefix=[0.]
        for y in density:prefix.append(prefix[-1]+y*step)
        def cdf(x):
            position=(x-left)/step
            if position<=0:return 0.
            if position>=n:return prefix[-1]
            idx=int(position)
            return prefix[idx]+(position-idx)*density[idx]*step
        density=[max(0,(cdf(x+half)-cdf(x-half))/(2*half)) for x in xs]
    area=sum(density)*step
    density=[v/area for v in density]
    def quantile(q):
        accum=0.
        for x,y in zip(xs,density):
            mass=y*step
            if mass and accum+mass>=q:return 1+x-step/2+step*(q-accum)/mass
            accum+=mass
        return 1.1
    return dict(x=tuple(1+x for x in xs),density=tuple(density),step=step,
                low=quantile(.05),high=quantile(.95),
                sigma=math.sqrt(sum(w*w for w in weights)/300),hits=len(weights))
