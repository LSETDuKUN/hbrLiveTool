import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from hbr_live_app.enemy_info import EnemyCatalog, forecast, rules_text, skill_title, skill_effects
from hbr_live_app.enemy_reader import EnemyReader


DATA = json.loads((Path(__file__).parent / 'fixtures/enemy_rules.json').read_text(encoding='utf-8'))


class EnemyInfoTests(unittest.TestCase):
    def test_effects_come_from_parts_and_unnamed_attack_has_readable_title(self):
        skill = dict(label='Boss_Internal_Attack', name='', target_type='All', hit_count=1,
                     parts=[dict(skill_type='AttackSkill', target_type='All', type='Stab', elements=[])])
        self.assertEqual(skill_title(skill), '全体攻击')
        self.assertEqual(skill_effects(skill), '全体 · 攻击 · 突')
        charge = dict(parts=[dict(skill_type='Charge', target_type='Self'),
                             dict(skill_type='AttackUp', target_type='Self', power=[0.5, 0])])
        self.assertIn('攻击提升', skill_effects(charge))
        self.assertNotIn('50%', skill_effects(charge))
        self.assertEqual(skill_effects({}), '')

    def setUp(self):
        self.info = dict(patterns=copy.deepcopy(DATA['pattern']), skills={s['id']: s for s in DATA['skills']})
        self.live = dict(dp=100, dp_pattern='ExoWatcherDefaultHard', hp_pattern='ExoWatcherDefaultHard_break',
                         dp_order=0, hp_order=0, down=0, charged=False, overridden=False)

    def test_two_observed_enemy_turns_match_preview_and_no_stale_commands(self):
        self.assertEqual([r['order'] for r in DATA['observations'] if r['selecting']], [0, 1, 2])
        self.assertEqual([s for r in DATA['observations'] for s in r['executing']],
                         ['ExoWatcherD_AttackSingle01', 'ExoWatcherD_Charge', 'ExoWatcherD_ChargeAttackAll01'])
        first = forecast(self.info, self.live, dict(selecting=True))
        self.assertIn('ExoWatcherD_AttackSingle01 → Power Pool', first['text'])
        self.live.update(dp_order=1, charged=True)
        second = forecast(self.info, self.live, dict(selecting=True))
        self.assertIn('Heavy Burst', second['text'])
        self.assertNotIn('Power Pool', second['text'])
        self.assertFalse(forecast(self.info, self.live, dict(selecting=False))['blink'])

    def test_unknown_loop_down_override_and_mismatch_do_not_flash(self):
        for values in [dict(dp_order=10), dict(down=1), dict(overridden=True), dict(dp_pattern='Other')]:
            with self.subTest(values=values):
                self.assertFalse(forecast(self.info, dict(self.live, **values), dict(selecting=True))['blink'])
        self.assertFalse(forecast(self.info, self.live, None)['blink'])

    def test_random_and_unknown_conditions_are_labeled(self):
        rule = self.info['patterns']['dp']['p'][0]
        self.info['patterns']['dp']['p'].append(dict(rule, skill_list=[46125503]))
        self.assertIn('随机候选', forecast(self.info, self.live, dict(selecting=True))['text'])
        rule['condition'] = 'UnknownGameCondition()'
        result = forecast(self.info, self.live, dict(selecting=True))
        self.assertIn('条件候选', result['text'])
        self.assertFalse(result['blink'])

    def test_exact_identity_only_and_missing_english_is_not_guessed(self):
        with patch('hbr_data.store.Catalog.query', side_effect=[
            ([], [('cn', '42', 'Exact', '中文名')], False),
            ([], [(json.dumps(DATA),)], False),
        ]) as query:
            info = EnemyCatalog().lookup('Exact', 42)
            self.assertEqual(info['names'], [dict(kind='cn', name='中文名')])
            self.assertIn('DP 阶段', info['rules'])
            self.assertEqual(query.call_count, 2)
        with patch('hbr_data.store.Catalog.query', return_value=([], [('cn', '43', 'Exact', '错版本')], False)):
            self.assertEqual(EnemyCatalog().lookup('Exact', 42)['names'], [])

    def test_offline_fallback_and_rule_conditions(self):
        with patch('hbr_data.store.Catalog.query', side_effect=OSError):
            self.assertEqual(EnemyCatalog().lookup('Missing')['rules'], '')
        text = rules_text(DATA)
        self.assertIn('IsEnemyCharge()', text)
        self.assertIn('权重 100', text)
        self.assertIn('不等同于战斗 Turn', text)

    def test_recorded_runtime_layout_reads_derived_progress_and_names(self):
        objects = json.loads((Path(__file__).parent / 'fixtures/enemy_layout.json').read_text(encoding='utf-8'))
        class RecordedMemory:
            def __init__(self):
                self.objects = {int(o['address'], 16): o for o in objects.values()}
                self.values, self.strings = {}, {}
                for address, obj in self.objects.items():
                    self.values[address] = address+1
                    for f in obj['fields']:
                        cell = address+f['offset']
                        if 'object' in f:
                            self.values[cell] = int(f['object']['address'], 16)
                        elif 'text' in f:
                            self.values[cell] = cell+10000
                            self.strings[cell+10000] = f['text']
                        else:
                            self.values[cell] = f.get('value', 0)
            def q(self, address): return self.values.get(address, 0)
            def i(self, address): return self.values.get(address)
            def read(self, address, size): return bytes([int(self.values[address])])
            def string(self, address): return self.strings.get(address)
            def cls(self, address): return self.objects.get(address, {}).get('class')
            def fields(self, address): return self.objects[address]
        memory = RecordedMemory()
        address = int(objects['enemy0']['address'], 16)
        # The derived enemy counters at 608/612 differ from the unused base counters.
        memory.values[address+608] = 1
        memory.values[address+592] = True
        reader = EnemyReader(memory)
        with patch.object(reader.catalog, 'lookup', return_value=dict(self.info, names=[], rules='规则')) as lookup:
            result = reader.sample(dict(address=address, dp=100, hp=500, name='ExoWatcherDefault01'), dict(selecting=True))
        lookup.assert_called_once_with('ExoWatcherDefault01_04', 13402704)
        self.assertEqual(result['enemy_progress']['dp_order'], 1)
        self.assertIn('异度监测之眼', result['names'][0]['name'])
        self.assertIn('Heavy Burst', result['forecast']['text'])
