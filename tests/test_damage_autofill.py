import unittest
from hbr_live_app.damage_autofill import autofill, WEIGHTS
from hbr_live_app.damage_math import skill_base


def status(kind,amount=0,**extra):
    return dict(label='SpecialStatus.'+kind,name=kind,duration_kind='permanent',element_type=0,
                values=dict(amountOnDpDamageInt=amount*100,amountOnHpDamageInt=amount*100,rateValueInt=amount*100),**extra)


def setup():
    part=dict(label='test',skill_type='AttackSkill',elements=['Thunder'],type='Stab',power=[50,100],
              diff_for_max=100,parameters=dict(str=2,dex=1,wis=0,luk=0,con=0,spr=0),
              growth=[.05,.02],multipliers=dict(dp=1,hp=1.5))
    player=dict(actor_id=1,statuses_available=True,statuses=[],combat_inputs=dict(
        selected_skill=dict(label='test',name='测试攻击',level=1,parts=[]),stats={k:200 for k in WEIGHTS}))
    enemy=dict(address=2,dp=0,statuses_available=True,statuses=[],base_resistances=dict(thunder=-300,stab=50),
               enemy_progress=dict(damage_rate=250),combat_inputs=dict(_defenseRefParam=100))
    return player,enemy,lambda label:dict(parts=[part])


