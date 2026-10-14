"""Read-only, bounded battle-state diagnostic; run elevated on Windows."""
import json
import sys
import time
import traceback
from pathlib import Path

from . import runtime as r
from .source import locate, members
from .windows import game_pid

ROOT = Path(__file__).resolve().parent.parent / 'sessions' / 'turn_probe'


def inspect(address):
    result = r.fields(address)
    for field in result['fields']:
        # Preserve undecoded enum/value-type bytes without guessing their meaning.
        if not any(key in field for key in ('value', 'text', 'object')):
            field['raw16'] = r.read(address + field['offset'], 16).hex()
    return result


def snapshot(module):
    roots = {'module': module, 'state': r.q(module + 16),
             'info': r.q(module + 64), 'actions': r.q(module + 96),
             'timeline': r.q(module + 216)}
    roots['fsm'] = r.q(r.q(roots['state'] + 168) + 48)
    result = {label: inspect(address) for label, address in roots.items()}
    additional = r.q(roots['info'] + 56)
    if additional and r.cls(additional) == 'List`1':
        result['additional_characters'] = dict(address=hex(additional),
            **{'class': r.cls(additional)}, fields=[],
            members=[inspect(address) for address in members(r, additional)])
    seen = set(roots.values())
    for label, obj in list(result.items()):
        for field in obj['fields']:
            child = field.get('object')
            if not child:
                continue
            name = child['class']
            if label != 'fsm' and not any(word in name.lower() for word in
                       ('turn', 'phase', 'state', 'overdrive', 'timeline', 'battleinfo')):
                continue
            address = int(child['address'], 16)
            if address in seen:
                continue
            seen.add(address)
            result[label + '.' + field['name']] = inspect(address)
    return result


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    # A stop marker is deliberately not cleared automatically: avoid restarting
    # or interfering with another collector. Remove it before a new watch run.
    status = ROOT / ('detail-status.json' if '--once' in sys.argv else 'status.json')

    def report(**values):
        status.write_text(json.dumps(dict(time=time.time(), **values), ensure_ascii=False), encoding='utf-8')

    try:
        pid = game_pid()
        r.open_process(pid)
        report(stage='locating', pid=pid)
        module = locate(r)
        first = snapshot(module)
        (ROOT / ('initial-' + time.strftime('%H%M%S') + '.json')).write_text(json.dumps(first, ensure_ascii=False, indent=2), encoding='utf-8')
        if '--once' in sys.argv:
            (ROOT / 'detail.json').write_text(json.dumps(first, ensure_ascii=False, indent=2), encoding='utf-8')
            report(stage='finished')
            return
        report(stage='watching', pid=pid, module=hex(module))
        previous = None
        started = time.monotonic()
        with (ROOT / 'changes.jsonl').open('a', encoding='utf-8') as log:
            while time.monotonic() - started < 900:
                if (ROOT / 'stop').exists():
                    break
                current = snapshot(module)
                if current != previous:
                    log.write(json.dumps(dict(time=time.time(), objects=current), ensure_ascii=False) + '\n')
                    log.flush()
                    previous = current
                time.sleep(0.1)
        report(stage='finished')
    except Exception:
        report(stage='error', error=traceback.format_exc())
    finally:
        if r.h:
            r.close(r.h)
            r.h = None


if __name__ == '__main__':
    main()
