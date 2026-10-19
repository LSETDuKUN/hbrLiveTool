import unittest
from hbr_live_app.sp_scaling import sp_factor
from hbr_live_app.damage_autofill import autofill
from hbr_live_app.damage_math import skill_base
from test_damage_autofill import setup, status


class SpScalingTests(unittest.TestCase):
    def skill(self):
        player,enemy,lookup=setup()
        db=lookup('test');part=db['parts'][0]
        part.update(skill_type='AttackBySp',value=[30,0])
        part['multipliers']['dr']=4.9
        player['combat_inputs'].update(current_sp=15,expected_sp=0,sp_to_consume=0)
        return player,enemy,db

    def test_power_cap_before_growth_and_over_threshold(self):
        p,e,db=self.skill()
        p['combat_inputs']['selected_skill']['level']=10
        r=autofill(p,e,lookup=lambda _:db)
        params=r['params'];params.update(enemy=0,orb=5)
        full=dict(params,sp_consumed=30)
        self.assertAlmostEqual(skill_base(params)[0],skill_base(full)[0]/2)
        self.assertEqual(skill_base(dict(full,sp_consumed=50)),skill_base(full))
        self.assertEqual(params['min_power'],50)
        self.assertEqual(params['skill_dr'],4.9)
        self.assertEqual(params['sp_consumed'],15)  # Ignore stale zero preview.

    def test_missing_and_zero_sp_do_not_guess_maximum(self):
        p,e,db=self.skill()
        for sp in (None,0,-1,float('nan'),float('inf')):
            p['combat_inputs']['current_sp']=sp
            r=autofill(p,e,lookup=lambda _:db)
            with self.assertRaises(ValueError):skill_base(r['params'])
        for cap in (0,None,-30):
            with self.assertRaises(ValueError):sp_factor(15,cap)

    def test_negative_token_cost_is_not_sp_scaling(self):
        p,e,lookup=setup();db=lookup('test')
        db.update(sp_cost=-1,consume_type='Token')
        self.assertFalse(autofill(p,e,lookup=lambda _:db)['sp_scaling'])

    def test_charging_destruction_branch_is_separate_from_sp(self):
        p,e,db=self.skill();part=db['parts'][0]
        import copy
        charged=copy.deepcopy(part);charged['multipliers']['dr']=22
        normal=copy.deepcopy(part);normal['multipliers']['dr']=11
        db['parts']=[dict(skill_type='SkillCondition',cond='IsCharging()',strval=[
            dict(parts=[charged]),dict(parts=[normal])])]
        for statuses,expected in [([],11),([status('BuffCharge')],22),
                                  ([status('BuffCharge',pending_remove=True)],11)]:
            p['statuses']=statuses
            r=autofill(p,e,lookup=lambda _:db)
            self.assertTrue(r['sp_scaling'])
            self.assertEqual(r['params']['skill_dr'],expected)
        p['statuses_available']=False
        r=autofill(p,e,lookup=lambda _:db)
        self.assertIsNone(r['params']['max_power'])
