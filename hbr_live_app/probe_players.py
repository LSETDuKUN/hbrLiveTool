"""Bounded read-only player state probe for non-command transitions."""
import json,time,traceback
from pathlib import Path
from . import runtime as r
from .source import locate,members,snapshot
from .formation import FormationReader
from .turns import TurnReader
from .windows import game_pid

def inspect(player):
    out={}; queue=[('player',player,0)];seen=set()
    while queue and len(out)<180:
        path,obj,depth=queue.pop(0)
        if obj in seen:continue
        seen.add(obj); d=r.fields(obj);out[path]=d
        for f in d['fields']:
            if f['type']==17:f['raw4']=r.read(obj+f['offset'],4).hex()
        if depth>=4:continue
        if d['class']=='List`1':
            try:queue.extend((path+f'[{i}]',v,depth+1) for i,v in enumerate(members(r,obj)[:24]) if r.cls(v))
            except RuntimeError:pass
        for f in d['fields']:
            child=f.get('object')
            if child and any(s in (f['name']+child['class']).lower() for s in ('special','status','domain','master','style','mode','form','command')):
                queue.append((path+'.'+f['name'],int(child['address'],16),depth+1))
    return out

def main():
    folder=Path(__file__).resolve().parent.parent/'sessions'
    status=folder/'player-probe-status.json'
    status.write_text(json.dumps(dict(stage='locating')),encoding='utf-8')
    try:
        r.open_process(game_pid());module=locate(r)
        manager=r.q(module+144)
        (folder/'player-manager.json').write_text(json.dumps(r.fields(manager),ensure_ascii=False,indent=2),encoding='utf-8')
        players=set()
        for field in r.fields(manager)['fields']:
            pointer=r.q(manager+field['offset'])
            if r.cls(pointer)=='List`1':
                try: players.update(p for p in members(r,pointer) if r.cls(p)=='BattlePlayerData')
                except RuntimeError: pass
        target=next(p for p in players if r.string(r.q(r.q(r.q(p+488)+16)+24))=='STezuka03')
        path=folder/('player-probe-'+time.strftime('%H%M%S')+'.jsonl')
        turns=TurnReader(r,module);last=None
        with path.open('w',encoding='utf-8') as log:
            status.write_text(json.dumps(dict(stage='watching',path=str(path))),encoding='utf-8')
            start=time.monotonic()
            while time.monotonic()-start<240 and not (folder/'player-probe-stop').exists():
                data=dict(player=inspect(target),context=turns.sample(),actions=snapshot(r,module)[1])
                if data!=last:
                    log.write(json.dumps(data,ensure_ascii=False)+'\n');log.flush();last=data
                time.sleep(.1)
    except Exception:status.write_text(json.dumps(dict(stage='error',error=traceback.format_exc())),encoding='utf-8')
    finally:
        if r.h:r.close(r.h);r.h=None
if __name__=='__main__':main()
