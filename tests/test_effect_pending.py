import unittest
from unittest.mock import patch
from hbr_live_app.effect_pending import pending_state,with_pending
from hbr_live_app.statuses import infer_suppressed_attacks
from hbr_live_app.damage_autofill import autofill
from test_compound_skills import actors,DATA


def debuff(value,element=None,permanent=False):
    return dict(label='SpecialStatus.DefenseDown',element_type=3 if element else 0,element_key=element,
                duration_kind='permanent' if permanent else 'turn',remaining=2,
                values=dict(amountOnDpDamageInt=-value*100,amountOnHpDamageInt=-value*100))


def item():
    return dict(title='预添加减防',caster=1,source='test',passive=False,part=dict(label='test',skill_type='DefenseDown',
                target_type='Single',elements=[],effect={'exitCond':'EnemyTurnEnd','limitType':'Default'}))


class PendingTests(unittest.TestCase):
    def tearDown(self):
        import gc
        gc.collect()

    def test_same_element_encodings_compete_and_permanent_adds(self):
        p,e=actors('STezukaSkill02')
        e['statuses']=[debuff(10,'Thunder'),debuff(20,'Thunder'),debuff(30)]
        e['statuses'][2]['element_type']=3
        e['statuses'].append(debuff(5,'Thunder',True))
        self.assertEqual(autofill(p,e,lookup=DATA.get)['values']['element_defense_down'],55)

    def test_debuff_display_suppression_releases_after_expiry(self):
        statuses=[debuff(10),debuff(20),debuff(30),debuff(5,permanent=True)]
        infer_suppressed_attacks(statuses)
        self.assertFalse(statuses[0]['effective'])
        self.assertNotIn('effective',statuses[3])
        statuses[2]['remaining']=0
        infer_suppressed_attacks(statuses)
        self.assertNotIn('effective',statuses[0])

    def test_snapshot_copy_and_restrictions(self):
        p,e=actors('STezukaSkill02');side,state=pending_state(item(),20,e)
        _,new=with_pending(p,e,[dict(enemy=side,state=state)])
        self.assertEqual(len(new['statuses']),1);self.assertEqual(e['statuses'],[])
        passive=dict(item(),passive=True)
        with self.assertRaises(ValueError):pending_state(passive,20,e)
        own=item();own['part'].update(skill_type='AttackUp',target_type='Self')
        with self.assertRaises(ValueError):pending_state(own,20,dict(actor_id=2))

    def test_ui_add_remove_preserves_manual_offset_and_applies_top_two(self):
        import tkinter as tk
        from hbr_live_app.damage_window import DamageWindow
        root=tk.Tk();root.withdraw()
        try:
            w=DamageWindow(root,lambda:{})
            p,e=actors('STezukaSkill02');p['actor_id']=1;e['address']=2
            e['statuses']=[debuff(10),debuff(20)]
            base=autofill(p,e,lookup=DATA.get)
            w.pending_context=(p,e,None,{},[p]);w.pending_base=base
            w.values['defense_down'].set('35') # live 30 + manual 5
            w.values['base'].set('100');w.use_skill.set(False)
            with patch('hbr_live_app.damage_window.autofill',side_effect=lambda p,e,f,**kw:autofill(p,e,f,lookup=DATA.get,**kw)):
                w.update_pending('add',(item(),30))
                self.assertEqual(float(w.values['defense_down'].get()),55)
                w.update_pending('add',(item(),5))
                self.assertEqual(float(w.values['defense_down'].get()),55)
                w.update_pending('remove',0)
                self.assertEqual(float(w.values['defense_down'].get()),35)
                w.update_pending('remove',0)
                self.assertEqual(float(w.values['defense_down'].get()),35)
            w.destroy()
        finally:root.update_idletasks();root.destroy()

    def test_orb_requires_explicit_enable_and_defaults_to_five(self):
        import tkinter as tk
        from hbr_live_app.effect_editor import EffectEditor
        root=tk.Tk();root.withdraw()
        try:
            editor=EffectEditor(root)
            for k,v in dict(minimum=20,maximum=40,threshold=100,attribute=200).items():editor.values[k].set(str(v))
            self.assertFalse(editor.orb_enabled.get());self.assertEqual(editor.orb_level.get(),'5')
            self.assertEqual(editor.calculate()['orb'],0)
            editor.orb_enabled.set(True);self.assertEqual(editor.calculate()['orb'],8)
            editor.orb_level.set('1');self.assertEqual(editor.calculate()['orb'],1.6)
            editor.orb_enabled.set(False);self.assertEqual(editor.calculate()['orb'],0)
        finally:root.update_idletasks();root.destroy()
