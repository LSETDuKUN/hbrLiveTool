import json
import unittest
from pathlib import Path
from unittest.mock import patch
from test_statuses import RecordedMemory
from hbr_live_app.statuses import StatusReader
from hbr_live_app.damage_inputs import read_inputs


class DamageInputTests(unittest.TestCase):
    def test_recorded_player_enemy_and_selected_skill(self):
        data=json.loads((Path(__file__).parent/'fixtures/damage_inputs.json').read_text(encoding='utf8'))
        reader=StatusReader(RecordedMemory(data))
        with patch('hbr_live_app.source.members',side_effect=lambda r,p:data['lists'][str(p)]):
            player=read_inputs(reader,data['player'])
            enemy=read_inputs(reader,data['enemy'])
        self.assertEqual(player['stats']['power'],767)
        self.assertEqual(player['stats']['dexterity'],621)
        self.assertEqual(player['token'],0)
        self.assertEqual(player['current_sp'],6)
        self.assertEqual(player['expected_sp'],6)
        self.assertEqual(player['sp_to_consume'],0)
        self.assertEqual(player['reinforced_mode_turn'],3)
        self.assertIn('Passive.Condition_AttackUp11',player['passive_labels'])
        self.assertEqual([p['label'] for p in player['passive_audit']],player['passive_labels'])
        self.assertEqual(enemy['_borderRefParam'],610)
        self.assertEqual(enemy['_defenseRefParam'],610)
        skill=player['selected_skill']
        self.assertEqual(skill['label'],'STezukaSkill02');self.assertEqual(skill['level'],10)
        attack=next(p for p in skill['parts'] if p['Label']=='STezukaSkill02')
        self.assertEqual(attack['MaxPower'],6701.25)
        self.assertEqual(attack['RefParamPower'],1);self.assertEqual(attack['RefParamDexterity'],1)
        self.assertNotIn('target',skill)
