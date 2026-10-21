import unittest
from hbr_live_app.damage_math import DamageInputs
from hbr_live_app.destruction import simulate_pools
from hbr_live_app.pool_probability import pool_distribution
from hbr_live_app.raw_probability import raw_distribution


class RawProbabilityTests(unittest.TestCase):
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

    def test_overkill_counted_but_dead_target_stops_further_hits(self):
        d=simulate_pools(DamageInputs(base=1000,critical=False),[.5,.5],2,0,4,0,300,0,10)
        self.assertEqual(d['damage'],10)
        self.assertEqual(d['raw_damage'],500)
        self.assertAlmostEqual(raw_distribution(d)['mean'],500,delta=1)
