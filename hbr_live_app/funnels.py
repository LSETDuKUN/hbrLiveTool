"""Keep bead count and per-bead damage weights visible and editable."""
from collections import Counter
import math
import re


def describe(weights):
    return ' + '.join(f'{count} × {weight*100:g}%' for weight,count in Counter(weights).items()) or '0 × 25%'


def parse(text):
    result=[]
    for item in text.split('+'):
        match=re.fullmatch(r'\s*(\d+)\s*[xX*×]\s*([\d.]+)\s*%?\s*',item)
        if not match:raise ValueError('连击珠请填“3 × 25%”，不同倍率用 + 分隔')
        count=int(match[1]);rate=float(match[2])
        if count>100 or not math.isfinite(rate) or not 0<=rate<=1000:raise ValueError('连击珠颗数或倍率超出支持范围')
        result.extend([rate/100]*count)
    if len(result)>100:raise ValueError('连击珠总颗数不能超过 100')
    return result
