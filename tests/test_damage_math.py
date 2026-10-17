import unittest
from hbr_live_app.damage_math import DamageInputs, calculate


class DamageMathTests(unittest.TestCase):
    def test_float_bounds_and_unknown_damage(self):
        r=calculate(DamageInputs(base=100,critical=False))
        self.assertAlmostEqual(r['minimum'],90)
        self.assertAlmostEqual(r['maximum'],110)
        for inputs in [DamageInputs(),DamageInputs(base=100,absorbed=True)]:
            r=calculate(inputs)
            self.assertIsNone(r['minimum']);self.assertIsNone(r['maximum'])

    def test_weakness_resistance_and_strict_boundary(self):
        for resistance, affinity, weak in [(50,2,True),(75,1,False),(90,.4,False)]:
            result=calculate(DamageInputs(element_bonus=300,resistance=resistance,mind_eye=100,fragile=50))
            self.assertAlmostEqual(result['affinity'],affinity)
            self.assertEqual(result['weak'],weak)
            self.assertEqual(result['factors']['attack'],2 if weak else 1)
            self.assertEqual(result['factors']['defense'],1.5 if weak else 1)

    def test_penetration_requires_crit_and_absorption_wins(self):
        self.assertTrue(calculate(DamageInputs(penetration_critical=True))['weak'])
        self.assertFalse(calculate(DamageInputs(penetration_critical=True,critical=False))['weak'])
        result=calculate(DamageInputs(base=100,element_bonus=300,penetration_critical=True,absorbed=True,mind_eye=100))
        self.assertFalse(result['weak']);self.assertIsNone(result['damage'])
        self.assertIsNone(result['multiplier']);self.assertEqual(result['factors']['attack'],1)

    def test_pool_token_charge_and_health_modifiers(self):
        i=DamageInputs(base=100,critical=False,attack=100,charge=50,token_bonus=160,
                       dp_bonus=50,hp_bonus=100,health_factor=2,down_factor=1.2)
        self.assertAlmostEqual(calculate(i)['damage'],100*2.5*2.6*2*2*1.2)
        i.target_pool='dp'
        self.assertAlmostEqual(calculate(i)['damage'],100*2.5*2.6*1.5*2*1.2)

    def test_missing_base_and_invalid_values(self):
        self.assertIsNone(calculate(DamageInputs())['damage'])
        for changes in [dict(base=float('nan')),dict(od=float('inf')),dict(resistance=101),dict(chain=-1),
                        dict(od=1e300,health_factor=1e300)]:
            with self.assertRaises(ValueError):calculate(DamageInputs(**changes))
