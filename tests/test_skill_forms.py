import unittest

from hbr_live_app.skill_forms import forms, with_form

CATALOG = {
    'KSkill08': dict(label='KSkill08', name='红尖晶石', parts=[dict(
        label='KSkill08', skill_type='SkillSwitch', strval=[
            dict(label='KSkill08a', name='红尖晶石', parts=[dict(label='KSkill08a_1', skill_type='AttackSkill')]),
            dict(label='KSkill08b', name='堇青石', parts=[dict(label='KSkill08b_1', skill_type='AttackSkill')])])]),
    'Plain': dict(label='Plain', parts=[dict(label='Plain', skill_type='AttackSkill')]),
}
lookup = lambda label: CATALOG.get(label, {})


def player(label, parts=()):
    inputs = dict(selected_skill=dict(label=label, name='红尖晶石', level=5, parts=list(parts)))
    return dict(actor_id=1, combat_inputs=inputs, inputs=inputs)


class SkillFormsTest(unittest.TestCase):
    def test_lists_switch_children(self):
        self.assertEqual([(l, n) for l, n, _ in forms('KSkill08', lookup)],
                         [('KSkill08a', '红尖晶石'), ('KSkill08b', '堇青石')])
        self.assertEqual(forms('Plain', lookup), [])

    def test_manual_choice_replaces_label_and_keeps_level(self):
        resolved, note = with_form(player('KSkill08', [dict(Label='KSkill08a_1')]), 1, lookup)
        selected = resolved['combat_inputs']['selected_skill']
        self.assertEqual(selected['label'], 'KSkill08b')
        self.assertEqual(selected['level'], 5)
        self.assertEqual(selected['switch_parent'], 'KSkill08')
        self.assertEqual(selected['parts'], [])  # live parts of the other form are dropped
        self.assertIn('堇青石', note)

    def test_auto_detects_from_live_parts(self):
        resolved, _ = with_form(player('KSkill08', [dict(Label='KSkill08b_1')]), None, lookup)
        self.assertEqual(resolved['combat_inputs']['selected_skill']['label'], 'KSkill08b')

    def test_undetectable_form_is_reported_not_guessed(self):
        original = player('KSkill08')
        resolved, note = with_form(original, None, lookup)
        self.assertIs(resolved, original)
        self.assertIn('未能自动判断', note)

    def test_plain_skill_untouched(self):
        original = player('Plain')
        self.assertEqual(with_form(original, 0, lookup), (original, None))


if __name__ == '__main__':
    unittest.main()
