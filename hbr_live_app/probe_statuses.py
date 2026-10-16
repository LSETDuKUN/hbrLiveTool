"""Bounded read-only status comparison, kept separate from production sampling."""
import json
import time
import traceback
from pathlib import Path
from . import runtime as r
from .windows import game_pid
from .source import locate, members
from .formation import FormationReader
from .turns import TurnReader
from .probe_players import inspect


def main():
    folder = Path(__file__).resolve().parent.parent/'sessions'
    status = folder/'status-probe-progress.json'
    status.write_text(json.dumps(dict(stage='locating')), encoding='utf-8')
    try:
        r.open_process(game_pid())
        module = locate(r)
        (folder/'status-probe-module.json').write_text(json.dumps(r.fields(module),ensure_ascii=False,indent=2),encoding='utf-8')
        formation = FormationReader(r,module)
        turns = TurnReader(r,module)
        path = folder/('status-probe-'+time.strftime('%H%M%S')+'.jsonl')
        start = time.monotonic()
        with path.open('w',encoding='utf-8') as log:
            while time.monotonic()-start<300 and not (folder/'status-probe-stop').exists():
                front = formation.sample()
                enemies = members(r,r.q(r.q(module+144)+168))
                data = dict(time=time.time(), context=turns.sample(), frontline=front,
                    players={str(p['actor_id']):inspect(p['actor_id'],6,512,128) for p in front},
                    enemies={str(e):inspect(e,6,512,128) for e in enemies})
                log.write(json.dumps(data,ensure_ascii=False)+'\n');log.flush()
                status.write_text(json.dumps(dict(stage='watching',path=str(path))),encoding='utf-8')
                time.sleep(.3)
    except Exception:
        status.write_text(json.dumps(dict(stage='error',error=traceback.format_exc())),encoding='utf-8')
    finally:
        if r.h:
            r.close(r.h);r.h=None


if __name__ == '__main__':
    main()
