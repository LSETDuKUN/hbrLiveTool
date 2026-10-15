import json
from pathlib import Path
import unittest
from hbr_live_app.enemy_conditions import evaluate
from hbr_live_app.enemy_prediction import predict
from hbr_live_app.enemy_observations import EnemyObservations


class Conditions(unittest.TestCase):
    def test_example_and_unknown_history(self):
        condition = 'EnemyCount() < 2 && PlayedSkillCount(DiamondEyeballRectusD_Buff02) == 0'
        self.assertTrue(evaluate(condition, dict(enemy_count=1, played_complete=True)))
        self.assertFalse(evaluate(condition, dict(enemy_count=2)))
        self.assertIsNone(evaluate(condition, dict(enemy_count=1)))
        self.assertFalse(evaluate(condition, dict(enemy_count=1, played_counts={'DiamondEyeballRectusD_Buff02': 1})))

    def test_precedence_comparisons_and_reject_code(self):
        self.assertTrue(evaluate('(DpRate() < 0.5 || HpRate() < 0.2) && !IsEnemyCharge()', dict(dp_rate=0.3, charged=False)))
        for text in ['__import__("os").system("echo bad")', 'SomethingUnknown()', 'Foo && true', '1 <', '(' * 500]:
            self.assertIsNone(evaluate(text, {}))
        self.assertTrue(evaluate('true || SomethingUnknown()', {}))
        self.assertFalse(evaluate('false && SomethingUnknown()', {}))


class Branches(unittest.TestCase):
    def setUp(self):
        data = json.loads((Path(__file__).parent/'fixtures/diamond_rules.json').read_text(encoding='utf-8'))
        self.info = dict(patterns=data['pattern'], skills={s['id']: s for s in data['skills']})
        self.live = dict(dp=100, dp_order=0, hp_order=0, dp_pattern=data['pattern']['dp']['l'],
                         hp_pattern='', down=0, charged=False, overridden=False, enemy_count=1,
                         played_complete=True, played_counts={})

    def test_single_enemy_first_buff_and_double_action(self):
        result = predict(self.info, self.live, dict(selecting=True, turn=1))
        self.assertEqual(result['order'], 1)
        self.assertEqual(len(result['branches'][0]['skills']), 2)
        self.assertIn('Madness Mode', result['text'])
        self.assertEqual(result['future'][0]['order'], 2)
        self.assertEqual(self.live['played_counts'], {})

    def test_two_enemies_skip_ineligible_rules(self):
        result = predict(self.info, dict(self.live, enemy_count=2), dict(selecting=True))
        self.assertEqual(result['order'], 3)
        self.assertEqual(result['skipped'], [1, 2])

    def test_weights_conditional_on_eligible_branches(self):
        result = predict(self.info, dict(self.live, enemy_count=2, dp_order=8), dict(selecting=True))
        self.assertEqual([b['share'] for b in result['branches']], [0.75, 0.25])
        self.assertEqual(result['future'], [])

    def test_unknown_counts_keep_fallback_without_fake_probabilities(self):
        result = predict(self.info, dict(self.live, played_complete=False), dict(selecting=True))
        self.assertEqual(result['branches'][0]['status'], 'unknown')
        self.assertIsNone(result['branches'][0]['share'])
        self.assertIsNotNone(result['fallback'])
        self.assertEqual(result['future'], [])

    def test_known_eligible_branch_prevents_impossible_fallthrough(self):
        group = self.info['patterns']['dp']
        group['p'] = [dict(id=1, order=1, weight=50, condition='', skill_list=[46125522]),
                      dict(id=2, order=1, weight=50, condition='Unknown()', skill_list=[46125523]),
                      dict(id=3, order=2, weight=100, condition='', skill_list=[46125527])]
        result = predict(self.info, self.live, dict(selecting=True))
        self.assertEqual(len(result['branches']), 2)
        self.assertIsNone(result['fallback'])
        self.assertTrue(all(b['share'] is None for b in result['branches']))

    def test_phase_change_uses_hp_rules_and_once_is_unknown(self):
        self.info['patterns']['hp'] = dict(l='AfterBreak', p=[dict(id=9, order=1, once=True, weight=100, skill_list=[46125527])])
        result = predict(self.info, dict(self.live, dp=0, hp_pattern='AfterBreak', recent_break=True), dict(selecting=True))
        self.assertEqual(result['phase'], 'hp')
        self.assertEqual(result['branches'][0]['status'], 'unknown')
        self.assertIn('击破', result['note'])


class Observations(unittest.TestCase):
    def test_execution_dedup_pause_and_late_connection(self):
        recorder = EnemyObservations()
        states = [dict(address=1, hp=100, dp=100)]
        progress = dict(dp_order=0, hp_order=0)
        recorder.update(states, [], now=0)
        self.assertTrue(recorder.state(1, progress, dict(selecting=True, turn=1))['played_complete'])
        action = dict(actor=1, actor_is_player=False, address=2, hit_set=3, skill='Buff', executing=True)
        recorder.update(states, [action], now=0.1)
        recorder.update(states, [action], now=0.2)
        self.assertEqual(recorder.state(1, progress, {})['played_counts'], {'Buff': 1})
        recorder.update(states, [], now=0.3)
        recorder.update(states, [action], now=0.4)
        self.assertEqual(recorder.state(1, progress, {})['played_counts'], {'Buff': 2})
        recorder.invalidate()
        self.assertFalse(recorder.state(1, progress, {})['played_complete'])
        self.assertEqual(recorder.state(1, progress, {})['played_counts'], {})
        late = EnemyObservations()
        late.update(states, [], now=0)
        self.assertFalse(late.state(1, progress, dict(selecting=True, turn=3))['played_complete'])

    def test_enemy_count_and_break_updates_independently(self):
        recorder = EnemyObservations()
        recorder.update([dict(address=1, hp=100, dp=50), dict(address=2, hp=100, dp=50)], [], now=0)
        recorder.update([dict(address=1, hp=100, dp=0), dict(address=2, hp=0, dp=0)], [], now=0.1)
        self.assertEqual(recorder.count, 1)
        self.assertTrue(recorder.enemies[1]['recent_break'])
