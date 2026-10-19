"""Explicit all-SP scaling; observed preview fields are not authoritative costs."""
import math


def sp_factor(consumed, cap):
    try:
        consumed, cap = float(consumed), float(cap)
    except (TypeError, ValueError):
        raise ValueError('请填写预计消耗 SP 和效果封顶 SP') from None
    if not all(math.isfinite(v) and v > 0 for v in (consumed, cap)):
        raise ValueError('全 SP 技能需要正数 SP；0 SP 无法发动')
    return min(consumed, cap) / cap
