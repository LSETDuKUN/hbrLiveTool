import unittest
from copy import deepcopy
from hbr_live_app.damage_math import DamageInputs
from hbr_live_app.damage_sequence import DamageSequence


def config(dp=50,hp=10000,rate=100,base=100,shield=None):
    return dict(inputs=DamageInputs(base=base,critical=False,destruction=rate,hp_bonus=15),
        weights=[1],main_hits=1,skill_dr=5,enemy_coefficient=4,bonus=0,maximum=300,
        enemy_dp=dp,enemy_hp=hp,shield=shield)


class SequenceTests(unittest.TestCase):
    def test_break_then_hp_bonus_and_rate_are_inherited_without_mutating_live(self):
        seq=DamageSequence();first=seq.append(1,'A','破盾',9,config())
        self.assertEqual(first['raw_damage'],100)
        self.assertEqual(first['damage'],50)
        self.assertEqual(first['after']['rate'],120)
        live=dict(address=9,dp=50,hp=10000,enemy_progress=dict(damage_rate=100))
        original=deepcopy(live);virtual=seq.overlay(live)
        self.assertEqual(live,original)
        second=seq.append(2,'B','终结',9,config(virtual['dp'],virtual['hp'],virtual['enemy_progress']['damage_rate']))
        self.assertAlmostEqual(second['damage'],138)
        self.assertEqual(second['after']['rate'],140)
        seq.undo();self.assertEqual(seq.current,first['after'])
        seq.clear();self.assertEqual(seq.overlay(live),live)

    def test_cap_and_locked_next_shield_survive_next_actor(self):
        seq=DamageSequence()
        shield=dict(remaining=3,index=0,broken=0,locked=False,limit_per_turn=1,next_dp=80,breaks_this_turn=0)
        first=seq.append(1,'A','破盾',9,config(shield=shield))
        self.assertEqual(first['after']['dp'],80)
        self.assertEqual(first['after']['shield']['remaining'],2)
        self.assertTrue(first['after']['shield']['locked'])
        self.assertEqual(first['after']['rate'],100)
        second=seq.append(2,'B','追打',9,config(80,10000,100,shield=first['after']['shield']))
        self.assertEqual(second['damage'],79)
        self.assertEqual(second['after']['dp'],1)
        self.assertEqual(second['after']['shield']['remaining'],2)
        self.assertEqual(second['after']['hp'],10000)
        cap=DamageSequence().append(1,'A','上限',9,config(dp=0,rate=295))
        self.assertEqual(cap['after']['rate'],300)

    def test_last_shield_and_invalid_steps(self):
        seq=DamageSequence()
        shield=dict(remaining=1,index=2,broken=2,locked=False,limit_per_turn=1)
        first=seq.append(1,'A','末盾',9,config(shield=shield))
        state=first['after'];self.assertEqual(state['shield']['remaining'],0)
        with self.assertRaises(ValueError):seq.overlay(dict(address=10))
        with self.assertRaises(ValueError):seq.append(1,'A','重复',9,config())
        with self.assertRaises(ValueError):seq.append(2,'B','旧参数',9,config())
        for actor in (2,3):
            state=seq.current
            seq.append(actor,str(actor),'攻击',9,config(state['dp'],state['hp'],state['rate'],shield=state['shield']))
        with self.assertRaises(ValueError):seq.append(4,'D','第四人',9,config())

    def test_killed_target_stops_and_saved_config_is_frozen(self):
        seq=DamageSequence();c=config(dp=0,hp=10)
        step=seq.append(1,'A','击杀',9,c)
        c['inputs'].base=999;c['weights'][0]=.5
        self.assertEqual(step['config']['inputs'].base,100)
        self.assertEqual(step['config']['weights'],[1])
        with self.assertRaises(ValueError):seq.append(2,'B','鞭尸',9,config(dp=0,hp=0,rate=120))
