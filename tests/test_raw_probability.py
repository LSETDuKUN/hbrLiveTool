import unittest
from hbr_live_app.damage_math import DamageInputs
from hbr_live_app.destruction import simulate_pools
from hbr_live_app.pool_probability import pool_distribution
from hbr_live_app.raw_probability import raw_distribution


class RawProbabilityTests(unittest.TestCase):
    def test_no_possible_break_matches_single_pool_curve_point_for_point(self):
        from hbr_live_app.damage_probability import distribution
        weights=[.1,.2,.3,.4]
        d=simulate_pools(DamageInputs(base=1000,critical=False,hp_bonus=500),weights,4,10,4,0,600,5000,10000)
        result=raw_distribution(d);single=distribution(weights)
        self.assertEqual(result['method'],'convolution')
        self.assertEqual(result['x'],[x*1000 for x in single['x']])
        self.assertEqual(result['density'],[p/1000 for p in single['density']])
        self.assertEqual(result['low'],single['low']*1000)
        self.assertEqual(result['high'],single['high']*1000)

    def test_break_branch_preserves_conditional_prefix_mean_and_variance(self):
        # K=2: U(45,50)+U(45,55); K=1: U(50,55)+U(54,66).
        # Equal branch mass: mean=105, variance=68.5. Replacing the breaking
        # prefix with the shield amount would destroy both moments.
        d=simulate_pools(DamageInputs(base=100,critical=False),[.5,.5],2,10,4,0,300,50,10000)
        r=raw_distribution(d)
        self.assertAlmostEqual(r['mass'],1,places=6)
        self.assertAlmostEqual(r['mean'],105,delta=.02)
        variance=sum((x-r['mean'])**2*p*r['step'] for x,p in zip(r['x'],r['density']))
        self.assertAlmostEqual(variance,68.5,delta=.1)

    def test_random_early_kill_keeps_all_hits(self):
        # Both hits still contribute after a lethal first hit.
        d=simulate_pools(DamageInputs(base=100,critical=False),[.5,.5],2,0,4,0,100,0,50)
        r=raw_distribution(d)
        self.assertAlmostEqual(r['mean'],100,delta=.02)
        variance=sum((x-r['mean'])**2*p*r['step'] for x,p in zip(r['x'],r['density']))
        self.assertAlmostEqual(variance,100/6,delta=.15)
        self.assertGreater(r['high'],90)

    def test_complex_branch_grid_converges(self):
        d=simulate_pools(DamageInputs(base=100,critical=False,hp_bonus=50),[.1]*10,10,10,4,20,300,40,100)
        a=raw_distribution(d);b=raw_distribution(d,bins=8192)
        for key in ('mean','low','high'):self.assertAlmostEqual(a[key],b[key],delta=.05)
        self.assertAlmostEqual(sum(a['density'])*a['step'],1,places=7)

    def test_grid_convolution_matches_direct_discrete_convolution(self):
        from hbr_live_app.probability_grid import convolve
        for a,b in zip(convolve([.25,.75],[.2,.2,.6]),[.05,.2,.3,.45]):self.assertAlmostEqual(a,b,places=12)

    def test_last_shield_does_not_cap_raw_damage(self):
        d=simulate_pools(DamageInputs(base=2000000,critical=False),[1],1,0,4,0,300,1600000,1000000,
                         shield=dict(limit_per_turn=1,locked=False,remaining=1))
        self.assertEqual(d['damage'],1600000)
        self.assertEqual(d['raw_damage'],2000000)
        self.assertEqual(pool_distribution(d)['atoms'],[(1600000,1)])
        p=raw_distribution(d)
        self.assertGreater(p['low'],1600000)
        self.assertAlmostEqual(p['mean'],2000000,delta=1500)
        self.assertFalse(p['atoms'])

    def test_locked_dp_still_produces_raw_hits(self):
        d=simulate_pools(DamageInputs(base=1000,critical=False),[.5,.5],2,10,4,0,300,1,1000,
                         shield=dict(limit_per_turn=1,locked=True,remaining=2))
        self.assertEqual(d['damage'],0)
        p=raw_distribution(d)
        self.assertAlmostEqual(p['mean'],1000,delta=1)
        self.assertGreater(p['low'],900)

    def test_random_break_retains_prefix_correlation(self):
        d=simulate_pools(DamageInputs(base=100,critical=False),[.5,.5],2,10,4,0,300,50)
        # Half the paths gain 20% DR for the second 50-damage hit.
        self.assertAlmostEqual(raw_distribution(d)['mean'],105,delta=.15)
        self.assertAlmostEqual(pool_distribution(d)['mean'],80,delta=.01)

    def test_overkill_keeps_further_hits(self):
        d=simulate_pools(DamageInputs(base=1000,critical=False),[.5,.5],2,0,4,0,300,0,10)
        self.assertEqual(d['damage'],10)
        self.assertEqual(d['raw_damage'],1000)
        self.assertAlmostEqual(raw_distribution(d)['mean'],1000,delta=1)

    def test_death_keeps_chain_damage_and_rate_growth(self):
        d=simulate_pools(DamageInputs(base=1000,critical=False,chain=75),[1,.25,.25,.25],1,10,4,0,300,50,10)
        self.assertEqual([r['raw_damage'] for r in d['rows']],[1000,350,375,400])
        self.assertEqual([r['after'] for r in d['rows']],[140,150,160,170])
        self.assertEqual(d['hp_damage'],10)
        self.assertAlmostEqual(raw_distribution(d)['mean'],2125,delta=1)
