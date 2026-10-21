"""Refresh published style/talent tables and atomically rebuild their local index."""
import copy
import hashlib
import json
import time
from datetime import datetime,timezone
from .sync import ROOT,fetch
from .store import build_database


def sync_talents(root=ROOT,progress=print):
    lock=root/'sync.lock'
    lock.mkdir()
    try:
        manifest=copy.deepcopy(json.loads((root/'current.json').read_text(encoding='utf-8')))
        tables={'styles','passives','support_skills','role_abilities'}
        jobs=[(url,source) for url,source in manifest['sources'].items() if source['table'] in tables]
        if not jobs:raise ValueError('未找到已验证的天赋来源')
        for url,source in jobs:
            raw=fetch(url);parsed=json.loads(raw)
            expected=dict if source['table']=='role_abilities' else list
            if not isinstance(parsed,expected) or not parsed:raise ValueError('天赋来源结构已变化：'+url)
            digest=hashlib.sha256(raw).hexdigest();path=root/'objects'/(digest+'.json')
            if not path.exists():path.write_bytes(raw)
            source.update(path=str(path.relative_to(root)).replace('\\','/'),bytes=len(raw),count=len(parsed),
                          fetched=datetime.now(timezone.utc).isoformat())
            progress(f'{source["region"]} / {source["table"]}: {len(parsed)}')
        destination=root/f'catalog-talents-{time.time_ns()}.sqlite'
        build_database(root,manifest,destination)
        manifest.update(database=destination.name,talents_updated=datetime.now(timezone.utc).isoformat())
        temporary=root/'talents-manifest.tmp'
        temporary.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(root/'current.json')
        progress('天赋来源与索引更新完成')
    finally:lock.rmdir()


if __name__=='__main__':sync_talents()
