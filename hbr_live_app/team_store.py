"""Local team-owned builds. Drafts never overwrite a saved team automatically."""
from contextlib import contextmanager
import copy
import json
import sqlite3
from datetime import datetime
from pathlib import Path

STATS = ('power', 'dexterity', 'toughness', 'spirit', 'wisdom', 'luck')


def skill_references(inputs):
    """Only observed loadout identity/level belong to a team, not shared skill data."""
    skills = inputs.get('equipped_skills') or ([inputs['selected_skill']] if inputs.get('selected_skill') else [])
    return [{k: skill[k] for k in ('label', 'base_label', 'name', 'level') if k in skill} for skill in skills]


def capture(players, context):
    if len(players) != 6 or any(not p.get('style_label') for p in players) or len({p.get('style_label') for p in players}) != 6:
        return None
    if any(not all(k in p.get('combat_inputs', {}).get('stats', {}) for k in STATS) for p in players):
        return None
    members = []
    for p in sorted(players, key=lambda p: p.get('actor_position', 99)):
        inputs = p.get('combat_inputs', {})
        members.append(dict(style_label=p['style_label'], actor=p.get('actor'), style_name=p.get('style_name'),
            position=p.get('actor_position'), dp=p.get('dp'), hp=p.get('hp'),
            dp_max=p.get('dp_max'), hp_max=p.get('hp_max'), stats=copy.deepcopy(inputs['stats']),
            skills=skill_references(inputs),
            skills_complete=bool(inputs.get('equipped_skills')),
            passives=copy.deepcopy(inputs.get('passive_audit', []))))
    return dict(schema=1, captured_at=datetime.now().isoformat(timespec='seconds'),
                context=copy.deepcopy(context or {}), members=members)


class TeamStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS teams (id INTEGER PRIMARY KEY, name TEXT NOT NULL, updated TEXT NOT NULL, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS drafts (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        self.observed = set()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        try:
            with db:
                yield db
        finally:
            db.close()

    def observe(self, run_id, players, context):
        if not run_id or run_id in self.observed: return False
        payload = capture(players, context)
        if payload is None: return False
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO drafts VALUES (?, ?)', (run_id, json.dumps(payload, ensure_ascii=False)))
        self.observed.add(run_id)
        return True

    def rows(self, drafts=False):
        with self.connect() as db:
            if drafts:
                return [(r, r, json.loads(p)) for r, p in db.execute('SELECT run_id,payload FROM drafts ORDER BY rowid DESC')]
            return [(i, n, json.loads(p)) for i, n, p in db.execute('SELECT id,name,payload FROM teams ORDER BY updated DESC,id DESC')]

    def save(self, run_id, name, target=None):
        if not name.strip(): raise ValueError('请输入配队名称')
        with self.connect() as db:
            row = db.execute('SELECT payload FROM drafts WHERE run_id=?', (run_id,)).fetchone()
            if not row: raise ValueError('待确认记录已不存在')
            now = datetime.now().isoformat(timespec='seconds')
            if target is None:
                db.execute('INSERT INTO teams(name,updated,payload) VALUES (?,?,?)', (name.strip(), now, row[0]))
            else:
                if not db.execute('UPDATE teams SET name=?,updated=?,payload=? WHERE id=?', (name.strip(), now, row[0], target)).rowcount:
                    raise ValueError('目标配队已不存在')
            db.execute('DELETE FROM drafts WHERE run_id=?', (run_id,))

    def delete(self, key, draft=False):
        with self.connect() as db:
            db.execute('DELETE FROM drafts WHERE run_id=?' if draft else 'DELETE FROM teams WHERE id=?', (key,))
