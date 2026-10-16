import sys
import tkinter as tk
import unittest
from unittest.mock import patch
from hbr_live_app.app import App


class DashboardTests(unittest.TestCase):
    def test_six_portraits_stay_fixed_on_swap_and_details_start_collapsed(self):
        players=[dict(actor_id=i+1,actor_position=i,actor=f'角色{i}',style_label='',statuses_available=True,statuses=[]) for i in range(6)]
        panel=self.app.player_panel
        panel.update_state(players,None)
        order=list(panel.order)
        tiles={key:value['frame'] for key,value in panel.tiles.items()}
        self.assertEqual(len(tiles),6)
        self.assertEqual(panel.detail.winfo_manager(),'')
        players[0]=dict(players[0],actor_position=3)
        players[3]=dict(players[3],actor_position=0)
        panel.update_state(players,None)
        self.assertEqual(panel.order,order)
        self.assertEqual({key:value['frame'] for key,value in panel.tiles.items()},tiles)
        self.assertEqual(panel.tiles[4]['badge'].cget('text'),'前排 · 中')
        panel.update_state([],None)
        self.assertEqual(panel.order,order)
        self.assertEqual(panel.tiles[4]['badge'].cget('text'),'暂不可读')
        panel.update_state(players,None)
        self.assertEqual(panel.order,order)
        self.assertEqual({key:value['frame'] for key,value in panel.tiles.items()},tiles)
        panel.select(4)
        self.assertEqual(panel.detail.winfo_manager(),'pack')
        panel.select(4)
        self.assertEqual(panel.detail.winfo_manager(),'')
        panel.reset()
        self.assertEqual(panel.order,[])
        self.assertEqual(panel.tiles,{})

    def test_compact_hides_players_without_losing_samples(self):
        self.app.compact.set(True);self.app.change_compact()
        self.assertFalse(self.app.players_visible.get())
        self.assertEqual(self.app.allies.winfo_manager(),'')
        self.app.compact.set(False);self.app.change_compact()
        self.assertEqual(self.app.allies.winfo_manager(),'grid')

    def test_portraits_target_and_text_toggle(self):
        from test_command_damage import event
        photo = tk.PhotoImage(master=self.root, width=44, height=44)
        e = dict(event(1, 0), actor_id=3, style_label='STezuka03',
                 targets=[dict(address=9, name='苍井', is_player=True, style_label='EAoi04', style_name='风格')])
        with patch.object(self.app.tree.portraits, 'get', return_value=photo) as lookup:
            self.app.model.update(dict(enemies=[], events=[e]))
            self.app.render([e])
            canvas = self.app.tree.canvas
            self.assertEqual(len([i for i in canvas.find_all() if canvas.type(i) == 'image']), 2)
            images = [i for i in canvas.find_all() if canvas.type(i) == 'image']
            skills = [i for i in canvas.find_all() if canvas.type(i) == 'text' and canvas.itemcget(i, 'text') == e['skill']]
            self.assertEqual(canvas.coords(images[0])[1], canvas.coords(images[1])[1])
            self.assertEqual(canvas.coords(images[0])[1], canvas.coords(skills[0])[1])
            self.assertIn((('EAoi04',),), [(call.args,) for call in lookup.call_args_list])
            self.app.tree.toggle_portraits()
            self.assertFalse(any(canvas.type(i) == 'image' for i in canvas.find_all()))
            texts = [canvas.itemcget(i, 'text') for i in canvas.find_all() if canvas.type(i) == 'text']
            self.assertIn('→ 苍井 / 风格', texts)

    def test_enemy_effect_text_expands_card_without_overlapping_footer(self):
        branch = dict(skills=['技能'], effects=['5 Hit · 全体 · 资料威力 2075–24900（非实伤） · 混乱'],
                      status='matched', share=1, weight=100)
        self.app.model.update(dict(enemies=[dict(address=4, hp=100, dp=100, name='敌人',
             forecast=dict(branches=[branch], text='技能', blink=False))], events=[]))
        self.app.render()
        card = self.app.enemy_cards[4]
        with patch.object(card, 'winfo_width', return_value=300):
            card.draw()
        effects = card.find_withtag('skill_effects')
        self.assertEqual(len(effects), 1)
        self.assertLess(card.bbox(effects[0])[3], card.footer_y)
    def test_command_damage_cards_accumulate_and_settle_animation(self):
        from test_command_damage import event
        for value in (1000, 11086):
            e = event(1, value)
            self.app.model.update(dict(enemies=[], events=[e]))
            self.app.render([e])
        self.assertEqual(self.app.total_label.cget('text'), '11,086')
        self.assertEqual(self.app.current_damage_label.cget('text'), '1,000 + 10,086')
        self.root.after_cancel(self.app.damage_timer)
        self.app.settle_damage()
        self.assertEqual(self.app.current_damage_label.cget('text'), '11,086')
        e = event(2, 10, command=2)
        self.app.model.update(dict(enemies=[], events=[e]))
        self.app.render([e])
        self.assertEqual(self.app.total_label.cget('text'), '11,086')
        self.assertEqual(self.app.current_damage_label.cget('text'), '0 + 10')

    def test_history_uses_independent_window_without_losing_records(self):
        self.assertFalse(self.app.history_visible.get())
        self.assertEqual(self.app.history_window.state(), 'withdrawn')
        self.assertEqual(self.app.allies.grid_info()['column'], 0)
        self.assertEqual(self.app.resources.grid_info()['column'], 1)
        event = dict(event_id=1, actor='角色', skill='技能', value=1, hits=[], settled=True)
        self.app.model.update(dict(enemies=[], events=[event]))
        self.app.render([event])
        for visible in (True, False, True):
            self.app.history_visible.set(visible)
            self.app.toggle_history()
            self.assertEqual(self.app.history_window.state(), 'normal' if visible else 'withdrawn')
            self.assertEqual(len(self.app.model.actions), 1)
        self.app.hide_history()
        self.assertFalse(self.app.history_visible.get())

    def test_only_battle_end_offers_save_once_and_decline_does_not_export(self):
        self.app.model.actions[1] = dict(event_id=1, actor='角色', skill='技能', value=1, hits=[], settled=True)
        self.app.queue.put(('stopped', None))
        with patch.object(self.app.root, 'after_idle') as later:
            self.app.pump()
            later.assert_not_called()
            self.app.queue.put(('battle_end', dict(run_id='one')))
            self.app.queue.put(('battle_end', dict(run_id='one')))
            self.app.pump()
            later.assert_called_once()
        with patch('hbr_live_app.app.messagebox.askyesno', return_value=False), \
                patch.object(self.app, 'export_axis') as export:
            self.app.offer_axis(self.app.model.export())
            export.assert_not_called()
        with patch('hbr_live_app.app.messagebox.askyesno', return_value=True), \
                patch.object(self.app, 'export_axis') as export:
            self.app.offer_axis(self.app.model.export())
            export.assert_called_once()

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        with patch.object(App, '_load_settings', return_value={}):
            self.app = App(self.root)

    def tearDown(self):
        self.app.closing = True
        for card in self.app.enemy_cards.values():
            card.set_monitoring(False)
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

    def test_enemy_card_names_forecast_lifecycle_and_details(self):
        from types import SimpleNamespace
        state = dict(address=4, dp=100, hp=500, name='Internal',
                     names=[dict(kind='cn', name='中文敌人'), dict(kind='en', name='English Enemy'),
                            dict(kind='internal', name='Internal')],
                     forecast=dict(text='规则预告：Heavy Burst', blink=True), action_rules='DP 阶段规则')
        self.app.model.update(dict(enemies=[state], events=[]))
        self.app.render([])
        card = self.app.enemy_cards[4]
        card.set_monitoring(True)
        self.assertIsNotNone(card.timer)
        card.click(SimpleNamespace(y=16))
        self.assertEqual(card.name_kind, 'en')
        card.update_state(self.app.model.enemies[4])
        self.assertEqual(card.name_kind, 'en')
        with patch.object(self.app, 'text_window') as show:
            card.click(SimpleNamespace(y=card.footer_y))
            self.assertIn('English Enemy', show.call_args.args[1])
            self.assertIn('DP 阶段规则', show.call_args.args[1])
        card.set_monitoring(False)
        self.assertIsNone(card.timer)

        card.set_monitoring(True)
        card.update_state(dict(self.app.model.enemies[4], dp=50))
        self.assertIsNotNone(card.trail_timer)
        self.assertEqual(card.state['dp'], 50)
        card.set_monitoring(False)
        self.assertIsNone(card.trail_timer)
        card.set_monitoring(True)
        card.update_state(dict(self.app.model.enemies[4], active=False))
        self.assertIsNone(card.timer)

    def test_enemy_wheel_branches_and_progress_animation(self):
        from hbr_live_app.enemy_prediction import predict
        info = dict(patterns={'dp': dict(l='rules', p=[
            dict(id=1, order=1, weight=75, skill_list=[1, 2]),
            dict(id=2, order=1, weight=25, skill_list=[2]),
            dict(id=3, order=2, weight=100, skill_list=[2])])},
            skills={1: dict(name='技能甲'), 2: dict(name='技能乙')})
        live = dict(dp=100, dp_order=0, hp_order=0, dp_pattern='rules', down=0, overridden=False)
        preview = predict(info, live, dict(selecting=True))
        enemy = dict(address=4, dp=100, hp=500, name='敌人', forecast=preview)
        self.app.model.update(dict(enemies=[enemy], events=[]))
        self.app.render([])
        card = self.app.enemy_cards[4]
        card.set_monitoring(True)
        with patch.object(card, 'winfo_width', return_value=300):
            card.draw()
        texts = [card.itemcget(i, 'text') for i in card.find_all() if card.type(i) == 'text']
        self.assertIn('75% 权重', texts)
        self.assertIn('25% 权重', texts)
        self.assertTrue(any('1 技能甲' in text and '2 技能乙' in text for text in texts))
        self.assertGreater(card.footer_y, 219)
        live['dp_order'] = 1
        enemy['forecast'] = predict(info, live, dict(selecting=True))
        self.app.model.update(dict(enemies=[enemy], events=[]))
        self.app.render([])
        self.assertIsNotNone(card.wheel_timer)
        card.set_monitoring(False)
        card.rotate()
        self.assertIsNone(card.wheel_timer)

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
        self.assertEqual(canvas.itemcget(actor_items[0], 'fill'), '#bdb1d4')
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
