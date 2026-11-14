"""Build contract snapshots (see :mod:`hbr_live_core.schema`).

The live builder used to be a closure inside ``App.open_damage_calculator``;
it lives here so that it can be tested and reused without Tk. It takes any
object with the ``BattleModel`` attributes (duck-typed, nothing imported).
"""
from .schema import SCHEMA_VERSION


def stamp(snapshot):
    """Return ``snapshot`` with the contract version set."""
    snapshot['schema_version'] = SCHEMA_VERSION
    return snapshot


def live_snapshot(model, connected):
    """Snapshot of the live battle model for the calculators.

    Top-level player/enemy dicts are fresh, nested values are shared with the
    model (same behaviour as before the move). The sampler replaces nested
    objects rather than mutating them; delivering fully immutable copies is
    roadmap item B4. ``inputs`` is a legacy alias of ``combat_inputs``.
    """
    players = [dict(p, name=p.get('actor'), inputs=p.get('combat_inputs', {}))
               for p in (model.players or [])]
    enemies = [dict(e, inputs=e.get('combat_inputs', {}))
               for e in model.enemies.values() if e.get('active')]
    return stamp(dict(
        connected=bool(connected), run_id=model.run_id,
        execution_revision=model.execution_revision, turn_context=model.turn_context,
        players=players, enemies=enemies, field_state=model.field_state,
        element_gauge=model.element_gauge, od_state=model.od_state))
