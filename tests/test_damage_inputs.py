import json
import unittest
from pathlib import Path
from unittest.mock import patch
from test_statuses import RecordedMemory
from hbr_live_app.statuses import StatusReader
from hbr_live_app.damage_inputs import read_inputs


class DamageInputTests(unittest.TestCase):
    def test_overwrite_keeps_effective_identity_but_uses_selected_base_name(self):
        from unittest.mock import Mock
        from hbr_live_app.damage_inputs import read_selection
        r=Mock()
        props={(1,'frontSkillList'):2,(1,'selectedCommandIndex'):0,
               (3,'domainSkill'):4,(3,'domainSkillOverwrite'):5,(3,'skillLevel'):10}
        fields={(4,'master'):6,(5,'master'):7,(6,'Label'):'AccessorySkillHealSp01',
                (6,'Name'):'点数援助',(7,'Label'):'SkillOverwrite.Karerin.HealCommon01'}
        r.prop.side_effect=lambda a,n:props.get((a,n))
        r.get.side_effect=lambda a,n:fields.get((a,n))
        r.r.cls.side_effect=lambda a:{2:'List`1',3:'BattleSkill'}.get(a)
        with patch('hbr_live_app.source.members',return_value=[3]):
            selected=read_selection(r,1)['selected_skill']
        self.assertEqual(selected['name'],'点数援助')
        self.assertEqual(selected['label'],'SkillOverwrite.Karerin.HealCommon01')
        self.assertEqual(selected['base_label'],'AccessorySkillHealSp01')
        fields[(7,'Name')]='真正的新技能名'
        with patch('hbr_live_app.source.members',return_value=[3]):
            self.assertEqual(read_selection(r,1)['selected_skill']['name'],'真正的新技能名')
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
