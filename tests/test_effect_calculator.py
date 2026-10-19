import unittest
from unittest.mock import patch
from hbr_live_app.effect_math import EffectInputs, calculate_effect
from hbr_live_app.effect_preview import proposals


def sample(typ='DefenseDown'):
    part=dict(label='effect',skill_type=typ,power=[.2,.3],diff_for_max=140,
              parameters=dict(str=0,dex=0,con=0,spr=0,wis=2,luk=1),growth=[0,0])
    player=dict(combat_inputs=dict(stats=dict(wisdom=300,luck=150),selected_skill=dict(label='skill',level=10)),statuses=[])
    enemy=dict(combat_inputs={'_defenseRefParam':200},statuses=[])
    return player,enemy,dict(name='测试',parts=[part])


class EffectTests(unittest.TestCase):
    def tearDown(self):
        # Collect destroyed Tk widgets on the main thread, before worker tests.
        import gc
        gc.collect()

    def test_debuff_floor_and_interpolation(self):
        i=EffectInputs(kind='debuff',minimum=20,maximum=30,threshold=100,attribute=50,enemy=100,over_rate=.001)
        self.assertEqual(calculate_effect(i)['base'],20)
        i.attribute=150;self.assertEqual(calculate_effect(i)['base'],25)
        i.attribute=250;r=calculate_effect(i)
        self.assertEqual(r['base'],30);self.assertEqual(r['over'],1.5)

    def test_buff_no_enemy_subtraction_growth_orb_and_over(self):
        i=EffectInputs(minimum=20,maximum=40,threshold=100,attribute=200,enemy=999,
                       level=10,growth_min=.03,growth_max=.02,orb=5,enhancement=20)
        r=calculate_effect(i)
        self.assertAlmostEqual(r['base'],47.2);self.assertAlmostEqual(r['orb'],8)
        self.assertAlmostEqual(r['over'],.944);self.assertAlmostEqual(r['final'],(47.2+8+.944)*1.2)

    def test_fixed_and_validation(self):
        self.assertEqual(calculate_effect(EffectInputs(kind='fixed',minimum=300))['final'],300)
        for kwargs in [dict(attribute=float('nan')),dict(level=1.5),dict(threshold=0),dict(orb=6),dict(enhancement=-1)]:
            with self.assertRaises(ValueError):calculate_effect(EffectInputs(**kwargs))

    def test_actual_weights_growth_calamity_and_runtime(self):
        p,e,db=sample();p['statuses']=[dict(label='SpecialStatus.Morale',values={'numValue':2})]
        e['statuses']=[dict(label='SpecialStatus.Misfortune'),dict(label='SpecialStatus.FearOfDevil')]
        p['combat_inputs']['selected_skill']['parts']=[dict(Label='effect',Power=.25)]
        row=proposals(p,e,lookup=lambda _:db)[0];v=row['values']
        self.assertEqual(v['attribute'],260);self.assertEqual(v['minimum'],25)
        self.assertEqual(v['growth_min'],0);self.assertEqual(v['reduction'],100)
        self.assertEqual(calculate_effect(EffectInputs(**v))['difference'],160)

    def test_scope_and_ambiguous_stacking(self):
        p,e,db=sample('MindEye')
        p['statuses']=[dict(label='SpecialStatus.GiveAttackBuffUp',values={'rateValueInt':2000})]
        self.assertEqual(proposals(p,e,lookup=lambda _:db)[0]['values']['enhancement'],0)
        db['parts'][0]['skill_type']='AttackUp'
        self.assertEqual(proposals(p,e,lookup=lambda _:db)[0]['values']['enhancement'],20)
        p['statuses']*=2
        self.assertEqual(proposals(p,e,lookup=lambda _:db)[0]['values']['enhancement'],0)
        p['statuses'][1]=dict(label='SpecialStatus.GiveAttackBuffUp',effective=False,values={'rateValueInt':9000})
        self.assertEqual(proposals(p,e,lookup=lambda _:db)[0]['values']['enhancement'],20)

    def test_fixed_passive_excluded_from_enhancement(self):
        p,e,db=sample('AttackUp');part=db['parts'][0]
        part.update(power=[3,0],diff_for_max=0,parameters=dict.fromkeys(part['parameters'],0))
        p['combat_inputs']['selected_skill']={};p['combat_inputs']['passive_audit']=[db]
        p['statuses']=[dict(label='SpecialStatus.GiveAttackBuffUp',values={'rateValueInt':2000})]
        row=proposals(p,e)[0]
        self.assertEqual(row['values']['kind'],'fixed')
        self.assertEqual(calculate_effect(EffectInputs(**row['values']))['final'],300)

    def test_missing_stats_not_silently_zero(self):
        p,e,db=sample();p['combat_inputs']['stats'].pop('luck')
        self.assertIsNone(proposals(p,e,lookup=lambda _:db)[0]['values']['attribute'])

    def test_editor_calculates_and_clears_stale_selection(self):
        import tkinter as tk
        from hbr_live_app.effect_editor import EffectEditor
        root=tk.Tk();root.withdraw()
        try:
            editor=EffectEditor(root);p,e,db=sample()
            with patch('hbr_live_app.effect_preview.catalog_skill',return_value=db):editor.load(p,e,{})
            self.assertIn('23.571%',editor.result.cget('text'))
            editor.values['enhancement'].set('20');editor.compute()
            self.assertIn('28.286%',editor.result.cget('text'))
            editor.load({},e,{})
            self.assertEqual(editor.values['enhancement'].get(),'0')
            self.assertIn('已清除',editor.result.cget('text'))
        finally:root.update_idletasks();root.destroy()

    def test_tabs_wrap_and_second_row_is_clickable(self):
        import tkinter as tk
        from hbr_live_app.components import TabBar
        root=tk.Tk();root.geometry('350x200')
        try:
            tabs=TabBar(root,['乘区试算','技能与属性','Buff／Debuff','当前内存参数'],lambda _:None)
            tabs.pack(fill='x');root.update();tabs.draw();root.update_idletasks()
            name,left,right,top=tabs._layout()[-1]
            self.assertGreater(top,0)
            self.assertEqual(tabs._hit((left+right)/2,top+22),name)
            self.assertGreaterEqual(int(tabs.cget('height')),top+44)
        finally:root.destroy()
