"""Regenerate the contract example JSON in tests/fixtures/contract/.

    python -m hbr_live_core.examples                    # offline + team examples
    python -m hbr_live_core.examples sessions/<run>.jsonl   # also a live example

The offline and team examples are built from code only. The live example is
replayed from a recorded session (sessions/ is not in Git) through the battle
model, then trimmed so it stays small: lists are shortened, the display-only
forecast is reduced, and nothing outside the game state is kept.
"""
import json
import sys
from pathlib import Path

from .schema import check
from .snapshot import live_snapshot

OUT = Path(__file__).resolve().parent.parent / 'tests' / 'fixtures' / 'contract'

STATS = dict(power=500, dexterity=480, toughness=420, spirit=450, wisdom=430, luck=410)


def team_payload():
    members = []
    for index in range(6):
        members.append(dict(
            style_label=f'Example{index}Style', actor=f'角色{index + 1}', style_name=f'示例风格{index + 1}',
            position=index, dp=1200, hp=3000, dp_max=1200, hp_max=3000, stats=dict(STATS),
            skills=[dict(label=f'Example{index}Skill01', name='示例攻击', level=10),
                    dict(label=f'Example{index}Skill02', name='示例增益', level=5)],
            skills_complete=True,
            passives=[dict(label='Passive.Start_AttackUp01', name='示例被动', condition='', timing='开始时',
                           description='示例：攻击力提升', parts=[], catalog_found=True,
                           classification='示例', runtime={})]))
    return dict(schema=1, captured_at='2026-11-14T15:00:00', context=dict(turn=1), members=members)


def offline_snapshot():
    # Imported lazily: offline_battle is pure logic but lives in the app package for now.
    from hbr_live_app import offline_battle as ob
    enemy = ob.manual_enemy(name='示例敌人', dp=50000, hp=300000, defense=420, damage_rate=150,
                            destruction_coefficient=3, destruction_max=300,
                            rates=dict(Fire=150, Slash=100),
                            statuses=[ob.manual_status('DefenseDown', 30, serial=1),
                                      ob.manual_status('ResistDown', 25, element='Fire', serial=2)])
    statuses = {0: [ob.manual_status('AttackUp', 50, serial=3),
                    ob.manual_status('Funnel', 25, count=3, serial=4)]}
    return ob.snapshot('example', team_payload(), enemy, skill_choices={0: 0}, statuses=statuses,
                       field=ob.zone_state('Fire', 30), od_level=1)


def _trim(snapshot, keep=4):
    snapshot['run_id'] = 'example-live'
    for player in snapshot['players']:
        player['statuses'] = player.get('statuses', [])[:keep]
        inputs = player.get('combat_inputs', {})
        if 'passive_audit' in inputs:
            inputs['passive_audit'] = inputs['passive_audit'][:keep]
            inputs['passive_labels'] = [p['label'] for p in inputs['passive_audit']]
        skill = inputs.get('selected_skill') or {}
        if 'parts' in skill:
            skill['parts'] = skill['parts'][:2]
        player['inputs'] = inputs
    for enemy in snapshot['enemies']:
        enemy['statuses'] = enemy.get('statuses', [])[:keep]
        forecast = enemy.get('forecast')
        if isinstance(forecast, dict):
            enemy['forecast'] = {k: forecast[k] for k in ('text', 'phase', 'pattern', 'order') if k in forecast}
        enemy['inputs'] = enemy.get('combat_inputs', {})
    return snapshot


def live_example(path):
    from hbr_live_app.model import BattleModel
    model, best = BattleModel(), None
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            try:
                packet = json.loads(line)
            except ValueError:
                continue
            if packet.get('kind') == 'start':
                model.run_id = packet.get('run_id')
            if 'enemies' not in packet:
                continue
            model.update(packet)
            # First selection-phase sample with complete player inputs.
            if (model.turn_context or {}).get('selecting') and model.players and all(
                    (p.get('combat_inputs') or {}).get('selected_skill') for p in model.players):
                best = live_snapshot(model, True)
                break
    if best is None:
        raise SystemExit('no selection-phase snapshot with player inputs found')
    return _trim(json.loads(json.dumps(best)))


def write(name, data, kind='Snapshot'):
    check(data, kind)
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / name
    target.write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('wrote', target)


def main(argv):
    write('team_payload.json', team_payload(), 'TeamPayload')
    write('offline_snapshot.json', offline_snapshot())
    if argv:
        write('live_snapshot.json', live_example(argv[0]))


if __name__ == '__main__':
    main(sys.argv[1:])
