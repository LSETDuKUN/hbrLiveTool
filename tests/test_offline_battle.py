import unittest

from hbr_live_app import offline_battle as ob
from hbr_live_app.damage_autofill import autofill

PAYLOAD = dict(captured_at='2026-11-05T10:00:00', members=[
    dict(style_label=f'S{i}', actor=f'A{i}', style_name=f'N{i}', position=i, dp=100, hp=200,
         dp_max=100, hp_max=200, stats=dict(power=500, dexterity=500, toughness=500, spirit=500,
                                            wisdom=500, luck=500),
         skills=[dict(label=f'S{i}Skill01', name='一', level=3), dict(label=f'S{i}Skill02', name='二', level=1)],
         passives=[dict(label='Passive.X')]) for i in range(6)])


class OfflineBattleTest(unittest.TestCase):
    def enemy(self, **kw):
        return ob.manual_enemy(dp=1000, hp=5000, defense=400, rates=dict(Fire=150, Slash=50), **kw)

    def test_members_become_live_shaped_players(self):
        players = ob.team_players(PAYLOAD, {1: 1})
        self.assertEqual(len(players), 6)
        self.assertEqual(players[0]['combat_inputs']['selected_skill']['label'], 'S0Skill01')
        self.assertEqual(players[1]['combat_inputs']['selected_skill']['label'], 'S1Skill02')
        self.assertEqual(players[1]['combat_inputs']['passive_labels'], ['Passive.X'])
        self.assertEqual(players[2]['actor_position'], 2)
        self.assertNotIn('parts', PAYLOAD['members'][0]['skills'][0])  # payload untouched

    def test_enemy_rates_use_catalog_encoding(self):
        enemy = self.enemy()
        self.assertEqual(enemy['base_resistances'], dict(fire=-50, slash=50))
        self.assertEqual(enemy['combat_inputs']['_defenseRefParam'], 400)
        with self.assertRaises(ValueError):
            ob.manual_enemy(dp=0, hp=0)
        with self.assertRaises(ValueError):
            ob.manual_enemy(hp=10, damage_rate=50)

    def test_manual_statuses_feed_autofill(self):
        player = ob.team_players(PAYLOAD, statuses={0: [ob.manual_status('AttackUp', 50, serial=1),
                                                         ob.manual_status('AttackUp', 30, serial=2),
                                                         ob.manual_status('AttackUp', 20, serial=3)]})[0]
        enemy = self.enemy(statuses=[ob.manual_status('DefenseDown', 25, serial=4),
                                     ob.manual_status('Fragile', 40, serial=5)])
        values = autofill(player, enemy, lookup=lambda label: {})['values']
        # Finite same-kind buffs keep the two strongest, as with live statuses.
        self.assertEqual(values['attack'], 80)
        self.assertEqual(values['defense_down'], 25)
        self.assertEqual(values['fragile'], 40)

    def test_permanent_statuses_add_up(self):
        statuses = [ob.manual_status('AttackUp', v, serial=i, permanent=True) for i, v in enumerate((50, 30, 20))]
        player = ob.team_players(PAYLOAD, statuses={0: statuses})[0]
        values = autofill(player, self.enemy(), lookup=lambda label: {})['values']
        self.assertEqual(values['attack'], 100)

    def test_status_validation(self):
        with self.assertRaises(ValueError):
            ob.manual_status('ResistDown', 10)
        with self.assertRaises(ValueError):
            ob.manual_status('Funnel', 25)
        with self.assertRaises(ValueError):
            ob.manual_status('AttackUp', -5)
        funnel = ob.manual_status('Funnel', 25, count=3)
        self.assertEqual(funnel['values'], dict(rateValueInt=2500, numValue=3))
        self.assertTrue(ob.describe_status(funnel).endswith('3 颗 × 25%'))

    def test_snapshot_shape(self):
        snap = ob.snapshot('s1', PAYLOAD, self.enemy(), od_level=2, field=ob.zone_state('Fire', 30))
        self.assertTrue(snap['connected'])
        self.assertEqual(snap['od_state'], dict(available=True, active=True, level=2))
        self.assertEqual(snap['field_state']['statuses'][0]['values']['rateValueInt'], 13000)
        self.assertEqual(snap['enemies'][0]['address'], ob.ENEMY_ADDRESS)
        self.assertFalse(ob.snapshot('s1', PAYLOAD, self.enemy())['od_state']['active'])


if __name__ == '__main__':
    unittest.main()
