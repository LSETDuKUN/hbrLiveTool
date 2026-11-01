"""Match explicit hbr.quest growth_abi, never infer from combat role."""
import json
import sqlite3
from functools import lru_cache

@lru_cache(maxsize=512)
def style_record(label):
    if not label:return {}
    from hbr_data.store import Catalog
    try:
        _,rows,_=Catalog().query("SELECT raw_json FROM styles WHERE region='cn' AND label=?",(label,),limit=2)
        return json.loads(rows[0][0]) if len(rows)==1 else {}
    except (OSError,ValueError,sqlite3.Error):return {}

def enabled(player,kind,effect_type=None):
    orb=style_record(player.get('style_label','')).get('growth_abi') or {}
    label=orb.get('l')
    if kind=='damage':return label=='AttackUp'
    if kind=='debuff':return label=='DebuffUp' and effect_type in ('DefenseDown','Fragile')
    if kind=='buff':
        return (label=='BuffUp' and effect_type in ('AttackUp','AttackUpIncludeNormal')) or (label=='CriticalRateUp' and effect_type=='CriticalRateUp')
    return False
