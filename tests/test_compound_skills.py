import json
from pathlib import Path
import unittest
from unittest.mock import patch
from hbr_data.skill_tree import effects,resolve,roots
from hbr_data.details import skill_detail
from hbr_live_app.effect_preview import proposals
from hbr_live_app.effect_math import EffectInputs,calculate_effect
from hbr_live_app.effect_passives import enhancements
from hbr_live_app.damage_autofill import autofill

DATA=json.loads((Path(__file__).parent/'fixtures/compound_skills.json').read_text(encoding='utf-8'))


def actors(label):
    return dict(actor_position=0,dp=100,dp_max=100,statuses=[],combat_inputs=dict(
        stats=dict(power=400,dexterity=400,wisdom=300,luck=300),selected_skill=dict(label=label,level=10))),dict(
        statuses=[],combat_inputs={'_defenseRefParam':150})


class CompoundTests(unittest.TestCase):
    def test_nanami_two_attack_pools_and_resonance(self):
        p,e=actors('NNanaseSkill52');passive=DATA['resonance']
        p['combat_inputs']['passive_audit']=[passive]
        rows=proposals(p,e,lookup=DATA.get)
        self.assertEqual(len(rows),2)
        self.assertIn('普通加攻',rows[0]['title']);self.assertIn('雷加攻',rows[1]['title'])
        self.assertEqual(rows[0]['values']['growth_max'],.02)
        self.assertEqual(rows[1]['values']['growth_max'],0)
        for row in rows:self.assertEqual(row['values']['enhancement'],20)
        p['dp']=49
        for row in proposals(p,e,lookup=DATA.get):self.assertEqual(row['values']['enhancement'],0)

    def test_resonance_runtime_lookup_and_no_double_count(self):
        p,e=actors('NNanaseSkill52');passive=DATA['resonance']
        from hbr_live_app.passive_audit import audit_entry
        with patch('hbr_live_app.passive_audit.passive_record',return_value=passive):
            p['combat_inputs']['passive_audit']=[audit_entry(passive['label'])]
        p['statuses']=[dict(label='SpecialStatus.GiveAttackBuffUp',source=passive['label'],values={'rateValueInt':2000},source_effect={'condition':'DpRate()>=0.5'})]
        for row in proposals(p,e,lookup=DATA.get):self.assertEqual(row['values']['enhancement'],20)

    def test_od_branch_and_attached_debuffs_keep_own_growth(self):
        p,e=actors('FMikotoSkill51Ev1')
        for od in (False,True):
            rows=proposals(p,e,modes={'od_active':od},lookup=DATA.get)
            self.assertEqual(len(rows),2)
            for row in rows:
                self.assertEqual(row['values']['growth_max'],0)
                self.assertIn('= 是' if od else '= 否',row['title'])
        unknown=proposals(p,e,lookup=DATA.get)
        self.assertEqual(len(unknown),4)

    def test_damage_uses_same_od_branch(self):
        for od,power in [(True,14250),(False,10890)]:
            p,e=actors('FMikotoSkill51')
            out=autofill(p,e,lookup=DATA.get,modes={'od_active':od})
            self.assertEqual(out['params']['max_power'],power)
        self.assertFalse(resolve(DATA['FMikotoSkill51'],{})['parts'])

    def test_library_one_root_with_nested_condition_details(self):
        root=DATA['FMikotoSkill51Ev1']
        self.assertEqual(len(list(roots(root))),1)
        detail=skill_detail(root)
        self.assertGreater(len(detail.effects),4)
        self.assertTrue(all('IsOverDrive' in effect.condition for effect in detail.effects))
        self.assertEqual(root['parts'][0]['skill_type'],'SkillCondition')

    def test_switch_branches_are_distinct_and_never_guessed(self):
        skill={'parts':[{'skill_type':'SkillSwitch','strval':[DATA['NNanaseSkill52'],DATA['STezukaSkill02']]}]}
        self.assertEqual(len(list(effects(skill))),6)
        self.assertEqual(resolve(skill)['parts'],[])
