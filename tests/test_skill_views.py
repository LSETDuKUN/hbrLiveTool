import unittest
from copy import deepcopy
from hbr_data.skill_views import variants
from hbr_data.details import skill_detail
from hbr_data.cards import effect_category
from hbr_live_app.status_rules import active
from test_compound_skills import DATA


class ViewTests(unittest.TestCase):
    def tearDown(self):
        import gc
        gc.collect()

    def test_source_unchanged_and_branch_hit_data_preserved(self):
        root=deepcopy(DATA['FMikotoSkill51']);before=deepcopy(root)
        root['parts'].append({'skill_type':'HealSp','power':[3,0]})
        options=variants(root)
        self.assertEqual([name for name,_ in options],['OD 中','非 OD'])
        self.assertEqual(options[0][1]['parts'][0]['power'],[7125,14250])
        self.assertEqual(options[1][1]['parts'][0]['power'],[5445,10890])
        self.assertTrue(all(d['parts'][-1]['skill_type']=='HealSp' for _,d in options))
        self.assertTrue(all(len(d['hits'])==8 for _,d in options))
        self.assertEqual(root['parts'][0],before['parts'][0])

    def test_effect_enhancement_is_buff_and_unknown_duration_does_not_crash(self):
        s=skill_detail({'parts':[{'skill_type':'GiveDebuffUp'}]})
        self.assertEqual(effect_category(s.effects[0]),'增益')
        self.assertTrue(active({'duration_kind':'turn','remaining':None}))
        self.assertFalse(active({'duration_kind':'turn','remaining':0}))

    def test_ui_switch_keeps_one_card_and_replaces_content(self):
        import tkinter as tk
        from hbr_data.cards import DetailCards
        root=tk.Tk();root.withdraw()
        try:
            cards=DetailCards(root)
            cards.render_skill(skill_detail(DATA['FMikotoSkill51']),1)
            def descendants(w):
                for child in w.winfo_children():
                    yield child
                    yield from descendants(child)
            buttons=[w for w in descendants(cards) if isinstance(w,tk.Radiobutton)]
            self.assertEqual(len(buttons),2)
            def text():return '\n'.join(str(w.cget('text')) for w in descendants(cards) if isinstance(w,tk.Label))
            self.assertIn('×3.75',text())
            buttons[1].invoke();root.update_idletasks()
            self.assertIn('×3.25',text());self.assertNotIn('×3.75',text())
            self.assertEqual(len(buttons),2)
        finally:root.update_idletasks();root.destroy()
