"""Shareable offline calculation session (roadmap B3).

An :class:`OfflineSession` bundles a team loadout, per-member skill/form
choices, user-entered enemy parameters (including the shared boss stat),
field/OD settings, and manual buffs/debuffs, and produces a contract-compliant
:class:`~hbr_live_core.schema.Snapshot`.

It can be saved to and loaded from a versioned JSON file ("试算方案") that
strips local/personal identifiers (such as ``run_id``, memory addresses and
capture timestamps) so players can share setups and regression tests can
replay them deterministically.
"""
from copy import deepcopy
import json
from pathlib import Path

from hbr_live_app import offline_battle as ob
from hbr_live_app.skill_forms import with_form
from .schema import check

PLAN_SCHEMA_VERSION = 1
PLAN_KIND = 'hbr_offline_plan'

_MEMBER_KEYS = (
    'style_label', 'actor', 'style_name', 'position',
    'dp', 'hp', 'dp_max', 'hp_max', 'stats', 'skills',
    'skills_complete', 'passives',
)
_SKILL_KEYS = ('label', 'base_label', 'name', 'level')
_PASSIVE_KEYS = (
    'label', 'name', 'condition', 'timing', 'description',
    'parts', 'catalog_found', 'classification', 'runtime',
)


def sanitize_team_payload(payload):
    """Return a copy of ``payload`` with local/personal fields removed."""
    if not isinstance(payload, dict):
        raise ValueError('配队数据格式无效')
    raw_context = payload.get('context') or {}
    context = {}
    if isinstance(raw_context.get('turn'), int) and not isinstance(raw_context.get('turn'), bool):
        context['turn'] = raw_context['turn']
    members = []
    for member in payload.get('members', []):
        clean = {k: deepcopy(member[k]) for k in _MEMBER_KEYS if k in member}
        clean['style_label'] = str(clean.get('style_label') or '')
        clean['stats'] = {k: v for k, v in (clean.get('stats') or {}).items()}
        if 'skills' in clean:
            clean['skills'] = [
                {k: s[k] for k in _SKILL_KEYS if k in s}
                for s in (clean.get('skills') or [])
                if isinstance(s, dict) and s.get('label')
            ]
        if 'passives' in clean:
            passives = []
            for p in (clean.get('passives') or []):
                if not isinstance(p, dict) or not p.get('label'):
                    continue
                item = {k: deepcopy(p[k]) for k in _PASSIVE_KEYS if k in p}
                item.setdefault('name', item['label'])
                item.setdefault('classification', '效果/时机待核对')
                item.setdefault('timing', '未确认')
                item.setdefault('condition', '')
                item.setdefault('description', '')
                item.setdefault('parts', [])
                item.setdefault('catalog_found', False)
                passives.append(item)
            clean['passives'] = passives
        members.append(clean)
    result = dict(schema=1, context=context, members=members)
    check(result, 'TeamPayload')
    return result


def _normalize_skill_choices(skill_choices):
    """Normalize ``{index: (skill_idx, form_idx) | skill_idx}``."""
    normalized = {}
    for raw_key, value in (skill_choices or {}).items():
        index = int(raw_key)
        if isinstance(value, (list, tuple)):
            skill_idx = int(value[0]) if len(value) > 0 and value[0] is not None else 0
            form_idx = int(value[1]) if len(value) > 1 and value[1] is not None else None
        else:
            skill_idx = int(value)
            form_idx = None
        normalized[index] = (skill_idx, form_idx)
    return normalized


def _normalize_target(target):
    if target in (ob.ENEMY, ob.ALL_MEMBERS):
        return target
    if isinstance(target, int) and not isinstance(target, bool):
        return target
    if isinstance(target, str) and target.isdigit():
        return int(target)
    raise ValueError(f'无效的状态目标：{target!r}')