class AutofillTests(unittest.TestCase):
    def test_hp_accessory_is_retained_while_enemy_still_has_dp(self):
        p,e,lookup=setup();e['dp']=40
        accessory=status('AttackUpIncludeNormal',source='AccessoryHp')
        accessory['values']['amountOnHpDamageInt']=1500
        p['statuses']=[accessory]
        r=autofill(p,e,lookup=lookup)
        self.assertEqual(r['values']['target_pool'],'dp')
        self.assertEqual(r['values']['hp_bonus'],65)
        self.assertEqual(r['values']['dp_bonus'],0)
        self.assertEqual(r['values']['attack'],0)
        self.assertNotIn('hp_bonus',r['hp_adjustments'])  # Already included, no double count.

    def test_thunder_mark_thresholds_and_highest_only(self):
        for rank,attack,crit,rate in [(0,0,50,0),(1,30,50,0),(3,30,50,0),(4,30,50,30),(5,30,80,30),(6,30,80,30)]:
            with self.subTest(rank=rank):
                p,e,lookup=setup()
                mark=status('ThunderMark');mark['values']['numValue']=rank
                p['statuses']=[mark,mark.copy()]
                r=autofill(p,e,lookup=lookup)
                self.assertEqual(r['values']['attack'],attack)
                self.assertEqual(r['values']['critical_bonus'],crit)
                self.assertEqual(r['params']['critical_rate_bonus'],rate)
                self.assertEqual(r['values']['destruction'],250)
        lower=status('ThunderMark');lower['values']['numValue']=1
        p['statuses'].append(lower)
        r=autofill(p,e,lookup=lookup,modes=dict(transcend=True,lightning_style=True))
        self.assertEqual(r['values']['attack'],330)
        self.assertEqual(r['values']['critical_bonus'],180)

    def test_morale_attribute_and_damage_components(self):
        p,e,lookup=setup()
        morale=status('Morale',10);morale['values']['numValue']=2
        p['statuses']=[morale]
        r=autofill(p,e,lookup=lookup)
        self.assertEqual(r['params']['morale_level'],2)
        self.assertEqual(r['values']['attack'],10)
        self.assertEqual(skill_base(r['params'],False)[1],210)
        self.assertEqual(p['combat_inputs']['stats']['power'],200)
        r['params'].update(enemy=200,orb=0)
        self.assertEqual(skill_base(r['params'],False)[0],55)
        self.assertEqual(skill_base(r['params'],True)[0],80)
        r['params']['morale_level']=0
        self.assertEqual(skill_base(r['params'],False)[0],50)

    def test_high_boost_single_instance_overrides_and_expiry(self):
        p,e,lookup=setup();p['statuses']=[status('HighBoost'),status('HighBoost')]
        self.assertEqual(autofill(p,e,lookup=lookup)['values']['attack'],180)
        self.assertEqual(autofill(p,e,lookup=lookup,modes=dict(high_boost=False))['values']['attack'],0)
        p['statuses']=[status('HighBoost',pending_remove=True)]
        expired=status('HighBoost');expired.update(duration_kind='turn',remaining=0)
        p['statuses'].append(expired)
        self.assertEqual(autofill(p,e,lookup=lookup)['values']['attack'],0)
        self.assertEqual(autofill(p,e,lookup=lookup,modes=dict(high_boost=True))['values']['attack'],180)
        db=lookup('test');db['parts'][0]['skill_type']='AttackNormal'
        self.assertEqual(autofill(p,e,lookup=lambda _:db,modes=dict(high_boost=True))['values']['attack'],0)

    def test_transcend_ghost_and_gidou_are_distinct_and_do_not_reenhance_buffs(self):
        p,e,lookup=setup();p['style_label']='STezuka03'
        p['statuses']=[status('AttackUp',100)]
        r=autofill(p,e,lookup=lookup,modes=dict(ghost=True,gidou=True,transcend=True,lightning_style=True))
        self.assertEqual(r['values']['attack'],700)
        self.assertEqual(r['values']['mind_eye'],120)
        self.assertEqual(r['values']['chain'],75)
        self.assertEqual(r['values']['critical_bonus'],150)
        self.assertEqual(r['values']['destruction'],250)
        self.assertTrue(r['values']['critical'])
        self.assertGreaterEqual(r['params']['critical_rate_bonus'],100)

    def test_mode_only_effects_compete_and_gidou_materialization_is_not_double_counted(self):
        p,e,lookup=setup();p['style_label']='STezuka03'
        gidou=status('AttackUp',300,source='Passive.Condition_AttackUp11');gidou.update(duration_kind='turn',remaining=1)
        mind=status('MindEye',150);mind.update(duration_kind='count',remaining=1,buff_limit_type=4)
        funnel=status('Funnel',25);funnel['values']['numValue']=3;funnel.update(buff_limit_type=4)
        crit=status('CriticalDamageUp',150);crit.update(duration_kind='count',remaining=1,buff_limit_type=4)
        p['statuses']=[gidou,mind,funnel,crit]
        r=autofill(p,e,lookup=lookup,modes=dict(ghost=True,gidou=True,transcend=True,lightning_style=True))['values']
        self.assertEqual(r['attack'],600);self.assertEqual(r['mind_eye'],150)
        self.assertEqual(r['chain'],75);self.assertEqual(r['critical_bonus'],200)

    def test_wrong_style_and_non_thunder_attack_do_not_receive_burst(self):
        p,e,lookup=setup();db=lookup('test');db['parts'][0]['elements']=['Ice']
        r=autofill(p,e,lookup=lambda label:db,modes=dict(ghost=True,gidou=True,transcend=True,lightning_style=True))['values']
        self.assertEqual(r['attack'],300);self.assertEqual(r['critical_bonus'],50)
        self.assertEqual(r['chain'],0);self.assertEqual(r['mind_eye'],0)
        r=autofill(p,e,lookup=lookup,modes=dict(transcend=True,lightning_style=False))['values']
        self.assertEqual(r['attack'],0)

    def test_level_ten_orb_five_matches_reference_piecewise_formula(self):
        p,e,lookup=setup();params=autofill(p,e,lookup=lookup)['params']
        params.update(min_power=3350.625,max_power=6701.25,difference=140,level=10,orb=5,
                      power=767,dexterity=621,weight_power=1,weight_dexterity=1,enemy=610)
        # weighted=694, critical diff=134, below the 140 border: no over-diff term.
        low=3350.625*1.45;high=6701.25*1.18
        expected=low+(high-low)*134/140+(3350.625+(6701.25-3350.625)*134/240)*.1
        self.assertAlmostEqual(skill_base(params,True)[0],expected)

    def test_known_buffs_field_resistance_specialization_and_passive(self):
        p,e,lookup=setup()
        accessory=status('AttackUpIncludeNormal',source='AccessoryHp')
        accessory['values']['amountOnHpDamageInt']=1500
        p['statuses']=[status('AttackUp',10),status('MindEye',100),status('CriticalDamageUp',50),
                       status('BuffCharge',30),accessory]
        funnel=status('Funnel',12);funnel['values']['numValue']=3;p['statuses'].append(funnel)
        e['statuses']=[status('DefenseDown',40),status('Fragile',50)]
        field=status('Zone',195);field.update(element_key='Thunder',element_type=3)
        result=autofill(p,e,dict(statuses=[field]),lookup)
        v=result['values']
        self.assertEqual(v['attack'],10);self.assertEqual(v['field'],95);self.assertEqual(v['hp_bonus'],65)
        self.assertEqual(v['critical_bonus'],100);self.assertEqual(v['chain'],36)
        self.assertEqual(v['charge'],30);self.assertEqual(v['destruction'],250)
        self.assertEqual(v['element_bonus'],300);self.assertEqual(v['resistance'],50)
        self.assertEqual(v['defense_down'],40);self.assertEqual(v['fragile'],50)
        self.assertEqual(result['params']['weight_power'],2)
        self.assertEqual(result['params']['orb'],5)

    def test_excludes_pending_other_elements_and_skill_debuff(self):
        p,e,lookup=setup()
        p['statuses']=[status('AttackUp',100,pending_add=True),status('AttackUp',100,element_key='Fire')]
        v=autofill(p,e,lookup=lookup)['values']
        self.assertEqual(v['attack'],0);self.assertEqual(v['defense_down'],0)

    def test_finite_only_competes_but_permanent_is_additive(self):
        p,e,lookup=setup()
        a=status('AttackUp',100);a.update(duration_kind='count',remaining=1,buff_limit_type=2)
        b=status('AttackUp',300);b.update(duration_kind='turn',remaining=4,buff_limit_type=4)
        p['statuses']=[a,b,status('AttackUp',10)]
        self.assertEqual(autofill(p,e,lookup=lookup)['values']['attack'],310)
        b['pending_remove']=True
        self.assertEqual(autofill(p,e,lookup=lookup)['values']['attack'],110)

    def test_memory_power_wins_and_skill_base_responds_to_edits(self):
        p,e,lookup=setup()
        p['combat_inputs']['selected_skill']['parts']=[dict(Label='test',Power=80,MaxPower=160)]
        params=autofill(p,e,lookup=lookup)['params']
        self.assertEqual(params['min_power'],80)
        params.update(orb=0)
        self.assertEqual(skill_base(params,False),(160,200))
        params.update(orb=5)
        self.assertAlmostEqual(skill_base(params,False)[0],172)
        params['weight_power']=0;params['dexterity']=100
        self.assertEqual(skill_base(params,False)[1],100)

    def test_missing_skill_stays_unknown(self):
        p,e,_=setup();p['combat_inputs']['selected_skill']={}
        result=autofill(p,e,lookup=lambda label:{})
        self.assertIsNone(result['params']['min_power'])
        self.assertTrue(result['skipped'])
