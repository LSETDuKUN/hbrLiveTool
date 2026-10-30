"""Repair a missing CN enemy detail using an exact catalog identity."""
import copy
import hashlib
import json
import time
from datetime import datetime,timezone
from .sync import ROOT,fetch
from .store import build_database


def sync_enemy_detail(label,root=ROOT):
    if not label or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' for c in label):
        raise ValueError('敌人标识不合法')
    lock=root/'sync.lock';lock.mkdir()
    try:
        manifest=copy.deepcopy(json.loads((root/'current.json').read_text(encoding='utf-8')))
        index_url=next(url for url,source in manifest['sources'].items() if source['region']=='cn' and source['table']=='enemies')
        index_raw=fetch(index_url)
        rows=[r for r in json.loads(index_raw) if r.get('label')==label]
        if len(rows)!=1:raise ValueError('敌人国服身份不唯一，未更新')
        url='https://master.hbr.quest/v1/cn/enemies/'+label+'.json'
        raw=fetch(url);data=json.loads(raw)
        if data.get('label')!=label or str(data.get('id'))!=str(rows[0]['id']) or not data.get('pattern'):
            raise ValueError('详细资料身份或行动表不匹配，保留原数据库')
        path=root/'objects'/(hashlib.sha256(raw).hexdigest()+'.json')
        if not path.exists():path.write_bytes(raw)
        manifest['sources'][url]=dict(region='cn',table='enemy_details',
            path=path.relative_to(root).as_posix(),bytes=len(raw),count=len(data),fetched=datetime.now(timezone.utc).isoformat())
        index_path=root/'objects'/(hashlib.sha256(index_raw).hexdigest()+'.json')
        if not index_path.exists():index_path.write_bytes(index_raw)
        manifest['sources'][index_url].update(path=index_path.relative_to(root).as_posix(),bytes=len(index_raw),count=len(json.loads(index_raw)),fetched=datetime.now(timezone.utc).isoformat())
        destination=root/f'catalog-enemy-{time.time_ns()}.sqlite'
        build_database(root,manifest,destination)
        manifest['database']=destination.name
        temporary=root/'enemy-manifest.tmp'
        temporary.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(root/'current.json')
        return destination
    finally:lock.rmdir()


if __name__=='__main__':
    import sys
    print(sync_enemy_detail(sys.argv[1]))
