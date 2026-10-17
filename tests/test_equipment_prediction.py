import json
import unittest
from pathlib import Path
from unittest.mock import patch
from test_damage_autofill import setup, status
from hbr_live_app.damage_autofill import autofill
from hbr_live_app.passive_audit import passive_record

RING='Passive.Start_DarkEnhanceRing02'
EARRING='Passive.Start_HPAttackUpRangeByHitEarring03'


class EquipmentPredictionTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((Path(__file__).parent/'fixtures/equipment_passives.json').read_text(encoding='utf8'))
        self.patch=patch('hbr_live_app.passive_audit.passive_record',side_effect=lambda label:self.data.get(label,{}))
        self.patch.start();self.addCleanup(self.patch.stop)
        self.p,self.e,lookup=setup();self.p['actor_position']=0
        self.p['combat_inputs']['passive_labels']=[RING,EARRING]
        self.db=lookup('test');self.db['hit_count']=10;self.db['parts'][0]['elements']=['Dark']

    def fill(self):return autofill(self.p,self.e,lookup=lambda _:self.db)

    def test_ring_six_and_ten_hit_earring_five_add_to_existing_hp_bonus(self):
        v=self.fill()['values']
        self.assertEqual(v['element_attack'],6)
        self.assertAlmostEqual(v['hp_bonus'],55)
        self.e['dp']=100
        v=self.fill()['values'];self.assertEqual(v['dp_bonus'],0)
        self.assertAlmostEqual(v['hp_bonus'],55)

    def test_hit_interpolation_excludes_followups_and_clamps(self):
        chain=status('Funnel',25);chain['values']['numValue']=3;self.p['statuses']=[chain]
        for hits,bonus in [(1,15),(9,15-80/9),(10,5),(20,5)]:
            self.db['hit_count']=hits
            self.assertAlmostEqual(self.fill()['values']['hp_bonus'],50+bonus)

    def test_actual_state_supersedes_prediction_and_is_not_double_counted(self):
        ring=status('AttackUp',6,source=RING,element_key='Dark')
        ear=status('AttackUp',6,source=EARRING);ear['values']['amountOnDpDamageInt']=0
        self.p['statuses']=[ring,ear]
        v=self.fill()['values'];self.assertEqual(v['element_attack'],6)
        self.assertAlmostEqual(v['hp_bonus'],56)
        self.assertEqual(v['attack'],0)

    def test_no_wrong_element_normal_attack_or_back_row_bonus(self):
        self.db['parts'][0]['elements']=['Fire']
        self.assertEqual(self.fill()['values']['element_attack'],0)
        self.p['actor_position']=3
        self.assertAlmostEqual(self.fill()['values']['hp_bonus'],50)
        self.p['actor_position']=0;self.db['parts'][0]['skill_type']='AttackNormal'
        self.assertEqual(self.fill()['values']['element_attack'],0)
        self.assertAlmostEqual(self.fill()['values']['hp_bonus'],50)

    def test_unowned_and_unknown_hits_are_not_guessed(self):
        self.p['combat_inputs']['passive_labels']=[]
        self.assertEqual(self.fill()['values']['element_attack'],0)
        self.p['combat_inputs']['passive_labels']=[EARRING];self.db.pop('hit_count')
        r=self.fill();self.assertAlmostEqual(r['values']['hp_bonus'],50)
        self.assertTrue(any('主 Hit 数未确认' in n for n in r['notes']))


class EquipmentCatalogTests(unittest.TestCase):
    def test_resolves_nested_accessory_effect_without_guessing_level(self):
        data=json.loads((Path(__file__).parent/'fixtures/equipment_passives.json').read_text(encoding='utf8'))
        nested=json.dumps(dict(rng_eff=[[dict(skill=data[EARRING])]]))
        passive_record.cache_clear()
        try:
            with patch('hbr_data.store.Catalog.query',side_effect=[([],[],False),([] ,[(nested,)],False)]):
                self.assertEqual(passive_record(EARRING)['parts'][0]['power'],[.05,.15])
        finally:passive_record.cache_clear()
