"""Snapshot contract between the reading/calculation core and any UI.

The snapshot dictionary has been the de-facto interface between the memory
reader, the offline session builder and the calculator windows for a while;
this module only writes it down. Field names are the existing ones and are
**never renamed here** -- fields that are observations of game memory (and may
therefore be absent or ``None`` on another game version, after a failed read or
in an offline session) are typed as optional.

The TypedDicts below are the single source of truth: :func:`validate` walks
their annotations, and ``tests/test_schema.py`` checks that every field is
described in ``docs/snapshot-contract.md``.

Validation rules:

* required keys must be present and every known key must have the right type;
* unknown keys are allowed (producers may add diagnostics; consumers must
  ignore what they do not understand);
* ``bool`` is not accepted where a number is expected, ``int`` is accepted where
  a ``float`` is expected (JSON has a single number type).

This module must stay free of UI imports.
"""
# No ``from __future__ import annotations``: TypedDict needs evaluated
# annotations to see Required[...] at runtime.
import types
import typing
from typing import Any, Literal, Required, TypedDict, Union

SCHEMA_VERSION = 1

Number = Union[int, float]
#: Memory addresses are ints in live sessions and strings in offline ones.
Identity = Union[int, str]


# ---- shared ------------------------------------------------------------------
class Status(TypedDict, total=False):
    """One buff/debuff/field effect, live (memory) or manual (offline)."""
    label: Required[str]                 # e.g. 'SpecialStatus.AttackUp'
    name: str
    value: str                           # display text
    values: dict[str, Number]            # rateValueInt / amountOnDpDamageInt / numValue ...
    source: str                          # skill or passive label that applied it
    source_name: str
    source_effect: dict[str, Any]        # catalog effect description (may be {})
    element_type: int | None
    element_key: str | None              # 'Fire' / 'Ice' / ... or None
    element_name: str | None
    buff_limit_type: int | None
    remaining: int | None                # None for permanent manual statuses
    duration: str                        # display text
    duration_kind: str                   # 'turn' / 'count' / 'permanent' / ...
    hidden: bool
    pending_add: bool
    pending_remove: bool
    # Set by rule inference (statuses.infer_suppressed_attacks), not by the game.
    effective: bool
    effective_basis: str
    effective_reason: str
    manual: bool                         # True for offline, user-entered statuses


class SkillRef(TypedDict, total=False):
    """Observed identity of an equipped skill (no shared catalog data)."""
    label: str
    base_label: str
    name: str
    level: int


class SelectedSkill(TypedDict, total=False):
    """The skill currently selected in the command menu (or chosen offline).

    May be ``{}`` when nothing is selected. ``parts`` holds raw runtime parts
    whose keys are the game's own (``Label``, ``Power``, ``MaxPower`` ...).
    """
    label: str
    base_label: str
    name: str | None
    name_source: str
    level: int
    base_sp_cost: int | None
    hit_count: int
    parts: list[dict[str, Any]]
    # Added when a switch-skill form is resolved (skill_forms.with_form).
    switch_parent: str
    switch_index: int


class PassiveAudit(TypedDict, total=False):
    label: Required[str]
    name: str
    condition: str
    timing: str
    description: str
    parts: list[dict[str, Any]]
    catalog_found: bool
    classification: str
    runtime: dict[str, Any]


class PlayerInputs(TypedDict, total=False):
    """``combat_inputs`` of a player; every field is an observation."""
    unavailable: bool                    # True when the whole read failed
    stats: dict[str, Number]             # power / dexterity / toughness / spirit / wisdom / luck
    token: int
    reinforced_mode_turn: int | None
    current_sp: int | None
    expected_sp: int | None
    sp_to_consume: int | None
    passive_labels: list[str]
    passive_audit: list[PassiveAudit]
    equipped_skills: list[SkillRef]
    selected_skill: SelectedSkill


class Player(TypedDict, total=False):
    actor_id: Required[Identity]         # live: memory address; offline: 'offline-<i>'
    actor_position: int | None           # 0-2 front line, 3-5 back line
    actor: str | None                    # character name
    name: str | None                     # display name used by calculator lists
    style_label: str | None
    style_name: str | None
    dp: Number | None
    hp: Number | None
    dp_max: Number | None
    hp_max: Number | None
    expected_dp: Number | None
    expected_hp: Number | None
    mode_count: int
    another_form: bool
    statuses: list[Status]
    statuses_available: bool
    combat_inputs: PlayerInputs
    inputs: PlayerInputs                 # legacy alias of combat_inputs


# ---- enemies -----------------------------------------------------------------
class EnemyInputs(TypedDict, total=False):
    stats: dict[str, Number]
    token: int
    _defenseRefParam: Number | None      # the boss stat used by damage/debuff differences
    _borderRefParam: Number | None


