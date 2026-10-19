import unittest
from hbr_live_app.destruction import dp_factor, per_hit, simulate_pools
from hbr_live_app.damage_math import DamageInputs
from hbr_live_app.damage_autofill import autofill
from test_damage_autofill import setup


class PoolDamageTests(unittest.TestCase):
    def test_dp_linear_endpoints_both_directions_and_overfill(self):
        self.assertEqual(dp_factor(0,100,1.75,1),1.75)
        self.assertEqual(dp_factor(50,100,1.75,1),1.375)
        self.assertEqual(dp_factor(150,100,1.75,1),1)
        self.assertAlmostEqual(dp_factor(50,100,.6,1.5),1.05)
        with self.assertRaises(ValueError):dp_factor(1,0,1.75,1)

    def test_breaking_hit_discards_overflow_but_increases_dr_after_damage(self):
        i=DamageInputs(base=100,critical=False,chain=25)
        d=simulate_pools(i,[.25]*5,4,12,4,0,300,40,1000)
        self.assertEqual([r['pool'] for r in d['rows']],['dp','dp','hp','hp','hp'])
        self.assertEqual([r['increment'] for r in d['rows']],[0,12,12,12,12])
        self.assertEqual(d['dp_damage'],40)
        self.assertEqual(d['overflow'],10)
        self.assertAlmostEqual(d['hp_damage'],28+31+34)
        self.assertEqual(d['final'],148)

    def test_exact_break_and_last_main_break_allow_extra_hit_on_hp(self):
        i=DamageInputs(base=100,critical=False,chain=25,hp_bonus=100)
        d=simulate_pools(i,[.5,.5,.25],2,4,4,0,300,100,1000)
        self.assertEqual(d['overflow'],0)
        self.assertEqual(d['hp_damage'],54)
        self.assertEqual(d['final'],112)
        self.assertEqual(d['rows'][-1]['kind'],'连击')

    def test_pool_specializations_and_hp_only_status_adjustment(self):
        i=DamageInputs(base=100,critical=False,dp_bonus=100,hp_bonus=50)
        d=simulate_pools(i,[.5,.5],2,4,4,0,300,50,1000,hp_adjustments={'attack':100})
        self.assertEqual(d['overflow'],50)
        self.assertEqual(d['hp_damage'],162)

    def test_breaking_hit_growth_is_capped_and_not_granted_while_shield_remains(self):
        i=DamageInputs(base=100,critical=False,destruction=295)
        d=simulate_pools(i,[1],1,10,4,0,300,50,1000)
        self.assertEqual(d['hp_damage'],0);self.assertEqual(d['overflow'],50)
        self.assertEqual(d['actual_increment'],5);self.assertEqual(d['clipped'],35)
        intact=simulate_pools(i,[1],1,10,4,0,300,101,1000)
        self.assertEqual(intact['actual_increment'],0)

    def test_nonmatching_element_does_not_reduce_existing_super_break(self):
        d=per_hit([.5,.5],2,10,4,0,350,300)
        self.assertEqual(d['final'],350)
        self.assertEqual(d['actual_increment'],0)
        self.assertEqual(d['weights'],[1.75,1.75])
        thunder=per_hit([.5,.5],2,10,4,0,350,600)
        self.assertEqual(thunder['final'],390)

    def test_hp_exhaustion_stops_following_hits(self):
        d=simulate_pools(DamageInputs(base=100,critical=False),[.5,.5],2,4,4,0,300,0,10)
        self.assertEqual(d['hp_damage'],10)
        self.assertEqual(d['rows'][1]['raw_damage'],0)

    def test_autofill_skill_specific_dp_and_element_cap(self):
        p,e,lookup=setup();db=lookup('test')
        db['parts'][0].update(skill_type='AttackByOwnDpRate',value=[1.75,1])
        p.update(dp=50,dp_max=100)
        e['enemy_progress'].update(destruction_coefficient=4,destruction_max=300,damage_rate=350)
        r=autofill(p,e,lookup=lambda _:db,modes=dict(transcend=True,lightning_style=True))
        self.assertTrue(r['dp_scaling']);self.assertEqual(r['values']['health_factor'],1.375)
        self.assertEqual(r['params']['max_dr'],600)
        db['parts'][0]['elements']=[]
        r=autofill(p,e,lookup=lambda _:db,modes=dict(transcend=True,lightning_style=True))
        self.assertEqual(r['params']['max_dr'],300)
        p['combat_inputs']['selected_skill']['parts']=[dict(Label='test',Value1=.6,Value2=1.5)]
        r=autofill(p,e,lookup=lambda _:db)
        self.assertAlmostEqual(r['values']['health_factor'],1.05)

