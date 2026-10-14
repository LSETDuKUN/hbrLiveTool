import sys
import tkinter as tk
import unittest
from unittest.mock import patch
from hbr_live_app.app import App


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        with patch.object(App, '_load_settings', return_value={}):
            self.app = App(self.root)

    def tearDown(self):
        self.app.closing = True
        self.root.update_idletasks()
        for after in self.root.tk.call('after', 'info'):
            self.root.after_cancel(after)
        self.root.destroy()

    def test_event_updates_existing_row_and_refilled_meter(self):
        enemy = dict(address=4, dp=100, hp=500, name='测试敌人')
        event = dict(event_id=1, actor='Saki', skill='凌空铁锤', value=50, settled=False,
                     hits=[dict(target=4, damage=50, funnel=False, critical=True)])
        self.app.model.update(dict(enemies=[enemy], events=[event]))
        self.app.render([event])
        event = dict(event, value=75, settled=True)
        enemy = dict(enemy, dp=300)
        self.app.model.update(dict(enemies=[enemy], events=[event]))
        self.app.render([event])
        self.assertEqual(len(self.app.tree.get_children()), 1)
        self.assertEqual(self.app.enemy_cards[4].state['dp'], 300)
        self.assertEqual(self.app.total_label.cget('text'), '75')
        self.assertIn('凌空铁锤', self.app.detail_text())

    def test_layout_switch_and_ocr_independence(self):
        for compact in [True, False, True]:
            self.app.compact.set(compact)
            self.app.layout()
            self.root.update_idletasks()
        self.assertFalse(any(k.startswith(('hbr_capture', 'hbr_recog')) for k in sys.modules))

    def test_three_enemy_cards_and_target_damage_detail(self):
        enemies = [dict(address=n, dp=n*100, hp=n*1000, name='测试敌人') for n in (4, 5, 6)]
        event = dict(event_id=1, actor='Saki', skill='群体技能', value=300, settled=True,
                     hits=[dict(target=n, damage=amount, funnel=False, critical=False)
                           for n, amount in [(4, 100), (6, 200)]])
        self.app.model.update(dict(enemies=enemies, events=[event]))
        self.app.render([event])
        self.assertEqual(len(self.app.enemy_cards), 3)
        self.assertEqual(self.app.enemy_cards[5].state['hp'], 5000)
        self.assertEqual(self.app.target_summary(event), '敌1、敌3')
        self.assertIn('敌1 100 / 敌3 200', self.app.detail_text())

    def test_pause_does_not_clear_model(self):
        self.app.connected = True
        self.app.model.run_id = 'keep'
        self.app.toggle_pause()
        self.assertTrue(self.app.paused.is_set())
        self.app.toggle_pause()
        self.assertFalse(self.app.paused.is_set())
        self.assertEqual(self.app.model.run_id, 'keep')

    def test_command_table_positions_updates_and_folded_details(self):
        from hbr_live_app.turns import CommandLedger
        from test_turns import context, event
        ledger = CommandLedger()
        events = ledger.update([dict(event(1), actor_position=1)], context(5, additional=True, od=True))
        self.app.model.update(dict(enemies=[], events=events))
        self.app.render(events)
        self.assertEqual(len(self.app.tree.get_children()), 1)
        iid = self.app.tree.get_children()[0]
        values = self.app.tree.item(iid, 'values')
        self.assertEqual(values, ('Turn 1 / Bonus 1 / Extra', '角色\n技能', '/', '/'))
        self.assertFalse(self.app.details_open)
        canvas = self.app.tree.canvas
        labels = canvas.find_withtag('context')
        self.assertEqual(''.join(canvas.itemcget(i, 'text') for i in labels), 'Turn 1 / Bonus 1 / Extra')
        self.assertEqual(len({canvas.coords(i)[1] for i in labels}), 1)

    def test_long_style_truncated_only_in_table(self):
        style = '完整而且很长的风格名称' * 8
        event = dict(event_id=1, actor='角色', actor_position=1, style_name=style,
                     style_label='Card02', skill='技能', value=0, hits=[], settled=True)
        self.app.model.update(dict(enemies=[], events=[event]))
        self.app.render([event])
        canvas = self.app.tree.canvas
        titles = [canvas.itemcget(i, 'text') for i in canvas.find_all() if canvas.type(i) == 'text']
        self.assertTrue(any(t.startswith('角色 / ') and t.endswith('…') for t in titles))
        self.assertIn(style, self.app.detail_text())
        self.assertIn('Card02', self.app.detail_text())

    def test_unknown_row_moves_after_recovery_and_text_is_centered(self):
        from hbr_live_app.turns import CommandLedger
        from test_turns import context, event
        ledger = CommandLedger()
        ledger.update([], context(2, turn=2))
        unknown = ledger.update([dict(event(1), actor_position=1)], None)
        self.app.model.update(dict(enemies=[], events=unknown))
        self.app.render(unknown)
        self.assertEqual(self.app.tree.get_children(), ('unknown:1',))
        repaired = ledger.update([], context(2, turn=2))
        self.app.model.update(dict(enemies=[], events=repaired))
        self.app.render(repaired)
        self.assertEqual(self.app.tree.get_children(), ('command:2',))
        self.assertEqual(self.app.tree.selection(), ('command:2',))
        canvas = self.app.tree.canvas
        actor_items = [i for i in canvas.find_all() if canvas.type(i) == 'text' and canvas.itemcget(i, 'text') == '角色']
        self.assertEqual(canvas.itemcget(actor_items[0], 'justify'), 'center')
        self.assertEqual(canvas.itemcget(actor_items[0], 'fill'), '#ffe4af')
        updated = ledger.update([event(1, 50)], context(6, turn=2))
        # Positions normally arrive on every event from ActionLedger.
        updated[0]['actor_position'] = 1
        self.app.model.update(dict(enemies=[], events=updated))
        self.app.render(updated)
        self.assertEqual(len(self.app.tree.get_children()), 1)
        self.assertIn('合计 50', self.app.detail_text())
        self.app.toggle_details()
        self.assertTrue(self.app.details_open)
        self.app.toggle_details()
        self.assertFalse(self.app.details_open)