class ShieldState(TypedDict, total=False):
    index: int | None
    total: int | None
    remaining: int | None
    broken: int | None
    breaks_this_turn: int | None
    limit_per_turn: int | None
    locked: bool | None
    complete: bool
    next_dp: int | None
    turn: int | None
    source: str
    capacity_source: str


class EnemyProgress(TypedDict, total=False):
    damage_rate: Number                  # destruction %, >= 100
    down: int
    destruction_coefficient: Number
    destruction_max: Number
    dp: int
    dp_max: int
    hp_max: int
    dp_rate: Number
    hp_rate: Number
    dp_index: int
    dp_order: int
    hp_order: int
    dp_pattern: str
    hp_pattern: str
    dp_active_pattern: str
    dp_extra: bool
    hp_extra: bool
    charged: bool
    charge_step: int
    enemy_count: int
    enemy_executing: bool
    enemy_pending: bool
    recent_break: bool
    overridden: bool
    last_actions: list[str]
    played_counts: dict[str, int]
    observed_played_counts: dict[str, int]
    played_complete: bool
    played_source: str
    shield: ShieldState | None


class EnemyName(TypedDict, total=False):
    kind: str                            # 'cn' / 'en' / 'internal'
    name: str


class Enemy(TypedDict, total=False):
    address: Required[Identity]          # live: memory address; offline: 'offline-enemy'
    dp: Required[Number]
    hp: Required[Number]
    name: Required[str]
    active: bool
    dp_max: Number | None
    hp_max: Number | None
    enemy_id: int
    enemy_label: str
    names: list[EnemyName]
    action_rules: str
    base_resistances: dict[str, Any] | None     # element/weapon -> int, plus absorb_element_list / ignore_penetration
    enemy_progress: EnemyProgress
    forecast: dict[str, Any]             # display-only action forecast; not a calculation input
    statuses: list[Status]
    statuses_available: bool
    combat_inputs: EnemyInputs
    inputs: EnemyInputs                  # legacy alias of combat_inputs
    # Added by the live model (model.BattleModel.update).
    dp_reference: Number
    hp_reference: Number
    dp_change: Number
    hp_change: Number
    dp_rises: int
    hp_rises: int


# ---- battle-wide state -------------------------------------------------------
class FrontlineSlot(TypedDict, total=False):
    actor_id: Identity
    actor: str
    position: int


class TurnContext(TypedDict, total=False):
    selecting: bool                      # True while in command selection
    turn: int | None
    phase: str
    phase_count: int
    command_count: int
    command_visit: int
    additional: bool
    extra: bool
    extra_turn: int
    extra_actor_ids: list[Identity] | None
    od: bool
    od_level: int | None
    od_activation: int
    od_before_enemy: bool | None
    bonus: int
    bonus_max: int
    frontline: list[FrontlineSlot] | None
    fsm_address: str
    state_address: str


class FieldState(TypedDict, total=False):
    available: bool
    statuses: Required[list[Status]]


class ElementGauge(TypedDict, total=False):
    value: int
    maximum: int
    element: int | None
    name: str
    full: Required[bool]


class OdState(TypedDict, total=False):
    available: bool
    active: bool
    level: int | None
    points: int
    percent: Number
    consumed_points: int
    last_activated_level: int


class Snapshot(TypedDict, total=False):
    """What every calculator receives: ``snapshot() -> Snapshot``."""
    schema_version: int
    connected: Required[bool]
    offline: bool
    run_id: Required[str | None]
    execution_revision: Required[int]
    turn_context: TurnContext | None
    players: Required[list[Player]]
    enemies: Required[list[Enemy]]
    field_state: FieldState | None
    element_gauge: ElementGauge | None
    od_state: OdState | None


# ---- saved teams -------------------------------------------------------------
class TeamMember(TypedDict, total=False):
    style_label: Required[str]
    actor: str | None
    style_name: str | None
    position: int | None
    dp: Number | None
    hp: Number | None
    dp_max: Number | None
    hp_max: Number | None
    stats: Required[dict[str, Number]]
    skills: list[SkillRef]
    skills_complete: bool
    passives: list[PassiveAudit]


class TeamPayload(TypedDict, total=False):
    """Versioned JSON stored per team in data/team_builds.sqlite3."""
    schema: Required[int]
    captured_at: str
    context: dict[str, Any]
    members: Required[list[TeamMember]]


# ---- calculation service (DRAFT, finalised with roadmap item B2) ----------------
Toggle = Literal['auto', 'on', 'off']


class CalcOptions(TypedDict, total=False):
    """Every switch the damage calculator exposes, as plain data."""
    transcend: Toggle
    high_boost: Toggle
    transcend_element: str | None        # None = detect; 'Fire' / 'Ice' / ...
    form_index: int | None               # None = detect the switch-skill form
    enemy_stat: Number | None            # shared boss stat override; None = read value
    target_pool: Literal['auto', 'dp', 'hp']
    critical: bool
    penetration_critical: bool
    absorbed: bool
    damage_metric: Literal['raw', 'applied']


