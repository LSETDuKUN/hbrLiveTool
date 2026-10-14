"""Bounded read-only enemy inspection; writes diagnostics only under sessions."""
import json
import time
import traceback
import sys
from pathlib import Path
from . import runtime as r
from .source import locate, members
from .windows import game_pid
from .turns import TurnReader


def watch_sample(module, turns):
    enemies = members(r, r.q(r.q(module + 144) + 168))
    result = dict(context=turns.sample(), enemies=[], actions=[])
    for enemy in enemies:
        commands = r.q(enemy + 600)
        row = dict(address=hex(enemy), hp=r.q(enemy+72), dp=r.q(enemy+80),
                   main=r.i(enemy+608), broken=r.i(enemy+612), base_main=r.i(enemy+400),
                   base_broken=r.i(enemy+404), down=r.i(enemy+128), selected_once=r.read(enemy+640,1).hex(),
                   commands=r.fields(commands) if commands else None)
        if commands and r.cls(commands) == 'List`1':
            row['items'] = [r.fields(p) for p in members(r, commands)]
        result['enemies'].append(row)
    manager = r.q(module+96)
    for entry in members(r, r.q(manager+16)):
        actor = r.q(entry+32)
        if actor not in enemies:
            continue
        master = r.q(r.q(r.q(entry+24)+16)+16)
        result['actions'].append(dict(actor=hex(actor), skill=r.string(r.q(master+24)),
                                     name=r.string(r.q(master+32)), executing=r.q(manager+40)==entry))
    return result


def inspect(module):
    enemies = members(r, r.q(r.q(module + 144) + 168))
    queue = [(f'enemy{n}', e, 0) for n, e in enumerate(enemies)]
    queue += [('actions', r.q(module + 96), 0), ('timeline', r.q(module + 216), 0)]
    output, seen = {}, set()
    while queue and len(output) < 160:
        path, obj, depth = queue.pop(0)
        if obj in seen:
            continue
        seen.add(obj)
        detail = r.fields(obj)
        output[path] = detail
        if depth >= 4:
            continue
        if detail['class'] == 'List`1':
            try:
                queue.extend((path + f'[{i}]', p, depth+1) for i, p in enumerate(members(r, obj)[:24]))
            except RuntimeError:
                pass
        for f in detail['fields']:
            child = f.get('object')
            if child and any(s in (f['name'] + child['class']).lower() for s in
                             ('enemy', 'master', 'skill', 'pattern', 'action', 'think', 'ai', 'turn', 'timeline')):
                queue.append((path + '.' + f['name'], int(child['address'], 16), depth+1))
    return output


def main():
    r.open_process(game_pid())
    try:
        module = locate(r)
        data = inspect(module)
        path = Path(__file__).resolve().parent.parent / 'sessions' / ('enemy-probe-' + time.strftime('%H%M%S') + '.json')
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(str(path))
        if '--watch' in sys.argv:
            turns = TurnReader(r, module)
            status = path.parent / 'enemy-probe-status.json'
            status.write_text(json.dumps(dict(stage='watching', log=str(path.with_suffix('.jsonl')))), encoding='utf-8')
            previous = None
            started = time.monotonic()
            with path.with_suffix('.jsonl').open('x', encoding='utf-8') as log:
                while time.monotonic()-started < 600 and not (path.parent / 'enemy-probe-stop').exists():
                    sample = watch_sample(module, turns)
                    if sample != previous:
                        log.write(json.dumps(dict(time=time.time(), **sample), ensure_ascii=False)+'\n')
                        log.flush()
                        previous = sample
                    time.sleep(0.05)
    finally:
        r.close(r.h)
        r.h = None


if __name__ == '__main__':
    status = Path(__file__).resolve().parent.parent / 'sessions' / 'enemy-probe-status.json'
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(json.dumps(dict(stage='running', time=time.time())), encoding='utf-8')
    try:
        main()
        result = dict(stage='finished', time=time.time())
    except Exception:
        result = dict(stage='error', time=time.time(), error=traceback.format_exc())
    status.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