class OfflineSession:
    """Self-contained, serialisable offline calculation setup."""

    def __init__(
        self,
        team_payload,
        *,
        title='',
        key='plan',
        skill_choices=None,
        enemy=None,
        enemy_stat=None,
        field=None,
        od_level=0,
        manual_statuses=None,
        selected_actor_index=0,
        mode_options=None,
        revision=0,
    ):
        self.team = sanitize_team_payload(team_payload)
        self.title = str(title or '')
        self.key = str(key or 'plan')
        self.skill_choices = _normalize_skill_choices(skill_choices)
        enemy_cfg = dict(enemy or {})
        if enemy_stat is None and enemy_cfg.get('defense') is not None:
            enemy_stat = float(enemy_cfg['defense'])
        self.enemy_stat = None if enemy_stat is None else float(enemy_stat)
        self.enemy_config = dict(
            name=enemy_cfg.get('name') or '自定义敌人',
            dp=enemy_cfg.get('dp', 0),
            hp=enemy_cfg.get('hp', 1000000),
            damage_rate=enemy_cfg.get('damage_rate', 100),
            destruction_coefficient=enemy_cfg.get('destruction_coefficient'),
            destruction_max=enemy_cfg.get('destruction_max'),
            rates=dict(enemy_cfg.get('rates') or {}),
            down=int(enemy_cfg.get('down', 0) or 0),
        )
        field_cfg = dict(field or {})
        self.field_config = dict(
            element=str(field_cfg.get('element') or ''),
            bonus=field_cfg.get('bonus'),
        )
        self.od_level = int(od_level or 0)
        if not 0 <= self.od_level <= 3:
            raise ValueError('OD 等级应为 0–3')
        self.manual_statuses = [
            (_normalize_target(target), deepcopy(status))
            for target, status in (manual_statuses or [])
        ]
        self.selected_actor_index = int(selected_actor_index or 0)
        self.mode_options = dict(mode_options or {})
        self.revision = int(revision or 0)

    def build_enemy(self, statuses=()):
        cfg = self.enemy_config
        return ob.manual_enemy(
            name=cfg['name'],
            dp=cfg['dp'],
            hp=cfg['hp'],
            defense=self.enemy_stat,
            damage_rate=cfg['damage_rate'],
            destruction_coefficient=cfg['destruction_coefficient'],
            destruction_max=cfg['destruction_max'],
            rates=cfg['rates'],
            down=cfg['down'],
            statuses=statuses,
        )

    def build_field(self):
        return ob.zone_state(self.field_config['element'], self.field_config['bonus'])

    def snapshot(self, lookup=None):
        """Build a contract-compliant :class:`~hbr_live_core.schema.Snapshot`."""
        ally_statuses = {}
        enemy_statuses = []
        count = len(self.team.get('members', []))
        for target, status in self.manual_statuses:
            if target == ob.ENEMY:
                enemy_statuses.append(deepcopy(status))
            else:
                indices = range(count) if target == ob.ALL_MEMBERS else [target]
                for index in indices:
                    if 0 <= index < count:
                        ally_statuses.setdefault(index, []).append(deepcopy(status))
        enemy = self.build_enemy(statuses=enemy_statuses)
        choices = {i: skill for i, (skill, _) in self.skill_choices.items()}
        data = ob.snapshot(
            self.key,
            self.team,
            enemy,
            skill_choices=choices,
            statuses=ally_statuses,
            field=self.build_field(),
            od_level=self.od_level,
            revision=self.revision,
        )
        players = []
        for index, player in enumerate(data['players']):
            form = self.skill_choices.get(index, (0, None))[1]
            players.append(with_form(player, form, lookup=lookup)[0] if form is not None else player)
        return check(dict(data, players=players))

    def to_dict(self):
        """Serialise to a shareable, versioned JSON-compatible dictionary."""
        # Validate by building the snapshot once before exporting.
        self.snapshot()
        enemy_out = dict(self.enemy_config, defense=self.enemy_stat)
        return dict(
            schema=PLAN_SCHEMA_VERSION,
            kind=PLAN_KIND,
            title=self.title,
            team=sanitize_team_payload(self.team),
            skill_choices={
                str(i): [skill, form] for i, (skill, form) in sorted(self.skill_choices.items())
            },
            enemy=enemy_out,
            field=dict(self.field_config),
            od_level=self.od_level,
            manual_statuses=[
                dict(target=target, status=deepcopy(status))
                for target, status in self.manual_statuses
            ],
            selected_actor_index=self.selected_actor_index,
            mode_options=dict(self.mode_options),
        )

    @classmethod
    def from_dict(cls, data):
        """Construct and validate an :class:`OfflineSession` from a dictionary."""
        if not isinstance(data, dict):
            raise ValueError('试算方案格式无效')
        version = data.get('schema', 1)
        if not isinstance(version, int) or isinstance(version, bool) or version != PLAN_SCHEMA_VERSION:
            raise ValueError(f'不支持的试算方案版本：{version}')
        kind = data.get('kind', PLAN_KIND)
        if kind != PLAN_KIND:
            raise ValueError('文件不是有效的试算方案')
        raw_statuses = data.get('manual_statuses') or []
        statuses = []
        for entry in raw_statuses:
            if isinstance(entry, dict) and 'target' in entry and 'status' in entry:
                status = entry['status']
                check(status, 'Status')
                statuses.append((_normalize_target(entry['target']), status))
            elif isinstance(entry, (list, tuple)) and len(entry) == 2:
                check(entry[1], 'Status')
                statuses.append((_normalize_target(entry[0]), entry[1]))
            else:
                raise ValueError('试算方案中的手动状态格式无效')
        enemy_cfg = dict(data.get('enemy') or {})
        session = cls(
            data.get('team'),
            title=data.get('title', ''),
            skill_choices=data.get('skill_choices'),
            enemy=enemy_cfg,
            enemy_stat=data.get('enemy_stat', enemy_cfg.get('defense')),
            field=data.get('field'),
            od_level=data.get('od_level', 0),
            manual_statuses=statuses,
            selected_actor_index=data.get('selected_actor_index', 0),
            mode_options=data.get('mode_options'),
        )
        session.snapshot()
        return session

    def save(self, path):
        """Atomically write the session as UTF-8 JSON to ``path``."""
        from hbr_data.sync import write_atomic

        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2).encode('utf-8')
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(target, payload)
        return target

    @classmethod
    def load(cls, path):
        """Load and validate an :class:`OfflineSession` from a JSON file."""
        raw = json.loads(Path(path).read_text(encoding='utf-8'))
        return cls.from_dict(raw)
