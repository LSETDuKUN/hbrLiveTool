import json
import subprocess
import sys
import unittest
from pathlib import Path

from hbr_live_core import schema
from hbr_live_core.schema import SchemaError, check, validate
from hbr_live_core.snapshot import live_snapshot
from hbr_live_core import examples
from hbr_live_app.model import BattleModel
from hbr_live_app import offline_battle as ob

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / 'tests' / 'fixtures'


def autofill_style_pair():
    """Same shapes test_damage_autofill feeds the calculator."""
    player = dict(actor_id=1, statuses_available=True, statuses=[], combat_inputs=dict(
        selected_skill=dict(label='test', name='测试攻击', level=1, parts=[]),
        stats=dict(power=200, dexterity=200, toughness=200, spirit=200, wisdom=200, luck=200)))
    enemy = dict(address=2, name='敌', dp=0, hp=10, statuses_available=True, statuses=[],
                 base_resistances=dict(thunder=-300, stab=50), enemy_progress=dict(damage_rate=250),
                 combat_inputs=dict(_defenseRefParam=100))
    return player, enemy


def fixture_model():
    """Feed recorded enemies/contexts from fixtures through the live model."""
    model = BattleModel()
    model.run_id = 'fixture'
    contexts = [c['context'] for c in json.loads((FIXTURES / 'auto_turn_events.json').read_text(encoding='utf-8'))]
    frames = json.loads((FIXTURES / 'break_and_overkill.json').read_text(encoding='utf-8'))
    player, _ = autofill_style_pair()
    for index, frame in enumerate(frames):
        model.update(dict(enemies=frame['enemies'], events=[], turn_context=contexts[index % len(contexts)],
                          player_states=[dict(player, actor='测试', actor_position=0)],
                          field_state=dict(available=False, statuses=[]), element_gauge=None,
                          od_state=dict(available=False)))
        yield model


class SchemaContractTest(unittest.TestCase):
    def test_offline_snapshot_conforms(self):
        snapshot = examples.offline_snapshot()
        self.assertEqual(validate(snapshot), [])
        self.assertEqual(snapshot['schema_version'], schema.SCHEMA_VERSION)

    def test_live_snapshot_from_fixture_replay_conforms(self):
        count = 0
        for model in fixture_model():
            snapshot = live_snapshot(model, True)
            self.assertEqual(validate(snapshot), [], f'frame {count}')
            json.dumps(snapshot)  # JSON-serialisable
            count += 1
        self.assertGreater(count, 10)

    def test_live_snapshot_keeps_old_shape(self):
        model = next(iter(fixture_model()))
        snapshot = live_snapshot(model, False)
        self.assertFalse(snapshot['connected'])
        player = snapshot['players'][0]
        self.assertEqual(player['name'], '测试')
        self.assertIs(player['inputs'], player['combat_inputs'])
        self.assertTrue(all(e['inputs'] is e.get('combat_inputs', e['inputs']) for e in snapshot['enemies']))
        # Building a snapshot must not mutate the model.
        self.assertNotIn('name', model.players[0])

    def test_inactive_enemies_are_left_out(self):
        model = BattleModel()
        model.update(dict(enemies=[dict(address=1, name='a', dp=0, hp=5), dict(address=2, name='b', dp=0, hp=5)]))
        model.update(dict(enemies=[dict(address=2, name='b', dp=0, hp=3)]))
        self.assertEqual([e['address'] for e in live_snapshot(model, True)['enemies']], [2])

    def test_calculator_shapes_conform(self):
        player, enemy = autofill_style_pair()
        self.assertEqual(validate(player, 'Player'), [])
        self.assertEqual(validate(enemy, 'Enemy'), [])
        for status in [ob.manual_status('AttackUp', 10), ob.manual_status('Funnel', 25, count=3),
                       ob.manual_status('ResistDown', 10, element='Fire'), ob.manual_status('Morale', 2)]:
            self.assertEqual(validate(status, 'Status'), [])
        self.assertEqual(validate(ob.zone_state('Fire', 30), 'FieldState'), [])

    def test_team_payload_conforms(self):
        self.assertEqual(validate(examples.team_payload(), 'TeamPayload'), [])

    def test_example_files_conform(self):
        files = sorted((FIXTURES / 'contract').glob('*.json'))
        self.assertTrue(files)
        for path in files:
            with self.subTest(path=path.name):
                kind = 'TeamPayload' if path.name.startswith('team') else 'Snapshot'
                self.assertEqual(validate(json.loads(path.read_text(encoding='utf-8')), kind), [])

    def test_generated_examples_are_up_to_date(self):
        for name, data in (('offline_snapshot.json', examples.offline_snapshot()),
                           ('team_payload.json', examples.team_payload())):
            with self.subTest(name=name):
                saved = json.loads((FIXTURES / 'contract' / name).read_text(encoding='utf-8'))
                self.assertEqual(saved, json.loads(json.dumps(data)),
                                 'run: python -m hbr_live_core.examples')


