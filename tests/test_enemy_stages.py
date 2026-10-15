import json
from pathlib import Path
import unittest
from unittest.mock import patch

from hbr_live_app.enemy_info import forecast, rules_text
from hbr_live_app.enemy_reader import EnemyReader


def fixture(name):
    return json.loads((Path(__file__).parent / 'fixtures' / (name+'.json')).read_text(encoding='utf-8'))


def info(data):
    return dict(patterns=data['pattern'], skills={s['id']: s for s in data['skills']},
                bars=data['bars'], extra_patterns=data['extra_gauge']['pattern'], names=[], rules='')


def live(data, **kwargs):
    return dict(dp=0, dp_pattern=data['pattern']['dp']['l'], hp_pattern=data['pattern']['hp']['l'],
                dp_order=0, hp_order=0, down=0, overridden=False, **kwargs)


class EnemyStageTests(unittest.TestCase):
    def test_shadow_without_dp_uses_main_axis_before_and_after_charge(self):
        data = fixture('shadow_rules')
        state = live(data, charged=False, dp_max=0)
        first = forecast(info(data), state, dict(selecting=True, turn=1))
        self.assertEqual(first['branches'][0]['skills'], ['Pale Beam', 'Demise Domination'])
        state.update(dp_order=1, charged=True)
        second = forecast(info(data), state, dict(selecting=True, turn=2))
        self.assertEqual(second['branches'][0]['skills'], ['Final Verdict'])
        self.assertNotIn('ESHeal', second['text'])

    def test_amon_same_turn_switches_gauge_table_not_hp_table(self):
        data = fixture('amon_rules')
        state = live(data, dp_extra=True, dp_index=0, dp_active_pattern='BigotryGateAmonDefaultHard_DP1')
        state['dp'] = 1600000
        first = forecast(info(data), state, dict(selecting=True, turn=1))
        self.assertEqual(first['branches'][0]['skills'], ['Disaster Shot'])
        state.update(dp=1319836, dp_index=1, dp_active_pattern='BigotryGateAmonDefaultHard_DP2')
        second = forecast(info(data), state, dict(selecting=True, turn=1))
        self.assertEqual(second['branches'][0]['skills'], ['Planar Collapse'])
        self.assertEqual(second['phase'], 'dp')
        self.assertIn('DP 第 2 层', rules_text(data))
        state['dp_active_pattern'] = None
        self.assertNotIn('branches', forecast(info(data), state, dict(selecting=True)))

    def test_empty_break_pattern_keeps_main_axis(self):
        data = fixture('amon_rules')
        state = live(data)
        state['hp_pattern'] = ''
        self.assertEqual(forecast(info(data), state, dict(selecting=True))['phase'], 'dp')

    def test_reader_uses_actual_gauge_index_and_runtime_group(self):
        objects = fixture('amon_layout')
        class Memory:
            def __init__(self):
                self.objects = {int(v['address'], 16): v for v in objects.values()}
                self.values, self.strings, self.classes = {}, {}, {}
                for addr, obj in self.objects.items():
                    self.classes[addr] = obj['class']
                    for f in obj['fields']:
                        cell = addr+f['offset']
                        if 'object' in f:
                            target = int(f['object']['address'], 16)
                            self.values[cell] = target
                            self.classes[target] = f['object']['class']
                        elif 'text' in f:
                            self.values[cell] = cell+10000
                            self.strings[cell+10000] = f['text']
                        else:
                            self.values[cell] = f.get('value', 0)
            def q(self, addr): return self.values.get(addr, 0)
            def i(self, addr): return self.values.get(addr)
            def read(self, addr, size): return bytes([int(self.values[addr])])
            def string(self, addr): return self.strings.get(addr)
            def cls(self, addr): return self.classes.get(addr)
            def fields(self, addr): return self.objects[addr]
        memory = Memory()
        enemy = int(objects['enemy0']['address'], 16)
        memory.values[enemy+92] = 1  # Actual stage after the recorded break.
        memory.values[enemy+300] = 2  # Predicted stage must not move the preview.
        groups = [int(objects[f'enemy0.domainEnemy._commandPatternList[{i}]']['address'],16) for i in range(3)]
        reader = EnemyReader(memory)
        with patch.object(reader.catalog, 'lookup', return_value=info(fixture('amon_rules'))), \
                patch('hbr_live_app.source.members', return_value=groups):
            result = reader.sample(dict(address=enemy, dp=1319836, hp=1166600, name='Amon'),
                                   dict(selecting=True, turn=1))
        self.assertFalse(result['enemy_progress']['overridden'])
        self.assertEqual(result['forecast']['branches'][0]['skills'], ['Planar Collapse'])


if __name__ == '__main__':
    unittest.main()
