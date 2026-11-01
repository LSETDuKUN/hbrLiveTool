import unittest
from unittest.mock import patch
from hbr_live_app.effect_preview import proposals
from hbr_live_app.effect_math import EffectInputs,calculate_effect

class CommandEffectTests(unittest.TestCase):
    def test_fixed_command_buff_accepts_enhancement_without_missing_parameters(self):
        player=dict(actor_id=1,combat_inputs=dict(selected_skill=dict(label='command')),statuses=[
            dict(label='SpecialStatus.GiveAttackBuffUp',values=dict(rateValueInt=2000))])
        skill=dict(label='command',parts=[dict(label='NNanaseCommandBuff',skill_type='AttackUpIncludeNormal')])
        with patch('hbr_live_app.effect_preview.owned_audit',return_value=[]),patch('hbr_live_app.effect_passives.enhancements',return_value=(0,[])):
            rows=proposals(player,{},lookup=lambda _:skill)
        self.assertEqual(len(rows),1)
        values=rows[0]['values']
        self.assertEqual(values['minimum'],15)
        self.assertEqual(values['maximum'],15)
        self.assertAlmostEqual(calculate_effect(EffectInputs(**values))['final'],18)