class ValidatorTest(unittest.TestCase):
    def snapshot(self):
        return dict(connected=True, run_id=None, execution_revision=0, players=[], enemies=[])

    def test_minimal_snapshot(self):
        self.assertEqual(validate(self.snapshot()), [])

    def test_missing_required_fields(self):
        errors = validate({})
        for key in ('connected', 'run_id', 'execution_revision', 'players', 'enemies'):
            self.assertIn(f'Snapshot.{key}: required field missing', errors)

    def test_wrong_types_are_reported_with_paths(self):
        data = self.snapshot()
        data['players'] = [dict(actor_id=1, statuses=[dict(label=3)])]
        data['enemies'] = [dict(address=1, name='x', dp='10', hp=1)]
        errors = validate(data)
        self.assertIn('Snapshot.players[0].statuses[0].label: expected str, got int', errors)
        self.assertTrue(any(e.startswith('Snapshot.enemies[0].dp: expected') for e in errors))

    def test_bool_is_not_a_number_but_int_is_a_float(self):
        data = self.snapshot()
        data['execution_revision'] = True
        self.assertTrue(validate(data))
        status = dict(label='SpecialStatus.X', values=dict(rateValueInt=1.5, numValue=2))
        self.assertEqual(validate(status, 'Status'), [])

    def test_unknown_fields_are_allowed(self):
        data = self.snapshot()
        data['diagnostic'] = {'anything': [1, 2]}
        data['players'] = [dict(actor_id='offline-0', future_field=1)]
        self.assertEqual(validate(data), [])

    def test_literals_and_optional_null(self):
        self.assertEqual(validate(dict(turn_context=None, **self.snapshot())), [])
        self.assertTrue(validate(dict(target_pool='both'), 'CalcOptions'))
        self.assertEqual(validate(dict(target_pool='dp', transcend='auto'), 'CalcOptions'), [])

    def test_check_raises(self):
        with self.assertRaises(SchemaError) as caught:
            check({'connected': 'yes'})
        self.assertIn('connected', str(caught.exception))
        data = self.snapshot()
        self.assertIs(check(data), data)


class ContractDocumentationTest(unittest.TestCase):
    def test_every_field_is_documented(self):
        doc = (ROOT / 'docs' / 'snapshot-contract.md').read_text(encoding='utf-8')
        missing = [f'{name}.{field}' for name, kind in schema.TYPES.items()
                   for field in schema.fields(kind) if f'`{field}`' not in doc]
        self.assertEqual(missing, [])
        for name in schema.TYPES:
            self.assertIn(name, doc)
        self.assertIn(f'schema_version = {schema.SCHEMA_VERSION}', doc)

    def test_core_never_imports_tkinter(self):
        code = (
            'import sys, hbr_live_core, hbr_live_core.schema, hbr_live_core.snapshot, '
            'hbr_live_core.damage_service, hbr_live_core.offline_session, '
            'hbr_live_core.live_session, hbr_live_core.http_api; '
            'print("tkinter" in sys.modules)'
        )
        out = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.strip()
        self.assertEqual(out, 'False')


if __name__ == '__main__':
    unittest.main()
