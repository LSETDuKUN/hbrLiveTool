import unittest
from hbr_live_app.statuses import infer_suppressed_attacks
from hbr_live_app.status_groups import effect_line, group_statuses


def attack(amount, **changes):
    value = dict(label='SpecialStatus.AttackUp', name='攻击力提升',
                 values=dict(amountOnDpDamageInt=amount, amountOnHpDamageInt=amount),
                 duration_kind='count', remaining=1, element_type=0, buff_limit_type=2)
    value.update(changes)
    return value


class SuppressionTests(unittest.TestCase):
    def test_debuff_targets_share_two_slots_and_permanent_is_separate(self):
        for kind in ('DefenseDown','Fragile','ResistDown'):
            with self.subTest(kind=kind):
                states=[]
                for i,amount in enumerate((1000,3000,2000)):
                    states.append(attack(amount,label='SpecialStatus.'+kind,
                        values=dict(amountOnDpDamageInt=-amount,amountOnHpDamageInt=-amount,
                                    rateValueInt=-amount if kind=='ResistDown' else amount),
                        duration_kind='turn',remaining=2,
                        source_effect=dict(condition='IsOverDrive()',target_type='All' if i else 'Single',
                                           target_condition='IsWeakElement()' if kind=='ResistDown' else '')))
                permanent=dict(states[0],duration_kind='permanent')
                infer_suppressed_attacks(states+[permanent])
                self.assertFalse(states[0]['effective'])
                self.assertNotIn('effective',permanent)
                self.assertTrue(all(s.get('effective') is not False for s in states[1:]))
                states[1]['remaining']=0
                infer_suppressed_attacks(states+[permanent])
                self.assertNotIn('effective',states[0])

    def test_debuff_elements_do_not_cover_each_other(self):
        states=[attack(n,label='SpecialStatus.DefenseDown',element_type=e)
                for n,e in ((100,0),(200,0),(300,3))]
        infer_suppressed_attacks(states)
        self.assertTrue(all(s.get('effective') is not False for s in states))

    def test_weaker_count_is_retained_and_returns_after_turn_buff_expires(self):
        low = attack(13575)
        high = attack(31623, duration_kind='turn', remaining=4, buff_limit_type=4)
        states = infer_suppressed_attacks([low, high])
        self.assertEqual(len(states), 2)
        self.assertEqual(low['remaining'], 1)
        self.assertFalse(low['effective'])
        self.assertIn('规则推断', effect_line(low))
        groups, folded = group_statuses(dict(statuses=states))
        self.assertEqual(groups['boost'], [high])
        self.assertEqual(folded, [low])
        infer_suppressed_attacks([low])
        self.assertNotIn('effective', low)
        self.assertEqual(low['remaining'], 1)

    def test_incompatible_or_uncertain_effects_are_not_suppressed(self):
        for changes in [dict(duration_kind='permanent'), dict(element_type=3),
                        dict(element_type=None), dict(pending_add=True),
                        dict(pending_remove=True), dict(remaining=0),
                        dict(source_effect=dict(target_condition='IsWeakElement')),
                        dict(buff_limit_type=2)]:
            with self.subTest(changes=changes):
                low = attack(13575)
                high = attack(31623, duration_kind='turn', remaining=4, buff_limit_type=4)
                high.update(changes)
                infer_suppressed_attacks([low, high])
                self.assertNotIn('effective', low)

    def test_permanent_low_and_crossing_dp_hp_values_are_preserved(self):
        high = attack(31623, buff_limit_type=4)
        low = attack(13575, duration_kind='permanent')
        crossing = attack(13575)
        crossing['values']['amountOnHpDamageInt'] = 40000
        infer_suppressed_attacks([low, crossing, high])
        self.assertTrue(all('effective' not in s for s in [low, crossing, high]))
