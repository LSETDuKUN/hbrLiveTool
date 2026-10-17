import json
import unittest
from pathlib import Path
from unittest.mock import patch
from test_damage_autofill import setup, status
from hbr_live_app.damage_autofill import autofill
from hbr_live_app.passive_audit import audit_entry, audit_text


class PassiveAuditTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((Path(__file__).parent/'fixtures/low_sp_passives.json').read_text(encoding='utf8'))
        self.mock=patch('hbr_live_app.passive_audit.passive_record',side_effect=lambda label:self.data.get(label,{}))
        self.mock.start();self.addCleanup(self.mock.stop)
        self.p,self.e,_=setup();self.p['combat_inputs']['selected_skill']['label']='BIYamawakiSkill55'
        self.party=[dict(actor_id=i+2,actor=name,hp=100,combat_inputs=dict(passive_labels=[label])) for i,(name,label) in enumerate(
            [('丰后','Passive.ConsumeSpAttackUp01'),('山胁','Passive.ConsumeSpAttackUp03')])]

    def fill(self):return autofill(self.p,self.e,lookup=lambda _:self.data['skill'],party=self.party)

    def test_big_explosion_pre_funnel_and_two_owned_passives(self):
        r=self.fill()
        self.assertEqual(r['values']['attack'],200)
        self.assertEqual(r['values']['chain'],75)
        self.assertEqual(len(r['hit_weights']),13)
        self.assertEqual(r['hit_weights'][-3:],[.25,.25,.25])

    def test_only_override_and_top_two_not_unlimited_attack(self):
        only=status('AttackUp',300);only.update(duration_kind='count',remaining=1,buff_limit_type=4)
        self.p['statuses']=[only,status('AttackUp',10)]
        self.assertEqual(self.fill()['values']['attack'],310)
        only.update(buff_limit_type=0)
        self.assertEqual(self.fill()['values']['attack'],410)

    def test_materialized_passive_and_skill_funnel_not_double_counted(self):
        actual=status('AttackUp',100,source='Passive.ConsumeSpAttackUp01',
                      source_effect=dict(target_condition='IsAttackNormal()==0 && ConsumeSp()<=8'))
        actual.update(duration_kind='turn',remaining=1)
        chain=status('Funnel',25,source='BIYamawakiSkill55');chain['values']['numValue']=3
        chain.update(duration_kind='count',remaining=1)
        self.p['statuses']=[actual,chain]
        r=self.fill();self.assertEqual(r['values']['attack'],200);self.assertEqual(r['values']['chain'],75)

    def test_unknown_cost_condition_and_unlocks_are_not_guessed(self):
        self.data['skill']['sp_cost']=8
        r=self.fill();self.assertEqual(r['values']['attack'],0)
        self.assertTrue(any('实际 SP' in n for n in r['notes']))
        self.p['combat_inputs']['selected_skill']['actual_sp_cost']=8
        self.assertEqual(self.fill()['values']['attack'],200)
        self.p['combat_inputs']['selected_skill']['actual_sp_cost']=9
        self.assertEqual(self.fill()['values']['attack'],0)
        self.party=[dict(actor_id=2,style_label='BIYamawaki08')]
        self.p['combat_inputs']['selected_skill']['actual_sp_cost']=0
        self.assertEqual(self.fill()['values']['attack'],0)

    def test_funnel_after_hit_or_conditional_not_preapplied(self):
        part=self.data['skill']['parts'][1]
        part['hits'][0]['type']='After'
        self.assertEqual(self.fill()['values']['chain'],0)
        part['hits'][0]['type']='Before';part['cond']='DpRate()<0.5'
        self.assertEqual(self.fill()['values']['chain'],0)

    def test_audit_keeps_unresolved_resonance_and_runtime_condition(self):
        item=audit_entry('Passive.SupportUnknown',dict(name='共鸣测试',condition='DpRate()<0.5'))
        self.assertEqual(item['classification'],'条件待核对')
        text=audit_text([dict(actor='角色',combat_inputs=dict(passive_audit=[item]))])
        self.assertIn('共鸣测试',text);self.assertIn('DpRate()<0.5',text)
        self.assertIn('资料未匹配',text)

    def test_changed_rule_is_rejected(self):
        self.data['Passive.ConsumeSpAttackUp01']['condition']='OtherCondition()'
        self.assertEqual(self.fill()['values']['attack'],100)