class CalcRequest(TypedDict, total=False):
    actor_id: Required[Identity]
    enemy_address: Required[Identity]
    options: CalcOptions
    overrides: dict[str, str | Number]   # user-edited factors, validated by the core


class CalcResult(TypedDict, total=False):
    ok: Required[bool]
    errors: dict[str, str]               # field -> message
    damage: Number | None                # deterministic (no variance) damage
    mean: Number | None
    low: Number | None                   # central 90% interval
    high: Number | None
    destruction_start: Number | None
    destruction_end: Number | None
    notes: list[str]


#: Top-level contract types, by name.
TYPES = {t.__name__: t for t in (
    Snapshot, Player, Enemy, Status, SelectedSkill, PlayerInputs, EnemyInputs, EnemyProgress,
    TurnContext, FieldState, ElementGauge, OdState, TeamPayload, TeamMember,
    CalcOptions, CalcRequest, CalcResult)}


# ---- validation ----------------------------------------------------------------
class SchemaError(ValueError):
    def __init__(self, errors):
        self.errors = list(errors)
        head = '; '.join(self.errors[:5])
        more = f' (+{len(self.errors) - 5} more)' if len(self.errors) > 5 else ''
        super().__init__(head + more)


_hints_cache: dict[type, dict[str, Any]] = {}


def _hints(kind):
    if kind not in _hints_cache:
        _hints_cache[kind] = typing.get_type_hints(kind)
    return _hints_cache[kind]


def _describe(tp):
    if tp is type(None):
        return 'null'
    return getattr(tp, '__name__', None) or str(tp).replace('typing.', '')


def _check(value, tp, path, errors):
    if tp is Any:
        return
    if tp is None or tp is type(None):
        if value is not None:
            errors.append(f'{path}: expected null, got {type(value).__name__}')
        return
    origin = typing.get_origin(tp)
    if origin is Union or origin is types.UnionType:
        for option in typing.get_args(tp):
            trial = []
            _check(value, option, path, trial)
            if not trial:
                return
        errors.append(f'{path}: expected {_describe(tp)}, got {type(value).__name__}')
        return
    if origin is Literal:
        if value not in typing.get_args(tp):
            errors.append(f'{path}: expected one of {typing.get_args(tp)}, got {value!r}')
        return
    if origin is list:
        if not isinstance(value, list):
            errors.append(f'{path}: expected list, got {type(value).__name__}')
            return
        (item,) = typing.get_args(tp) or (Any,)
        for index, element in enumerate(value):
            _check(element, item, f'{path}[{index}]', errors)
        return
    if origin is dict:
        if not isinstance(value, dict):
            errors.append(f'{path}: expected object, got {type(value).__name__}')
            return
        key_type, item = typing.get_args(tp) or (str, Any)
        for key, element in value.items():
            if key_type is str and not isinstance(key, str):
                errors.append(f'{path}: non-string key {key!r}')
            _check(element, item, f'{path}.{key}', errors)
        return
    if typing.is_typeddict(tp):
        _check_typeddict(value, tp, path, errors)
        return
    if tp is float:
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif tp is int:
        ok = isinstance(value, int) and not isinstance(value, bool)
    else:
        ok = isinstance(value, tp)
    if not ok:
        errors.append(f'{path}: expected {_describe(tp)}, got {type(value).__name__}')


def _check_typeddict(value, kind, path, errors):
    if not isinstance(value, dict):
        errors.append(f'{path}: expected {kind.__name__} object, got {type(value).__name__}')
        return
    for key in sorted(kind.__required_keys__):
        if key not in value:
            errors.append(f'{path}.{key}: required field missing')
    for key, tp in _hints(kind).items():
        if key in value:
            _check(value[key], tp, f'{path}.{key}', errors)


def validate(data, kind=Snapshot, path=None):
    """Return a list of human-readable problems (empty when ``data`` conforms)."""
    if isinstance(kind, str):
        kind = TYPES[kind]
    errors = []
    _check(data, kind, path or getattr(kind, '__name__', 'value'), errors)
    return errors


def check(data, kind=Snapshot):
    """Raise :class:`SchemaError` unless ``data`` conforms; return ``data``."""
    errors = validate(data, kind)
    if errors:
        raise SchemaError(errors)
    return data


def fields(kind):
    """``{field: (type description, required)}`` -- used by docs and tests."""
    if isinstance(kind, str):
        kind = TYPES[kind]
    return {key: (_describe(tp), key in kind.__required_keys__) for key, tp in _hints(kind).items()}
