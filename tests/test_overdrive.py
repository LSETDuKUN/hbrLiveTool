import json
import unittest
from pathlib import Path
from unittest.mock import patch
from test_statuses import RecordedMemory
from test_damage_autofill import setup
from hbr_live_app.statuses import StatusReader
from hbr_live_app.overdrive import read_overdrive,od_label
from hbr_live_app.damage_math import calculate,DamageInputs
from hbr_live_app.damage_autofill import autofill
from hbr_live_app.passive_audit import od_gain_bonus


class OverdriveTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((Path(__file__).parent/'fixtures/overdrive.json').read_text(encoding='utf8'))

    def sample(self):return read_overdrive(StatusReader(RecordedMemory(self.data)),self.data['module'])

    def change(self,name,value):
        for obj in self.data['objects']:
            for field in obj['fields']:
                if field['name']==name:field['value']=value

    def test_live_level_one_and_exact_fraction(self):
        state=self.sample()
        self.assertEqual(state['level'],1);self.assertTrue(state['active'])
        self.assertEqual(state['percent'],70);self.assertEqual(state['consumed_points'],10000)
        self.change('_currentPoint',5774)
        self.assertEqual(self.sample()['percent'],57.74)
        self.assertIn('57.74%',od_label(self.sample()))

    def test_stale_activated_level_is_not_current_od(self):
        self.change('<isOverDriveTurn>k__BackingField',False)
        state=self.sample();self.assertEqual(state['level'],0)
        self.assertFalse(state['active']);self.assertEqual(state['last_activated_level'],1)
        self.change('_currentPoint',-500)
        self.assertEqual(self.sample()['percent'],-5)

    def test_unknown_transition_and_layout_fail_closed(self):
        self.change('activatedLevel',0)
        self.assertIsNone(self.sample()['level'])
        self.change('_currentPoint',2000000)
        self.assertFalse(self.sample()['available'])

    def test_auto_damage_od_tiers_and_inactive(self):
        p,e,lookup=setup()
        for tier in (1,2,3):
            r=autofill(p,e,lookup=lookup,modes=dict(od_active=True,od_level=tier))
            self.assertAlmostEqual(r['values']['od'],1+.1*tier)
        r=autofill(p,e,lookup=lookup,modes=dict(od_active=False,od_level=3))
        self.assertEqual(r['values']['od'],1)
        r=autofill(p,e,lookup=lookup,modes=dict(od_active=True,od_level=None))
        self.assertEqual(r['values']['od'],1)

    def test_od_accessory_affects_gain_only(self):
        label=self.data['accessory']['label'];p,e,lookup=setup();p['actor_position']=0
        p['combat_inputs']['passive_labels']=[label]
        with patch('hbr_live_app.passive_audit.passive_record',return_value=self.data['accessory']):
            for hits,bonus in [(1,5),(10,15),(20,15)]:
                self.assertAlmostEqual(od_gain_bonus(p,dict(hit_count=hits))[0],bonus)
            self.assertAlmostEqual(20*(1+od_gain_bonus(p,dict(hit_count=10))[0]/100),23)
            db=lookup('test');db['hit_count']=10
            r=autofill(p,e,lookup=lambda _:db)
            self.assertAlmostEqual(r['params']['od_gain_bonus'],15)
            self.assertEqual(r['values']['od'],1)
            self.assertEqual(r['values']['attack'],0)

    def test_servant_weakness_gate_and_separate_stacking(self):
        for kwargs,expected in [(dict(),1),(dict(element_bonus=300),2.6),
                                (dict(element_bonus=300,resistance=75),1),
                                (dict(penetration_critical=True),2.6)]:
            r=calculate(DamageInputs(mind_eye=120,servant_mind_eye=40,**kwargs))
            self.assertEqual(r['factors']['attack'],expected)
        self.assertEqual(calculate(DamageInputs(mind_eye=120,servant_mind_eye=40,penetration_critical=True,absorbed=True))['factors']['attack'],1)
