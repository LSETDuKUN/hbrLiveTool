"""Bounded read-only inspection of status display metadata; never changes UI."""
import json
import time
import traceback
from pathlib import Path
from . import runtime as r
from .source import locate, members
from .windows import game_pid
from .statuses import StatusReader
from .probe_players import inspect


def main():
    folder=Path(__file__).resolve().parent.parent/'sessions'
    progress=folder/'status-display-progress.json'
    progress.write_text(json.dumps(dict(stage='locating',time=time.time())),encoding='utf8')
    try:
        r.open_process(game_pid());module=locate(r);reader=StatusReader(r)
        hud=reader.prop(module,'hudModule')
        manager=reader.prop(module,'specialStatusManager')
        queue=[('hud',hud,0),('status_manager',manager,0)]
        member=reader.get(hud,'battleMemberHudModule')
        window=reader.get(member,'uiBattleStatus') if member else None
        if window:
            for name in ('battleStatusContainer','detailStatusContainer','enemyWeakResistContainer','fieldContainer'):
                container=reader.get(window,name)
                if container:
                    for key in ('dataList','_listItems'):
                        items=reader.get(container,key)
                        if items:queue.insert(0,(name+'.'+key,items,0))
        result={};seen=set()
        while queue and len(result)<300:
            path,address,depth=queue.pop(0)
            if not address or address in seen:continue
            seen.add(address);data=r.fields(address);result[path]=data
            for f in data['fields']:
                if f['type']==17:f['raw4']=r.read(address+f['offset'],4).hex()
            if depth>=5:continue
            if data['class']=='List`1':
                try:queue.extend((path+f'[{i}]',a,depth+1) for i,a in enumerate(members(r,address)) if r.cls(a))
                except RuntimeError:pass
            for f in data['fields']:
                child=f.get('object')
                if not child:continue
                key=(f['name'].replace('k__BackingField','')+' '+child['class']).lower()
                if depth==0 or any(word in key for word in ('status','buff','detail','dialog','icon','limit','character','item','panel','popup','entity','data')):
                    queue.append((path+'.'+f['name'],int(child['address'],16),depth+1))
        path=folder/('status-display-'+time.strftime('%H%M%S')+'.json')
        path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        statuslist=members(r,reader.get(manager,'specialStatusList'))
        path.with_suffix('.statuses.json').write_text(json.dumps([inspect(a,4,60) for a in statuslist],ensure_ascii=False),encoding='utf8')
        progress.write_text(json.dumps(dict(stage='done',time=time.time(),path=str(path))),encoding='utf8')
    except Exception:
        progress.write_text(json.dumps(dict(stage='error',error=traceback.format_exc())),encoding='utf8')
    finally:
        if r.h:r.close(r.h);r.h=None


if __name__=='__main__':main()
