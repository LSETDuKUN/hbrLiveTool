import unittest
from hbr_live_app.damage_math import DamageInputs
from hbr_live_app.destruction import simulate_pools
from hbr_live_app.pool_probability import pool_distribution


class PoolProbabilityTests(unittest.TestCase):
    def test_zero_damage_locked_shield_is_a_zero_atom(self):
        d=simulate_pools(DamageInputs(base=0,critical=False),[1],1,0,4,0,300,100,1000,
                         shield=dict(limit_per_turn=1,locked=True,remaining=3,next_dp=None))
        p=pool_distribution(d)
        self.assertEqual(p['atoms'],[(0,1)])
        self.assertEqual(p['mean'],0)

    def test_mean_does_not_depend_on_plot_resolution(self):
        d=self.simulate(50)
        a=pool_distribution(d,bins=16);b=pool_distribution(d,bins=2048)
        self.assertAlmostEqual(a['mean'],b['mean'],places=10)
        self.assertAlmostEqual(a['mean'],80,delta=.001)
        with self.assertRaises(ValueError):pool_distribution(d,bins=0)
    def test_cross_pool_hp_specialization_applies_to_suffix_only(self):
        inputs=DamageInputs(base=100,critical=False,hp_bonus=65)
        # Skill HP +50% and accessory HP +15% add; DP remains unboosted.
        detail=simulate_pools(inputs,[.5,.5],2,0,4,0,300,40)
        self.assertEqual(detail['bases']['dp'],100)
        self.assertEqual(detail['bases']['hp'],165)
        self.assertEqual(detail['rows'][0]['raw_damage'],50)
        self.assertEqual(detail['rows'][1]['raw_damage'],82.5)
        self.assertAlmostEqual(pool_distribution(detail)['mean'],122.5,delta=.01)
        changed=simulate_pools(inputs,[.5,.5],2,0,4,0,300,40,hp_adjustments={'hp_bonus':15})
        self.assertAlmostEqual(changed['bases']['hp'],180)
        self.assertEqual(changed['bases']['dp'],100)

    def simulate(self,dp,hp=None,weights=(.5,.5),**kwargs):
        return simulate_pools(DamageInputs(base=100,critical=False,**kwargs),weights,len(weights),
                              10,4,0,300,dp,hp)

    def test_half_first_hit_break_half_last_hit_atom(self):
        d=pool_distribution(self.simulate(50))
        probs={b['hit']:b['probability'] for b in d['branches']}
        self.assertAlmostEqual(probs[1],.5,delta=.001)
        self.assertAlmostEqual(probs[2],.5,delta=.001)
        self.assertAlmostEqual(dict(d['atoms'])[50],.5,delta=.001)
        # First-hit break: 50 DP + uniform(54,66) HP; otherwise exactly 50 DP.
        self.assertAlmostEqual(d['mean'],80,delta=.05)
        self.assertAlmostEqual(d['low'],50,delta=.001)
        self.assertAlmostEqual(d['high'],114.8,delta=.05)
        self.assertAlmostEqual(d['mass'],1,places=5)

    def test_last_hit_rare_break_and_unbroken_density(self):
        d=pool_distribution(self.simulate(109))
        probs={b['hit']:b['probability'] for b in d['branches']}
        # Sum of two U(45,55): P(sum>=109)=1/200.
        self.assertAlmostEqual(probs[2],.005,delta=.0001)
        self.assertAlmostEqual(probs[None],.995,delta=.0001)
        self.assertAlmostEqual(dict(d['atoms'])[109],.005,delta=.0001)

    def test_hp_cap_has_point_mass_and_kill_probability(self):
        d=pool_distribution(self.simulate(50,60))
        self.assertAlmostEqual(d['kill_probability'],.25,delta=.001)
        self.assertAlmostEqual(dict(d['atoms'])[110],.25,delta=.001)
        self.assertAlmostEqual(d['high'],110,delta=.001)

    def test_certain_break_and_already_broken(self):
        for dp in (40,0):
            detail=self.simulate(dp)
            d=pool_distribution(detail)
            self.assertAlmostEqual(d['mean'],detail['damage'],delta=.05)
            self.assertEqual(len(d['branches']),1)
            self.assertAlmostEqual(d['mass'],1,places=5)

    def test_all_last_hit_or_dead_is_pure_atom(self):
        d=pool_distribution(self.simulate(10,weights=(1,)))
        self.assertEqual(d['atoms'],[(10,1)])
        self.assertEqual(sum(d['density']),0)
        d=pool_distribution(self.simulate(0,0))
        self.assertEqual(d['atoms'],[(0,1)])

    def test_initial_above_cap_and_chain_increment(self):
        detail=simulate_pools(DamageInputs(base=100,critical=False,chain=25,destruction=350),
                              [.5,.5,.25],2,10,4,0,300,40)
        d=pool_distribution(detail)
        self.assertAlmostEqual(d['mean'],40+50*3.5+25*3.5,delta=.1)
