import json
import math
import unittest
from pathlib import Path
from test_damage_autofill import setup, status
from hbr_live_app.damage_autofill import autofill
from hbr_live_app.damage_math import calculate, DamageInputs, skill_base, enemy_attribute_reduction
from hbr_live_app.damage_probability import distribution
from hbr_live_app.statuses import status_value


class RoundThreeTests(unittest.TestCase):
    def test_calamaties_compete_with_critical_only_for_damage(self):
        p,e,lookup=setup()
        e['statuses']=[status('FearOfDevil'),status('Misfortune')]
        params=autofill(p,e,lookup=lookup)['params']
        for critical in (False,True):self.assertEqual(enemy_attribute_reduction(params,critical),100)
        params['fear_of_devil']=0
        self.assertEqual(enemy_attribute_reduction(params,True),50)
        self.assertEqual(enemy_attribute_reduction(params,False),20)
        e['statuses'][0]['pending_remove']=True
        self.assertEqual(autofill(p,e,lookup=lookup)['params']['fear_of_devil'],0)
        params.update(orb=0,enemy=250,calamity=20,fear_of_devil=100)
        # diff = 200 - 250 + max(100,20,50) = 50, NOT 120.
        self.assertEqual(skill_base(params,True)[0],75)

    def test_recorded_servants_are_40_percent_and_deduplicated(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/damage_round3.json').read_text(encoding='utf8'))
        p,e,lookup=setup()
        p['statuses']=fixture['servants'];e['statuses']=fixture['enemy_statuses']
        r=autofill(p,e,lookup=lookup)
        self.assertEqual(r['values']['servant_mind_eye'],40)
        self.assertEqual(r['values']['attack'],0)
        self.assertEqual(r['params']['fear_of_devil'],100)
        self.assertIn('40%',status_value('BIYamawakiServant',dict(rateValueInt=4000)))
        self.assertIn('100',status_value('FearOfDevil',{}))

    def test_split_fields_preserve_multiplier(self):
        old=calculate(DamageInputs(base=100,attack=250,critical_bonus=150,defense_down=80))
        split=calculate(DamageInputs(base=100,attack=100,element_attack=50,field=100,
                                    critical_bonus=100,element_critical_bonus=50,
                                    defense_down=30,element_defense_down=50))
        self.assertEqual(old['damage'],split['damage'])
        p,e,lookup=setup()
        p['statuses']=[status('AttackUp',50,element_key='Thunder'),status('AttackUp',100),
                       status('CriticalDamageUp',30,element_key='Thunder')]
        e['statuses']=[status('DefenseDown',20,element_key='Thunder')]
        v=autofill(p,e,lookup=lookup)['values']
        self.assertEqual(v['attack'],100);self.assertEqual(v['element_attack'],50)
        self.assertEqual(v['element_critical_bonus'],30);self.assertEqual(v['element_defense_down'],20)

    def test_over_difference_keeps_growing_past_border(self):
        p,e,lookup=setup();params=autofill(p,e,lookup=lookup)['params']
        params.update(orb=0)
        first=skill_base(params,False)[0]
        for stat in ('power','dexterity'):params[stat]+=100
        second=skill_base(params,False)[0]
        self.assertAlmostEqual(second-first,100*.0025*100)
        for stat in ('power','dexterity'):params[stat]+=100
        self.assertAlmostEqual(skill_base(params,False)[0]-second,second-first)

    def test_hit_weights_from_catalog_plus_selected_funnel(self):
        p,e,lookup=setup();db=lookup('test')
        db.update(hit_count=2,hits=[dict(type='Main',power_ratio=.25),dict(type='Main',power_ratio=.75)])
        f=status('Funnel',25);f['values']['numValue']=3;p['statuses']=[f]
        r=autofill(p,e,lookup=lambda _:db)
        self.assertEqual(r['hit_weights'],[.25,.75,.25,.25,.25])
        db['hits']=[]
        r=autofill(p,e,lookup=lambda _:db)
        self.assertIn('等权',r['hit_note']);self.assertEqual(r['hit_weights'][:2],[.5,.5])


class DistributionTests(unittest.TestCase):
    def test_single_uniform_quantiles(self):
        d=distribution([1])
        self.assertAlmostEqual(d['low'],.91,places=4)
        self.assertAlmostEqual(d['high'],1.09,places=4)
        self.assertAlmostEqual(sum(d['density'])*d['step'],1,places=10)

    def test_two_hits_match_triangle_and_unequal_variance(self):
        d=distribution([1,1])
        self.assertAlmostEqual(d['low'],.9+math.sqrt(.001),places=4)
        self.assertAlmostEqual(max(d['density']),10,places=2)
        for weights in ([1,3],[1]*30,[1]*108):
            d=distribution(weights)
            mean=sum(x*y*d['step'] for x,y in zip(d['x'],d['density']))
            variance=sum((x-1)**2*y*d['step'] for x,y in zip(d['x'],d['density']))
            self.assertAlmostEqual(mean,1,places=7)
            self.assertAlmostEqual(variance,d['sigma']**2,delta=3e-7)
            self.assertAlmostEqual(d['low']+d['high'],2,places=7)
            self.assertTrue(all(math.isfinite(y) and y>=0 for y in d['density']))

    def test_invalid_and_scale_invariance(self):
        self.assertEqual(distribution([1,3]),distribution([10,30]))
        self.assertAlmostEqual(distribution([1,1e-300])['low'],.91,places=4)
        for weights in ([],[0],[-1],[float('nan')],[float('inf')],[1]*257):
            with self.assertRaises(ValueError):distribution(weights)
