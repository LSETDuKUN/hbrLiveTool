import json
import math
import unittest
from pathlib import Path
from unittest.mock import patch
from hbr_live_app.destruction import per_hit, apply_to_result
from hbr_live_app.damage_math import DamageInputs, calculate
from hbr_live_app.damage_autofill import autofill
from hbr_live_app.passive_audit import accessory_effects
from test_damage_autofill import setup, status


class DestructionTests(unittest.TestCase):
    def test_live_six_hit_sample_with_destruction_earring(self):
        data=json.loads((Path(__file__).parent/'fixtures/destruction_live.json').read_text(encoding='utf-8'))
        result=per_hit(data['weights'],6,data['skill_dr'],data['enemy_coefficient'],
                       data['bonus'],data['initial'],data['maximum'])
        for row,observed in zip(result['rows'],data['observed_after']):
            self.assertAlmostEqual(row['after'],observed,delta=.0002)
            self.assertAlmostEqual(row['increment'],2.9)
        self.assertAlmostEqual(result['actual_increment'],17.4)

    def test_equal_growth_unequal_damage_and_pre_increment(self):
        d=per_hit([.1,.9],2,10,4,50,100,999)
        self.assertEqual([r['increment'] for r in d['rows']],[30,30])
        self.assertEqual(d['final'],160)
        self.assertAlmostEqual(d['weights'][0],.1)
        self.assertAlmostEqual(d['weights'][1],1.17)
        self.assertAlmostEqual(d['average'],1.27)

    def test_cap_and_additional_hits(self):
        d=per_hit([.1,.9,.25,.25],2,10,4,0,100,135)
        self.assertEqual([r['before'] for r in d['rows']],[100,120,135,135])
        self.assertEqual([r['increment'] for r in d['rows']],[20,15,0,0])
        self.assertEqual(d['theoretical_increment'],60)
        self.assertEqual(d['actual_increment'],35)
        self.assertEqual(d['clipped'],25)
        self.assertEqual(d['theoretical_final'],160)
        uncapped=per_hit([.5,.5,.25],2,10,4,0,100,999)
        self.assertEqual(uncapped['final'],150)

    def test_reported_limit_impact_with_two_ten_percent_bonuses(self):
        d=per_hit([1],1,3.5,4,20,112.675,300)
        self.assertAlmostEqual(d['actual_increment'],16.8)
        capped=per_hit([1],1,3.5,4,20,295,300)
        self.assertAlmostEqual(capped['theoretical_increment'],16.8)
        self.assertEqual(capped['actual_increment'],5)
        self.assertAlmostEqual(capped['clipped'],11.8)

    def test_replaces_fixed_destruction_without_counting_chain_twice(self):
        i=DamageInputs(base=100,critical=False,chain=25,destruction=200)
        old=calculate(i)
        result,detail=apply_to_result(old,i,[.5,.5,.25],2,10,4,0,999)
        self.assertEqual(old['damage'],250)
        self.assertAlmostEqual(result['damage'],100*(1+1.1+.6))
        self.assertEqual(result['factors']['chain'],1.25)
        self.assertEqual(detail['final'],250)
        self.assertAlmostEqual(result['minimum'],result['damage']*.9)

    def test_dp_has_no_destruction_damage_bonus_or_growth(self):
        i=DamageInputs(base=100,critical=False,destruction=300,target_pool='dp')
        result,detail=apply_to_result(calculate(i),i,[.5,.5],2,10,4,50,500)
        self.assertEqual(result['damage'],100)
        self.assertEqual(detail['final'],300)
        self.assertEqual(detail['weights'],[.5,.5])

    def test_invalid_inputs_and_chain_edits(self):
        for weights,n,cap in [([.3,.3],2,300),([1],2,300),([1],1,50),([math.nan],1,300)]:
            with self.assertRaises(ValueError):per_hit(weights,n,10,4,0,100,cap)
        i=DamageInputs(chain=75)
        with self.assertRaisesRegex(ValueError,'连击合计'):
            apply_to_result(calculate(i),i,[1,.25],1,1,4,0,300)


