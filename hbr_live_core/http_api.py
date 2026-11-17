"""Thin local-only HTTP API over hbr_live_core services (roadmap B6, for Option C).

Listens strictly on loopback (``127.0.0.1``) using the standard library's
:class:`http.server.ThreadingHTTPServer` so no external web framework is
required to run or test it.

Endpoints:

* ``GET  /snapshot``        -- latest live or active offline :class:`Snapshot`
* ``GET  /teams``           -- saved teams and drafts from :class:`TeamStore`
* ``POST /damage/prepare``  -- :func:`hbr_live_core.damage_service.prepare`
* ``POST /damage/pending``  -- :func:`hbr_live_core.damage_service.apply_pending`
* ``POST /damage/compute``  -- :func:`hbr_live_core.damage_service.compute`
* ``POST /damage/sequence`` -- ``sequence_add`` / ``sequence_undo`` / ``sequence_clear``
* ``POST /offline/plan``    -- validate an :class:`OfflineSession` plan and return its snapshot + exported dict
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import urlsplit

from hbr_live_app.damage_sequence import DamageSequence
from . import damage_service
from .offline_session import OfflineSession

LOOPBACK_HOSTS = {'127.0.0.1', 'localhost', '::1'}

# Keys inside PreparedCalc / CalcResult that hold internal tuples/sets or raw
# dataclass instances and should be serialised or omitted in JSON responses.
_PREPARED_OMIT = {'pending_context', 'pending_base', 'dismissed_effects', 'filled'}
_COMPUTE_OMIT = {'sequence_candidate'}


def _json_safe_prepared(prepared):
    if not isinstance(prepared, dict):
        return prepared
    out = {k: v for k, v in prepared.items() if k not in _PREPARED_OMIT}
    if 'modes' in out and isinstance(out['modes'], dict):
        out['modes'] = {k: v for k, v in out['modes'].items() if k != 'enemies'}
    if 'form_info' in out and isinstance(out['form_info'], dict):
        out['form_info'] = {k: v for k, v in out['form_info'].items() if k not in ('data', 'form_key')}
    if 'identity' in out and isinstance(out['identity'], tuple):
        out['identity'] = list(out['identity'])
    if 'sequence_battle' in out and isinstance(out['sequence_battle'], tuple):
        out['sequence_battle'] = list(out['sequence_battle'])
    if 'pending_battle' in out and isinstance(out['pending_battle'], tuple):
        out['pending_battle'] = list(out['pending_battle'])
    return out


def _json_safe_compute(result):
    if not isinstance(result, dict):
        return result
    return {k: v for k, v in result.items() if k not in _COMPUTE_OMIT}


class LocalApi:
    """In-memory request dispatcher backing the local HTTP server."""

    def __init__(self, snapshot_provider=None, team_store=None, autofill_fn=None):
        self.snapshot_provider = snapshot_provider or (
            lambda: dict(connected=False, run_id=None, execution_revision=0, players=[], enemies=[])
        )
        self.team_store = team_store
        self.autofill_fn = autofill_fn
        self.sequence = DamageSequence()
        self.prepared = None
        self.last_calc = None
        self.offline_session = None

    def current_snapshot(self):
        if self.offline_session is not None:
            return self.offline_session.snapshot()
        return self.snapshot_provider()

    def handle(self, method, path, body=None):
        """Dispatch ``(method, path, body_dict)`` and return ``(status_code, response_dict)``."""
        route = urlsplit(path).path.rstrip('/') or '/'
        data = body or {}
        try:
            if method == 'GET' and route == '/snapshot':
                return 200, self.current_snapshot()
            if method == 'GET' and route == '/teams':
                if self.team_store is None:
                    return 200, dict(teams=[], drafts=[])
                teams = [
                    dict(id=key, name=name, payload=payload)
                    for key, name, payload in self.team_store.rows(drafts=False)
                ]
                drafts = [
                    dict(run_id=key, name=name, payload=payload)
                    for key, name, payload in self.team_store.rows(drafts=True)
                ]
                return 200, dict(teams=teams, drafts=drafts)
            if method == 'POST' and route == '/damage/prepare':
                snap = data.get('snapshot') or self.current_snapshot()
                actor_id = data.get('actor_id')
                enemy_address = data.get('enemy_address')
                options = data.get('options') or {}
                prev = self.prepared or {}
                self.prepared = damage_service.prepare(
                    snap,
                    actor_id,
                    enemy_address,
                    options=options,
                    sequence=self.sequence,
                    sequence_battle=prev.get('sequence_battle'),
                    pending_effects=prev.get('pending_effects'),
                    dismissed_effects=prev.get('dismissed_effects'),
                    pending_battle=prev.get('pending_battle'),
                    autofill_fn=self.autofill_fn,
                )
                return 200, _json_safe_prepared(self.prepared)
            if method == 'POST' and route == '/damage/pending':
                if self.prepared is None:
                    return 400, dict(ok=False, error='请先调用 /damage/prepare')
                action = data.get('action')
                payload = (data.get('item'), data.get('amount')) if action == 'add' else data.get('index', data.get('payload'))
                self.prepared = damage_service.apply_pending(
                    self.prepared,
                    action,
                    payload,
                    current_values=data.get('current_values'),
                    current_hit_weights=data.get('current_hit_weights'),
                    autofill_fn=self.autofill_fn,
                )
                return 200, _json_safe_prepared(self.prepared)
            if method == 'POST' and route == '/damage/compute':
                overrides = data.get('overrides', data)
                self.last_calc = damage_service.compute(self.prepared, overrides=overrides)
                return 200, _json_safe_compute(self.last_calc)
            if method == 'POST' and route == '/damage/sequence':
                action = data.get('action')
                if action == 'add':
                    if self.last_calc is None:
                        self.last_calc = damage_service.compute(self.prepared, overrides=data.get('overrides'))
                    out = damage_service.sequence_add(self.sequence, self.prepared, self.last_calc)
                elif action == 'undo':
                    out = damage_service.sequence_undo(self.sequence)
                elif action == 'clear':
                    out = damage_service.sequence_clear(self.sequence)
                    if self.prepared:
                        self.prepared['pending_effects'] = []
                        self.prepared['dismissed_effects'] = set()
                        self.prepared['pending_delta'] = {}
                else:
                    return 400, dict(ok=False, error=f'未知序列操作：{action}')
                return 200, dict(
                    ok=True,
                    steps=[
                        dict(
                            actor_id=s['actor_id'],
                            actor=s['actor'],
                            skill=s['skill'],
                            raw_damage=s['raw_damage'],
                            damage=s['damage'],
                            before=s['before'],
                            after=s['after'],
                        )
                        for s in out['steps']
                    ],
                    current=out['current'],
                    message=out['message'],
                )
            if method == 'POST' and route == '/offline/plan':
                session = OfflineSession.from_dict(data)
                if data.get('activate', True):
                    self.offline_session = session
                return 200, dict(ok=True, plan=session.to_dict(), snapshot=session.snapshot())
            return 404, dict(ok=False, error=f'未找到接口：{method} {route}')
        except (ValueError, LookupError, TypeError) as exc:
            return 400, dict(ok=False, error=str(exc))


def create_server(api, host='127.0.0.1', port=0):
    """Create a loopback-only :class:`ThreadingHTTPServer` for ``api``."""
    if host not in LOOPBACK_HOSTS:
        raise ValueError(f'本地服务仅允许绑定回环地址 127.0.0.1，拒绝：{host!r}')

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, payload):
            raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            status, payload = api.handle('GET', self.path)
            self._send(status, payload)

        def do_POST(self):
            length = int(self.headers.get('Content-Length') or 0)
            raw = self.rfile.read(length) if length > 0 else b'{}'
            try:
                body = json.loads(raw.decode('utf-8')) if raw else {}
            except ValueError:
                self._send(400, dict(ok=False, error='无效的 JSON 请求体'))
                return
            status, payload = api.handle('POST', self.path, body)
            self._send(status, payload)

        def log_message(self, format, *args):
            # Silence default stderr logging during normal use and tests.
            pass

    return ThreadingHTTPServer((host, port), Handler)
