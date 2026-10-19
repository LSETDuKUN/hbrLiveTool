"""Observed shield stages; Turn, not command/extra/OD, resets Amon's lock."""
import time


class ShieldLayers:
    def __init__(self):
        self.states={}

    def update(self,address,label,live,bars,context,now=None):
        layers=[b.get('v') for b in (bars or {}).get('main',[]) if b.get('kind')=='dp']
        if len(layers)<2:return None
        index=live.get('dp_index');turn=(context or {}).get('turn')
        if not isinstance(index,int) or not 0<=index<=len(layers):return None
        if index==len(layers) and live['dp']>0:return None
        broken=min(len(layers),index+int(live['dp']==0))
        now=time.monotonic() if now is None else now
        old=self.states.get(address)
        count=0 if broken==0 and turn is not None else None
        if old and old['turn']==turn and turn is not None and broken>=old['broken']:
            delta=broken-old['broken']
            count=old['count']+delta if old['count'] is not None else (delta if delta else None)
        elif old and turn is not None and old['turn'] is not None and turn>old['turn'] and now-old['time']<=.6 and broken==old['broken']:
            count=0
        # A long sampling gap can span unseen turns or a new encounter.
        if old and now-old['time']>.6 and broken>0:count=None
        locked=None if count is None else count>0
        known_rule=label.startswith('BigotryGateAmon')
        result=dict(total=len(layers),index=index,broken=broken,remaining=max(0,len(layers)-broken),
                    turn=turn,breaks_this_turn=count,locked=locked if known_rule else None,
                    limit_per_turn=1 if known_rule else None,
                    next_dp=layers[index+1] if index+1<len(layers) else None,
                    source='runtime_index_and_observation',capacity_source='catalog',
                    complete=count is not None)
        self.states[address]=dict(turn=turn,broken=broken,count=count,time=now)
        return result


def shield_text(shield):
    if not shield:return ''
    text=f"盾 {shield['remaining']}/{shield['total']} · 已破 {shield['broken']}"
    if shield['remaining']==0:return text+' · HP 阶段'
    if shield.get('limit_per_turn')==1:
        text+=' · 本 Turn '+('破盾记录未知' if shield.get('locked') is None else '已破盾，锁至 1 DP' if shield['locked'] else '尚可破 1 层')
    return text
