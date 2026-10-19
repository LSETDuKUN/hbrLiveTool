import json
from pathlib import Path
import unittest
from hbr_live_app.damage_autofill import autofill
from hbr_live_app.effect_preview import proposals
from hbr_live_app.effect_pending import pending_state,with_pending
from hbr_live_app.statuses import infer_suppressed_attacks
from hbr_live_app.status_rules import independent
from hbr_data.battle_conditions import context_for,evaluate

DATA=json.loads((Path(__file__).parent/'fixtures/down_turn.json').read_text(encoding='utf-8'))


def setup(label='CReaperSkill53',down=1):
    p=dict(actor_id=1,actor_position=0,statuses=[],combat_inputs=dict(stats=dict(power=400,dexterity=400,wisdom=300,luck=300),
        selected_skill=dict(label=label,level=1),passive_audit=[DATA['passive']]))
    e=dict(hp=1000,dp=0,statuses=[],enemy_progress={'down':down},combat_inputs={'_defenseRefParam':200})
    return p,e


class DownTurnTests(unittest.TestCase):
    def test_carol_power_and_passive_auto_activate_once(self):
        p,e=setup();r=autofill(p,e,lookup=DATA.get)
        self.assertAlmostEqual(r['params']['min_power'],10642.5,delta=.002)
        self.assertAlmostEqual(r['params']['max_power'],21285,delta=.002)
        self.assertEqual(r['params']['skill_dr'],3.875)
        self.assertEqual(r['values']['hp_bonus'],50)
        self.assertEqual(r['values']['down_factor'],1)
        self.assertEqual(r['values']['critical_bonus'],75)
        p['statuses']=[dict(label='SpecialStatus.CriticalDamageUp',source=DATA['passive']['label'],duration_kind='turn',remaining=1,values={'rateValueInt':2500})]
        self.assertEqual(autofill(p,e,lookup=DATA.get)['values']['critical_bonus'],75)

    def test_zero_unknown_and_other_enemy_conditions_are_distinct(self):
        p,e=setup(down=0)
        r=autofill(p,e,lookup=DATA.get,modes={'enemies':[e]})
        self.assertEqual(r['params']['min_power'],7582.5);self.assertEqual(r['values']['critical_bonus'],50)
        e['enemy_progress']={}
        self.assertIsNone(evaluate('TargetBreakDownTurn()>0',context_for(p,e)))
        self.assertEqual(autofill(p,e,lookup=DATA.get)['values']['critical_bonus'],50)
        _,other=setup(down=2)
        r=autofill(p,e,lookup=DATA.get,modes={'enemies':[e,other]})
        self.assertEqual(r['values']['critical_bonus'],75)
        self.assertEqual(r['params']['min_power'],7582.5)

    def test_other_style_destruction_replacement_and_nested_branch(self):
        p,e=setup('KAsakuraSkill55a')
        r=autofill(p,e,lookup=DATA.get)
        self.assertEqual(r['params']['skill_dr'],21)
        self.assertAlmostEqual(r['params']['max_power'],9390*1.3322684)
        self.assertAlmostEqual(r['values']['hp_bonus'],30)
        p,e=setup('AMizuharaSkill54')
        self.assertEqual(autofill(p,e,lookup=DATA.get)['params']['skill_dr'],28)
        e['enemy_progress']['down']=0
        self.assertEqual(autofill(p,e,lookup=DATA.get,modes={'enemies':[e]})['params']['skill_dr'],3.5)

    def test_conditional_hp_bonus_comes_from_branch_not_hardcoded(self):
        child=lambda hp:dict(parts=[dict(DATA['CReaperSkill53']['parts'][0],skill_type='AttackSkill',cond='',multipliers=dict(dp=1,hp=hp,dr=1))])
        skill=dict(label='test',parts=[dict(skill_type='SkillCondition',cond='TargetBreakDownTurn()>0',strval=[child(1.5),child(1.3)])])
        p,e=setup('test')
        self.assertEqual(autofill(p,e,lookup=lambda _:skill)['values']['hp_bonus'],50)
        e['enemy_progress']['down']=0
        self.assertAlmostEqual(autofill(p,e,lookup=lambda _:skill)['values']['hp_bonus'],30)

    def test_passive_critical_manual_preview_replaces_auto_prediction(self):
        p,e=setup();item=next(r for r in proposals(p,e,lookup=DATA.get) if r.get('passive'))
        side,state=pending_state(item,30,p)
        new,_=with_pending(p,e,[dict(enemy=side,state=state)])
        self.assertEqual(autofill(new,e,lookup=DATA.get)['values']['critical_bonus'],80)
        self.assertEqual(autofill(p,e,lookup=DATA.get)['values']['critical_bonus'],75)

    def test_passive_and_accessory_are_not_suppressed_but_counted_buff_is(self):
        def state(source,amount,only=0):
            return dict(label='SpecialStatus.AttackUp',source=source,element_type=0,duration_kind='turn',remaining=1,
                        buff_limit_type=only,values=dict(amountOnDpDamageInt=amount,amountOnHpDamageInt=amount))
        states=[state('Passive.BreakTurn_AttackUp01',5000),state('Accessory.Ring',600),state('skill',30000,4),state('Passive.ConsumeSpAttackUp01',10000)]
        infer_suppressed_attacks(states)
        self.assertNotIn('effective',states[0]);self.assertNotIn('effective',states[1]);self.assertFalse(states[3]['effective'])
        p,e=setup();p['statuses']=states
        self.assertEqual(autofill(p,e,lookup=DATA.get)['values']['attack'],356)
