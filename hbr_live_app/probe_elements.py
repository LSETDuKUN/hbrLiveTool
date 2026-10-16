"""One-shot read-only element gauge inspection."""
import json
import traceback
from pathlib import Path
from . import runtime as r
from .source import locate
from .windows import game_pid


def main():
    out = Path(__file__).resolve().parent.parent/'sessions'/'element-probe.json'
    try:
        r.open_process(game_pid())
        module = locate(r)
        queue = [('module', module, 0), ('info',r.q(module+64),0)]
        result = {}; seen = set()
        while queue and len(result) < 80:
            path, address, depth = queue.pop(0)
            if address in seen:
                continue
            seen.add(address)
            data = r.fields(address)
            result[path] = data
            for f in data['fields']:
                if f['type'] == 17:
                    f['raw4'] = r.read(address+f['offset'], 4).hex()
                obj = f.get('object')
                if obj and depth < 4 and any(s in (f['name'].replace('k__BackingField','')+obj['class']).lower()
                        for s in ('element', 'burst', 'zone', 'gauge', 'field', 'master', 'specialstatus', 'limit', 'exitcondition')):
                    queue.append((path+'.'+f['name'], int(obj['address'],16), depth+1))
        out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        from .statuses import StatusReader
        from .formation import FormationReader
        from .source import members
        reader = StatusReader(r)
        from .probe_players import inspect
        manager = reader.prop(module,'specialStatusManager')
        statuses = members(r,reader.get(manager,'specialStatusList'))
        out.with_name('global-status-probe.json').write_text(json.dumps(
            [inspect(a,4,80) for a in statuses],ensure_ascii=False,indent=2),encoding='utf8')
        players = FormationReader(r,module).sample()
        enemies = members(r,r.q(r.q(module+144)+168))
        out.with_name('resistance-probe.json').write_text(json.dumps(
            [inspect(e,4,120) for e in enemies],ensure_ascii=False,indent=2),encoding='utf8')
        snapshot = dict(players=[dict(p, **reader.sample(p['actor_id'],True)) for p in players],
            enemies=[dict(address=e, **reader.sample(e)) for e in members(r,r.q(r.q(module+144)+168))],
            element_gauge=reader.element_gauge(module), field_state=reader.sample_fields(module))
        out.with_name('status-reader-check.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf8')
    except Exception:
        out.with_name('element-probe-error.txt').write_text(traceback.format_exc(),encoding='utf8')
    finally:
        if r.h:
            r.close(r.h);r.h=None


if __name__ == '__main__':
    main()
