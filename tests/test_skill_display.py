import unittest
from hbr_live_app.skill_effects import preview_effects
from hbr_live_app.events import ActionLedger
from hbr_live_app.history import beneficiary, beneficiary_title
from test_battle import entry


class SkillDisplayTests(unittest.TestCase):
    def test_effects_show_hits_control_and_explicit_raw_power(self):
        text = preview_effects(dict(hit_count=5, target_type='All', parts=[
            dict(skill_type='AttackSkill', power=[2075,24900]),
            dict(skill_type='ConfusionRandom', cond='Condition()')]))
        for value in ('5 Hit', '全体', '资料威力 2075–24900（非实伤）', '混乱（有条件）'):
            self.assertIn(value, text)
        self.assertNotIn('Hit', preview_effects(dict(hit_count=-1, parts=[dict(skill_type='AttackUp')])) )
        self.assertIn('效果未收录', preview_effects({}))

    def test_executed_non_damage_effect_captures_exact_target_style(self):
        action = entry([0], 1)
        action['hits'][0].update(target=9, type=2, index=99, target_name='苍井', target_is_player=True,
                                 target_style_label='EAoi04', target_style_name='风格')
        self.assertEqual(ActionLedger().update([action], {4}), [])
        action['executing'] = True
        result = ActionLedger().update([action], {4})[0]
        self.assertEqual(result['value'], 0)
        self.assertEqual(beneficiary(result)['style_label'], 'EAoi04')
        self.assertEqual(beneficiary_title(result), '苍井 / 风格')
        result['targets'].append(dict(address=10, is_player=True, name='同伴'))
        self.assertIsNone(beneficiary(result))
        self.assertIsNone(beneficiary(dict(actor_id=9, targets=[result['targets'][0]])))
