"""Local loopback HTTP API and Web UI server (roadmap B6 & F5, Option C).

Listens strictly on loopback (``127.0.0.1``) using the standard library's
:class:`http.server.ThreadingHTTPServer`.

Serves both the Single-Page Web UI (3-column Damage Calculator for Live &
Offline modes, Team Build Archive with skill details & shareable calculation
plans, and the Reference Library) and the JSON API:

* ``GET  /``                         -- Web UI (``hbr_live_core/web/index.html``)
* ``GET  /style.css``                -- Web UI stylesheet
* ``GET  /app.js``                   -- Web UI frontend application
* ``GET  /portrait/<style_label>``   -- Local style portrait PNG (if cached)
* ``GET  /snapshot``                 -- Latest live or active offline :class:`Snapshot`
* ``POST /mode``                     -- Switch active calculator source (``live`` / ``offline``)
* ``POST /damage/prepare``           -- :func:`hbr_live_core.damage_service.prepare` + proposals + audit
* ``POST /damage/effect/proposals``  -- Candidate skill/passive effects for a party caster
* ``POST /damage/effect/calculate``  -- Calculate buff/debuff effect amount
* ``POST /damage/precast``           -- Pre-cast all confirmed support effects for a caster
* ``POST /damage/pending``           -- :func:`hbr_live_core.damage_service.apply_pending`
* ``POST /damage/compute``           -- :func:`hbr_live_core.damage_service.compute`
* ``POST /damage/sequence``          -- ``sequence_add`` / ``sequence_undo`` / ``sequence_clear``
* ``GET  /teams``                    -- Saved teams and drafts from :class:`TeamStore`
* ``POST /teams/save``               -- Save or overwrite a team from a draft
* ``POST /teams/delete``             -- Delete a saved team or draft
* ``GET  /skills/detail``            -- Structured catalog skill detail by ``label``
* ``POST /offline/plan``             -- Build/validate/activate an :class:`OfflineSession`
* ``POST /offline/status``           -- Create & validate a manual status entry
* ``GET  /library/search``           -- Search local ``hbr_data`` catalog
* ``GET  /library/record``           -- Fetch full record detail from ``hbr_data``
* ``POST /library/sql``              -- Read-only SQL query against local ``hbr_data``

Can be launched standalone from the command line::

    python -B -m hbr_live_core.http_api --port 8765 --open
"""
import argparse
from dataclasses import asdict, is_dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlsplit
import webbrowser

from hbr_live_app import offline_battle as ob
from hbr_live_app.damage_autofill import catalog_skill, style_elements
from hbr_live_app.damage_sequence import DamageSequence
from hbr_live_app.effect_math import EffectInputs, calculate_effect
from hbr_live_app.effect_preview import proposals as effect_proposals
from hbr_live_app.skill_forms import forms as skill_forms
from hbr_live_app.team_views import effect_group, equipment_slot, member_matches
from . import damage_service
from .offline_session import OfflineSession

LOOPBACK_HOSTS = {'127.0.0.1', 'localhost', '::1'}
ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent / 'web'

_PREPARED_OMIT = {'pending_context', 'pending_base', 'dismissed_effects', 'filled'}
_COMPUTE_OMIT = {'sequence_candidate'}


