import unittest
from hbr_live_app.shield_layers import ShieldLayers
from hbr_live_app.destruction import simulate_pools
from hbr_live_app.pool_probability import pool_distribution
from hbr_live_app.damage_math import DamageInputs


class ShieldTests(unittest.TestCase):
    def test_turn_not_extra_or_od_resets_limit(self):
        tracker=ShieldLayers();bars={'main':[{'kind':'dp','v':100}]*3}
        def sample(i,dp,turn,t,**kw):
            return tracker.update(1,'BigotryGateAmonDefault01_04',dict(dp_index=i,dp=dp),bars,dict(turn=turn,**kw),t)
        self.assertFalse(sample(0,100,1,0)['locked'])
        self.assertTrue(sample(0,0,1,.1)['locked'])
        s=sample(1,100,1,.2,extra=True);self.assertEqual(s['breaks_this_turn'],1)
        s=sample(1,1,1,.3,od=True,bonus=1);self.assertTrue(s['locked']);self.assertEqual(s['remaining'],2)
        self.assertFalse(sample(1,1,2,.4)['locked'])
        self.assertEqual(sample(2,100,2,.5)['broken'],2)
        self.assertTrue(sample(2,100,2,.6)['locked'])
        self.assertFalse(sample(2,100,3,.7)['locked'])
        self.assertEqual(sample(3,0,3,.8)['remaining'],0)

    def test_late_join_gap_and_enemy_isolation(self):
        tracker=ShieldLayers();bars={'main':[{'kind':'dp','v':100}]*3}
        def sample(a,i,turn,t):return tracker.update(a,'BigotryGateAmonDefault',dict(dp_index=i,dp=100),bars,dict(turn=turn),t)
        self.assertIsNone(sample(1,1,2,0)['locked'])
        self.assertFalse(sample(2,0,2,.1)['locked'])
        self.assertFalse(sample(1,1,3,.1)['locked'])
        self.assertFalse(sample(1,1,3,2)['locked'])
        self.assertFalse(sample(1,1,3,2.1)['locked'])
        self.assertFalse(sample(1,1,4,2.2)['locked'])

    def run_damage(self,dp,locked=False,remaining=3,next_dp=100):
        shield=dict(limit_per_turn=1,locked=locked,remaining=remaining,next_dp=next_dp)
        return simulate_pools(DamageInputs(base=1000,critical=False,hp_bonus=50),[.5,.5],2,10,4,0,300,dp,1000,shield=shield)

    def test_break_one_layer_then_stop_at_one_dp(self):
        d=self.run_damage(100)
        self.assertEqual(d['dp_damage'],199)
        self.assertEqual(d['hp_damage'],0)
        self.assertEqual(d['remaining_dp'],1)
        self.assertEqual(d['final'],100)  # Still protected by DP, no HP destruction growth.
        p=pool_distribution(d)
        self.assertEqual(p['atoms'],[(199,1)])
        self.assertEqual(p['kill_probability'],0)

    def test_already_locked_and_final_layer(self):
        d=self.run_damage(100,locked=True)
        self.assertEqual(d['dp_damage'],99);self.assertEqual(d['hp_damage'],0)
        self.assertEqual(pool_distribution(d)['atoms'],[(99,1)])
        d=self.run_damage(1,locked=True,remaining=1,next_dp=None)
        self.assertEqual(d['damage'],0)
        self.assertEqual(pool_distribution(d)['atoms'],[(0,1)])
        d=self.run_damage(100,remaining=1,next_dp=None)
        self.assertEqual(d['hp_damage'],900)
        self.assertEqual(d['final'],140)

    def test_uncertain_lock_and_missing_next_capacity_block(self):
        with self.assertRaises(ValueError):self.run_damage(100,locked=None)
        with self.assertRaises(ValueError):self.run_damage(100,next_dp=None)

    def test_random_first_break_keeps_suffix_in_dp(self):
        shield=dict(limit_per_turn=1,locked=False,remaining=3,next_dp=100)
        d=simulate_pools(DamageInputs(base=100,critical=False,hp_bonus=500),[.5,.5],2,10,4,0,300,50,1000,shield=shield)
        p=pool_distribution(d)
        self.assertAlmostEqual(p['mean'],75,delta=.05)
        self.assertAlmostEqual(dict(p['atoms'])[50],.5,delta=.001)
        self.assertEqual(p['kill_probability'],0)