class DestructionFillTests(unittest.TestCase):
    def setUp(self):
        self.p,self.e,lookup=setup();self.p['actor_position']=0
        self.db=lookup('test');self.db.update(hit_count=2,hits=[dict(type='Main',power_ratio=.1),dict(type='Main',power_ratio=.9)])
        self.db['parts'][0]['multipliers']['dr']=10
        self.e['enemy_progress'].update(destruction_coefficient=4,destruction_max=600)
        self.data=json.loads((Path(__file__).parent/'fixtures/destruction_accessories.json').read_text(encoding='utf-8'))
        patcher=patch('hbr_live_app.passive_audit.passive_record',side_effect=lambda label:self.data.get(label,{}))
        patcher.start();self.addCleanup(patcher.stop)

    def fill(self):return autofill(self.p,self.e,lookup=lambda _:self.db)

    def test_equipment_types_and_hit_dependent_values(self):
        self.p['combat_inputs']['passive_labels']=list(self.data)
        self.db['hit_count']=10
        self.db['hits']=[dict(type='Main',power_ratio=.1) for _ in range(10)]
        r=self.fill()
        self.assertEqual(r['values']['element_attack'],6)
        self.assertEqual(r['values']['dp_bonus'],5)
        self.assertAlmostEqual(r['params']['destruction_bonus'],25)
        self.assertAlmostEqual(r['params']['od_gain_bonus'],15)
        self.assertTrue(r['equipment_notes'])
        self.assertTrue(r['destruction_ready'])

    def test_actual_equipment_and_inactive_state_prevent_duplicate_prediction(self):
        label='Passive.Start_DamageRateUpByHitEarring03'
        self.p['combat_inputs']['passive_labels']=[label]
        self.p['statuses']=[status('DamageRateUp',12,source=label)]
        self.assertEqual(self.fill()['params']['destruction_bonus'],12)
        self.p['statuses'][0]['effective']=False
        self.assertEqual(self.fill()['params']['destruction_bonus'],0)

    def test_necklace_attack_is_predicted_once_and_actual_state_supersedes(self):
        label='Passive.Start_SkillEnhance'
        self.p['combat_inputs']['passive_labels']=[label,'Passive.Start_DamageRateUp_10']
        r=self.fill();self.assertEqual(r['values']['attack'],10)
        self.assertEqual(r['params']['destruction_bonus'],10)
        self.p['statuses']=[status('AttackUp',10,source=label)]
        self.assertEqual(self.fill()['values']['attack'],10)

    def test_live_hit_count_wins_and_mismatching_distribution_blocks_growth(self):
        self.p['combat_inputs']['selected_skill']['hit_count']=3
        r=self.fill();self.assertFalse(r['destruction_ready'])
        self.assertTrue(any('采用游戏段数' in text for text in r['skipped']))

    def test_finite_buffs_compete_permanent_and_equipment_add(self):
        self.p['combat_inputs']['passive_labels']=['Passive.Start_DamageRateUp_10']
        a=status('DamageRateUp',20);a.update(duration_kind='count',buff_limit_type=0)
        b=status('DamageRateUp',50);b.update(duration_kind='count',buff_limit_type=4)
        self.p['statuses']=[a,a.copy(),b,status('DamageRateUp',7)]
        self.assertEqual(self.fill()['params']['destruction_bonus'],67)

    def test_unknown_resistance_disables_automatic_growth(self):
        self.e['statuses']=[status('DamageRateResistUp',50)]
        r=self.fill();self.assertFalse(r['destruction_ready']);self.assertIsNone(r['params']['enemy_dr'])
        self.assertTrue(any('破坏抗性' in n for n in r['skipped']))

    def test_missing_distribution_or_enemy_coeff_does_not_invent_growth(self):
        self.db.pop('hits');r=self.fill();self.assertFalse(r['destruction_ready'])
        self.e['enemy_progress'].pop('destruction_coefficient');self.assertIsNone(self.fill()['params']['enemy_dr'])

    def test_confirmed_before_hit_buff_and_materialization(self):
        self.db['parts'].append(dict(label='buff',skill_type='DamageRateUp',target_type='Self',
                                    power=[.5,0],growth=[],hits=[dict(type='Before')],
                                    effect=dict(exitCond='Count',limitType='Default')))
        self.assertEqual(self.fill()['params']['destruction_bonus'],50)
        self.p['statuses']=[status('DamageRateUp',50,source='test')]
        self.assertEqual(self.fill()['params']['destruction_bonus'],50)

    def test_runtime_skill_dr_preferred(self):
        self.p['combat_inputs']['selected_skill']['parts']=[dict(Label='test',DamageRateRate=12)]
        self.assertEqual(self.fill()['params']['skill_dr'],12)