def _to_plain(obj):
    if is_dataclass(obj):
        return _to_plain(asdict(obj))
    if isinstance(obj, dict):
        return {str(k): _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_to_plain(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    return obj


def _json_safe_prepared(prepared):
    if not isinstance(prepared, dict):
        return prepared
    out = {k: v for k, v in prepared.items() if k not in _PREPARED_OMIT}
    if 'modes' in out and isinstance(out['modes'], dict):
        out['modes'] = {k: v for k, v in out['modes'].items() if k != 'enemies'}
    if 'form_info' in out and isinstance(out['form_info'], dict):
        out['form_info'] = {k: v for k, v in out['form_info'].items() if k not in ('data', 'form_key')}
    for key in ('identity', 'sequence_battle', 'pending_battle'):
        if key in out and isinstance(out[key], tuple):
            out[key] = list(out[key])
    return _to_plain(out)


def _json_safe_compute(result):
    if not isinstance(result, dict):
        return result
    return _to_plain({k: v for k, v in result.items() if k not in _COMPUTE_OMIT})


def _enrich_team_payload(payload, lookup=None):
    """Attach passive categories, equipment slots and switch-skill forms for UI rendering."""
    members = []
    for index, member in enumerate(payload.get('members', [])):
        m = dict(member, index=index)
        skills = []
        for si, sk in enumerate(member.get('skills', [])):
            if not sk.get('label'):
                continue
            variants = skill_forms(sk['label'], lookup=lookup)
            skills.append(dict(
                sk,
                skill_index=si,
                forms=[dict(form_index=fi, label=fl, name=fn) for fi, (fl, fn, _) in enumerate(variants)],
            ))
        m['skills_enriched'] = skills
        passives = []
        for p in member.get('passives', []):
            group = effect_group(p)
            slot = equipment_slot(p) if group == '饰品效果' else None
            passives.append(dict(p, group=group, slot=slot))
        m['passives_enriched'] = passives
        members.append(m)
    return dict(payload, members=members)


def _proposals_for_caster(prepared, caster_id=None, lookup=None):
    if not prepared or 'pending_context' not in prepared:
        return []
    player, enemy, _, modes, party = prepared['pending_context']
    if caster_id is not None:
        player = next((p for p in (party or []) if p.get('actor_id') == caster_id), player)
    caster_modes = dict(modes, lightning_style='Thunder' in style_elements(player.get('style_label', '')))
    items = effect_proposals(player, enemy, caster_modes, lookup=lookup)
    out = []
    for idx, item in enumerate(items):
        try:
            preview_amount = calculate_effect(EffectInputs(**item['values']))['final']
        except (ValueError, TypeError, OverflowError):
            preview_amount = None
        out.append(dict(
            index=idx,
            title=item['title'],
            caster=item.get('caster'),
            source=item.get('source'),
            passive=bool(item.get('passive')),
            funnel_count=item.get('funnel_count'),
            values=item['values'],
            notes=item.get('notes', ''),
            part=item['part'],
            preview_amount=preview_amount,
        ))
    return out


class LocalApi:
    """In-memory request dispatcher backing the local HTTP server."""

    def __init__(self, snapshot_provider=None, team_store=None, autofill_fn=None, catalog_lookup=None):
        self.snapshot_provider = snapshot_provider or (
            lambda: dict(connected=False, run_id=None, execution_revision=0, players=[], enemies=[])
        )
        self.team_store = team_store
        self.autofill_fn = autofill_fn
        self.catalog_lookup = catalog_lookup
        self.sequence = DamageSequence()
        self.prepared = None
        self.last_calc = None
        self.offline_session = None
        self.mode = 'live'
        self._status_serial = 0

    def current_snapshot(self):
        if self.mode == 'offline' and self.offline_session is not None:
            return self.offline_session.snapshot(lookup=self.catalog_lookup)
        if self.offline_session is not None and not self.snapshot_provider().get('connected'):
            return self.offline_session.snapshot(lookup=self.catalog_lookup)
        return self.snapshot_provider()

    def _enrich_prepared_response(self):
        safe = _json_safe_prepared(self.prepared)
        if isinstance(safe, dict) and safe.get('ok'):
            safe['effect_proposals'] = _proposals_for_caster(self.prepared, lookup=self.catalog_lookup)
            snap = self.current_snapshot()
            audit, raw_header = damage_service.format_raw_inspection(snap, safe.get('fill_notes', ''))
            safe['audit_text'] = audit
            safe['raw_header'] = raw_header
        return safe

    def handle_http(self, method, path, raw_body=b''):
        """Serve static Web UI files, cached portraits, or JSON API endpoints.

        Returns ``(status_code, content_type, body_bytes)``.
        """
        static_files = {
            '/': ('index.html', 'text/html; charset=utf-8'),
            '/index.html': ('index.html', 'text/html; charset=utf-8'),
            '/style.css': ('style.css', 'text/css; charset=utf-8'),
            '/app.js': ('app.js', 'application/javascript; charset=utf-8'),
        }
        route = urlsplit(path).path
        if method == 'GET' and route in static_files:
            filename, content_type = static_files[route]
            target = WEB_DIR / filename
            if target.is_file():
                return 200, content_type, target.read_bytes()
        if method == 'GET' and route.startswith('/portrait/'):
            label = route.removeprefix('/portrait/').strip('/')
            raw = _find_portrait_bytes(label)
            if raw:
                return 200, 'image/png', raw
            err = json.dumps(dict(ok=False, error='portrait not cached'), ensure_ascii=False).encode('utf-8')
            return 404, 'application/json; charset=utf-8', err
        body = {}
        if method == 'POST' and raw_body:
            try:
                body = json.loads(raw_body.decode('utf-8')) if isinstance(raw_body, (bytes, bytearray)) else json.loads(raw_body)
            except ValueError:
                err = json.dumps(dict(ok=False, error='无效的 JSON 请求体'), ensure_ascii=False).encode('utf-8')
                return 400, 'application/json; charset=utf-8', err
        status, payload = self.handle(method, path, body)
        return status, 'application/json; charset=utf-8', json.dumps(payload, ensure_ascii=False).encode('utf-8')

    def handle(self, method, path, body=None):
        """Dispatch ``(method, path, body_dict)`` and return ``(status_code, response_dict)``."""
        parsed = urlsplit(path)
        route = parsed.path.rstrip('/') or '/'
        query = {k: v[0] for k, v in parse_qs(parsed.query).items() if v}
        data = body or {}
        try:
            if method == 'GET' and route == '/snapshot':
                snap = self.current_snapshot()
                return 200, dict(snap, active_mode='offline' if snap.get('offline') else 'live')

            if method == 'POST' and route == '/mode':
                mode = data.get('mode', 'live')
                if mode not in ('live', 'offline'):
                    raise ValueError('模式必须为 live 或 offline')
                self.mode = mode
                if mode == 'live':
                    self.offline_session = None
                snap = self.current_snapshot()
                return 200, dict(ok=True, mode=self.mode, snapshot=snap)

            if method == 'GET' and route == '/teams':
                q = query.get('q', '').strip()
                scope = query.get('scope', 'team')
                if self.team_store is None:
                    return 200, dict(teams=[], drafts=[])
                teams = []
                for key, name, payload in self.team_store.rows(drafts=False):
                    if q:
                        if scope == 'member':
                            if not any(member_matches(m, q) for m in payload.get('members', [])):
                                continue
                        elif q.casefold() not in name.casefold():
                            continue
                    teams.append(dict(
                        id=key,
                        key=f's:{key}',
                        draft=False,
                        name=name,
                        captured_at=payload.get('captured_at', ''),
                        payload=_enrich_team_payload(payload, lookup=self.catalog_lookup),
                    ))
                drafts = []
                for key, name, payload in self.team_store.rows(drafts=True):
                    label = (payload.get('captured_at') or name or key).replace('T', ' ')
                    if q:
                        if scope == 'member':
                            if not any(member_matches(m, q) for m in payload.get('members', [])):
                                continue
                        elif q.casefold() not in label.casefold():
                            continue
                    drafts.append(dict(
                        run_id=key,
                        key=f'd:{key}',
                        draft=True,
                        name=label,
                        captured_at=payload.get('captured_at', ''),
                        payload=_enrich_team_payload(payload, lookup=self.catalog_lookup),
                    ))
                return 200, dict(teams=teams, drafts=drafts)

            if method == 'POST' and route == '/teams/save':
                if self.team_store is None:
                    raise ValueError('配队数据库未初始化')
                run_id = data.get('run_id')
                name = data.get('name', '')
                target = data.get('target')
                if target in ('', None):
                    target = None
                else:
                    target = int(target)
                self.team_store.save(run_id, name, target)
                return self.handle('GET', '/teams')

            if method == 'POST' and route == '/teams/delete':
                if self.team_store is None:
                    raise ValueError('配队数据库未初始化')
                draft = bool(data.get('draft', False))
                key = data.get('key')
                if not draft and key is not None:
                    key = int(key)
                self.team_store.delete(key, draft=draft)
                return self.handle('GET', '/teams')

            if method == 'GET' and route == '/skills/detail':
                from hbr_data.details import skill_detail
                label = query.get('label', '').strip()
                lookup = self.catalog_lookup or catalog_skill
                raw = lookup(label) if label else {}
                if not raw:
                    return 200, dict(found=False, label=label)
                detail = _to_plain(skill_detail(raw))
                variants = skill_forms(label, lookup=lookup)
                form_details = []
                for fi, (fl, fn, _) in enumerate(variants):
                    f_raw = lookup(fl) or {}
                    if f_raw:
                        form_details.append(dict(index=fi, label=fl, name=fn, detail=_to_plain(skill_detail(f_raw))))
                return 200, dict(found=True, label=label, detail=detail, forms=form_details)

            if method == 'POST' and route == '/damage/prepare':
                snap = data.get('snapshot') or self.current_snapshot()
                actor_id = data.get('actor_id')
                enemy_address = data.get('enemy_address')
                if actor_id is None and snap.get('players'):
                    actor_id = snap['players'][0].get('actor_id')
                if enemy_address is None and snap.get('enemies'):
                    enemy_address = snap['enemies'][0].get('address')
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
                return 200, self._enrich_prepared_response()

            if method == 'POST' and route == '/damage/effect/proposals':
                if self.prepared is None or not self.prepared.get('ok'):
                    return 400, dict(ok=False, error='请先自动填充角色与敌人')
                caster_id = data.get('caster_id')
                items = _proposals_for_caster(self.prepared, caster_id=caster_id, lookup=self.catalog_lookup)
                return 200, dict(ok=True, proposals=items)

            if method == 'POST' and route == '/damage/effect/calculate':
                inputs = EffectInputs(
                    kind=str(data.get('kind', 'buff')),
                    minimum=float(data.get('minimum', 0)),
                    maximum=float(data.get('maximum', 0)),
                    threshold=float(data.get('threshold', 0)),
                    level=int(float(data.get('level', 1))),
                    growth_min=float(data.get('growth_min', 0)),
                    growth_max=float(data.get('growth_max', 0)),
                    attribute=float(data.get('attribute', 0)),
                    enemy=float(data.get('enemy', 0)),
                    reduction=float(data.get('reduction', 0)),
                    orb=int(float(data.get('orb', 0))),
                    enhancement=float(data.get('enhancement', 0)),
                    over_rate=float(data.get('over_rate', 0)),
                )
                res = calculate_effect(inputs)
                return 200, dict(ok=True, result=res)

            if method == 'POST' and route == '/damage/precast':
                if self.prepared is None or not self.prepared.get('ok'):
                    return 400, dict(ok=False, error='请先自动填充伤害角色和敌人')
                caster_id = data.get('caster_id')
                updated, rows, skipped, message = damage_service.pre_cast_support(
                    self.prepared,
                    caster_id=caster_id,
                )
                self.prepared = damage_service.prepare(
                    self.current_snapshot(),
                    self.prepared['actor_id'],
                    self.prepared['enemy_address'],
                    options=data.get('options') or {},
                    sequence=self.sequence,
                    sequence_battle=self.prepared.get('sequence_battle'),
                    pending_effects=updated['pending_effects'],
                    dismissed_effects=self.prepared.get('dismissed_effects'),
                    pending_battle=self.prepared.get('pending_battle'),
                    autofill_fn=self.autofill_fn,
                )
                out = self._enrich_prepared_response()
                out['precast_message'] = message
                out['precast_count'] = len(rows)
                out['precast_skipped'] = skipped
                return 200, out

            if method == 'POST' and route == '/damage/pending':
                if self.prepared is None:
                    return 400, dict(ok=False, error='请先调用 /damage/prepare')
                action = data.get('action')
                if action == 'add':
                    item = data.get('item')
                    if item is None and 'proposal_index' in data:
                        caster_id = data.get('caster_id')
                        props = _proposals_for_caster(self.prepared, caster_id=caster_id, lookup=self.catalog_lookup)
                        idx = int(data['proposal_index'])
                        if not 0 <= idx < len(props):
                            raise ValueError('请先选择技能效果')
                        item = dict(props[idx])
                        if data.get('funnel_count') is not None:
                            item['funnel_count'] = float(data['funnel_count'])
                        if data.get('recipient_id') is not None:
                            item['recipient_id'] = data['recipient_id']
                    payload = (item, float(data.get('amount', 0)))
                else:
                    payload = int(data.get('index', data.get('payload', 0)))
                self.prepared = damage_service.apply_pending(
                    self.prepared,
                    action,
                    payload,
                    current_values=data.get('current_values'),
                    current_hit_weights=data.get('current_hit_weights'),
                    autofill_fn=self.autofill_fn,
                )
                return 200, self._enrich_prepared_response()

            if method == 'POST' and route == '/damage/compute':
                overrides = data.get('overrides', data)
                self.last_calc = damage_service.compute(self.prepared, overrides=overrides)
                return 200, _json_safe_compute(self.last_calc)

            if method == 'POST' and route == '/damage/sequence':
                action = data.get('action')
                if action == 'add':
                    if self.last_calc is None or data.get('overrides'):
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

            if method == 'POST' and route == '/offline/status':
                self._status_serial += 1
                status = ob.manual_status(
                    kind=data.get('kind'),
                    value=data.get('value'),
                    element=data.get('element') or '',
                    count=data.get('count'),
                    serial=int(data.get('serial') or self._status_serial),
                    permanent=bool(data.get('permanent', False)),
                )
                target = data.get('target', ob.ALL_MEMBERS)
                return 200, dict(
                    ok=True,
                    target=target,
                    status=status,
                    description=ob.describe_status(status),
                )

            if method == 'POST' and route == '/offline/plan':
                payload_data = dict(data)
                if not payload_data.get('team') and payload_data.get('team_key') and self.team_store is not None:
                    tkey = str(payload_data['team_key'])
                    if tkey.startswith('d:'):
                        raw_id = tkey[2:]
                        found = next((p for k, _, p in self.team_store.rows(drafts=True) if str(k) == raw_id), None)
                    else:
                        raw_id = tkey[2:] if tkey.startswith('s:') else tkey
                        found = next((p for k, _, p in self.team_store.rows(drafts=False) if str(k) == raw_id), None)
                    if found is None:
                        raise ValueError('未找到所选配队档案')
                    payload_data['team'] = found
                session = OfflineSession.from_dict(payload_data)
                if data.get('activate', True):
                    self.offline_session = session
                    self.mode = 'offline'
                snap = session.snapshot(lookup=self.catalog_lookup)
                return 200, dict(
                    ok=True,
                    plan=session.to_dict(),
                    team_enriched=_enrich_team_payload(session.team, lookup=self.catalog_lookup),
                    snapshot=snap,
                )

            if method == 'GET' and route == '/library/search':
                from hbr_data.store import Catalog
                region = query.get('region', 'cn')
                dataset = query.get('dataset', 'styles')
                keyword = query.get('q', '').strip()
                limit = min(200, int(query.get('limit', 100)))
                catalog = Catalog()
                try:
                    _, rows, truncated = catalog.search(region, dataset, keyword, limit=limit)
                except (OSError, ValueError, KeyError) as exc:
                    return 200, dict(available=False, error=str(exc), rows=[], truncated=False)
                items = [
                    dict(record_key=r[0], id=r[1], name=r[2], label=r[3])
                    for r in rows
                ]
                return 200, dict(available=True, rows=items, truncated=truncated)

            if method == 'GET' and route == '/library/record':
                from hbr_data.details import DetailService
                record_key = query.get('key', '').strip()
                if not record_key:
                    raise ValueError('缺少 record_key')
                service = DetailService()
                rec = service.record(record_key)
                return 200, dict(ok=True, record=_to_plain(rec))

            if method == 'POST' and route == '/library/sql':
                from hbr_data.store import Catalog
                sql = str(data.get('sql', '')).strip()
                if not sql:
                    raise ValueError('请输入 SQL 查询语句')
                catalog = Catalog()
                columns, rows, truncated = catalog.query(sql, limit=min(500, int(data.get('limit', 200))))
                return 200, dict(ok=True, columns=columns, rows=[list(r) for r in rows], truncated=truncated)

            return 404, dict(ok=False, error=f'未找到接口：{method} {route}')
        except (ValueError, LookupError, TypeError, KeyError) as exc:
            return 400, dict(ok=False, error=str(exc))


def _find_portrait_bytes(style_label):
    """Look up a cached style portrait PNG by style_label without network requests."""
    if not style_label:
        return None
    try:
        from hbr_data.assets import AssetStore
        from hbr_data.store import Catalog
        catalog = Catalog()
        assets = AssetStore(catalog.root)
        for region in ('cn', 'jp', 'en'):
            _, rows, _ = catalog.query(
                "SELECT id, raw_json FROM records WHERE region=? AND dataset='styles' AND label=? LIMIT 1",
                (region, style_label),
            )
            if not rows:
                continue
            entity_id, raw = rows[0]
            path = assets.get(region, 'styles', entity_id)
            if path and Path(path).is_file():
                return Path(path).read_bytes()
            data = json.loads(raw)
            image = data.get('image') or ''
            if image:
                for candidate in (catalog.root / 'assets').rglob(Path(image).name):
                    if candidate.is_file():
                        return candidate.read_bytes()
    except Exception:
        return None
    return None


def create_server(api, host='127.0.0.1', port=0):
    """Create a loopback-only :class:`ThreadingHTTPServer` for ``api``."""
    if host not in LOOPBACK_HOSTS:
        raise ValueError(f'本地服务仅允许绑定回环地址 127.0.0.1，拒绝：{host!r}')

    class Handler(BaseHTTPRequestHandler):
        def _send_bytes(self, status, raw, content_type):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            status, content_type, raw = api.handle_http('GET', self.path)
            self._send_bytes(status, raw, content_type)

        def do_POST(self):
            length = int(self.headers.get('Content-Length') or 0)
            raw_body = self.rfile.read(length) if length > 0 else b'{}'
            status, content_type, raw = api.handle_http('POST', self.path, raw_body)
            self._send_bytes(status, raw, content_type)

        def log_message(self, format, *args):
            pass

    return ThreadingHTTPServer((host, port), Handler)


class WebServerController:
    """Manage a background local HTTP server thread for the desktop app."""

    def __init__(self, snapshot_provider, team_store):
        self.api = LocalApi(snapshot_provider=snapshot_provider, team_store=team_store)
        self.server = None
        self.thread = None
        self.url = None

    def start(self, host='127.0.0.1', port=0):
        if self.server is not None:
            return self.url
        self.server = create_server(self.api, host=host, port=port)
        actual_port = self.server.server_address[1]
        self.url = f'http://127.0.0.1:{actual_port}/'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self.url

    def open_browser(self, tab=None):
        url = self.start()
        if tab:
            url = f'{url}#{tab}'
        webbrowser.open(url)
        return url

    def stop(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
            self.url = None


def main(argv=None):
    from hbr_live_app.team_store import TeamStore
    from .live_session import LiveSession

    parser = argparse.ArgumentParser(description='HBR Live local Web UI server (Option C).')
    parser.add_argument('--host', default='127.0.0.1', help='Loopback address to bind (default: 127.0.0.1).')
    parser.add_argument('--port', type=int, default=8765, help='Port to listen on (0 for automatic).')
    parser.add_argument('--replay', type=Path, help='Pre-load a recorded session JSONL file for live mode.')
    parser.add_argument('--open', action='store_true', help='Open the Web UI in the default browser.')
    args = parser.parse_args(argv)

    store = TeamStore(ROOT / 'data' / 'team_builds.sqlite3')
    session = LiveSession(ROOT / 'sessions', store)
    if args.replay:
        session.replay_file(args.replay)
    api = LocalApi(snapshot_provider=session.latest_snapshot, team_store=store)
    server = create_server(api, host=args.host, port=args.port)
    actual_port = server.server_address[1]
    url = f'http://{args.host}:{actual_port}/'
    print(f'HBR Live Web UI running at {url}')
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
