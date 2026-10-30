import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from hbr_live_app.player_transitions import PlayerTransitions
from hbr_live_app.formation import FormationReader


class PlayerTransitionTests(unittest.TestCase):
    def test_initial_used_button_is_explicitly_marked_not_invented_activation(self):
        from hbr_live_app.turns import CommandLedger,context_label
        from hbr_live_app.model import BattleModel
        t=PlayerTransitions();p=dict(actor_id=1,actor='咲',style_label='STezuka03',style_name='风格',mode_count=1,actor_position=0)
        events=t.update([p],now=0)
        events=CommandLedger().update(events,dict(turn=2,command_count=1,selecting=True))
        self.assertTrue(events[0]['observed_before_connection'])
        self.assertNotIn('turn',events[0]['command'])
        self.assertIn('时点未知',context_label(events[0]['command']))
        model=BattleModel();model.update(dict(enemies=[],events=events))
        self.assertEqual(len(model.planned_actions),1)
        self.assertEqual(model.total,0)
        t.invalidate();self.assertFalse(t.update([p],now=2))
        self.assertEqual(t.update([dict(p,mode_count=2)],now=2.1)[0]['skill'],'鬼神化')
    def test_recorded_saki_activation_without_action_entry_is_recorded_once(self):
        frames = json.loads((Path(__file__).parent/'fixtures/saki_mode.json').read_text(encoding='utf-8'))
        tracker = PlayerTransitions()
        r, roster, names = Mock(), Mock(), Mock()
        r.q.return_value = 123
        roster.sample.return_value = [dict(actor_id=1000, position=0, actor='STezuka03')]
        names.actor.return_value = '手冢 咲'
        names.style.return_value = '希望的拂晓'
        results = []
        for index, frame in enumerate(frames):
            self.assertEqual(frame['actions'], [])
            r.fields.return_value = dict(fields=frame['fields'])
            values = {1000+f['offset']: f['value'] for f in frame['fields']}
            r.i.side_effect = lambda addr: values[addr]
            r.read.side_effect = lambda addr, size: bytes([values[addr]])
            states = tracker.sample(r, roster, names)
            results += tracker.update(states, now=index*.1)
            self.assertEqual(tracker.update(states, now=index*.1+.01), [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['skill'], '鬼神化')
        self.assertTrue(results[0]['instant'])
        self.assertEqual(results[0]['value'], 0)

    def test_style_form_changes_and_reconnection_baseline(self):
        t = PlayerTransitions()
        state = dict(actor_id=1, actor_position=4, actor='角色', style_label='A', style_name='风格A', another_form=False)
        self.assertEqual(t.update([state], now=0), [])
        result = t.update([dict(state, another_form=True)], now=.1)
        self.assertIn('形态切换', result[0]['skill'])
        result = t.update([dict(state, style_label='B', style_name='风格B')], now=.2)
        self.assertIn('风格A → 风格B', result[0]['skill'])
        t.invalidate()
        self.assertEqual(t.update([state], now=.3), [])
        self.assertEqual(t.update([dict(state, another_form=True)], now=3), [])

    def test_full_roster_selected_even_with_front_and_sub_lists(self):
        from test_formation import FormationTests
        reader, _ = FormationTests().setup_reader()
        reader.r.fields.return_value = dict(fields=[
            dict(name='<frontPlayerList>k__BackingField', offset=144, type=21),
            dict(name='<subPlayerList>k__BackingField', offset=152, type=21),
            dict(name='<playerList>k__BackingField', offset=160, type=21)])
        with patch('hbr_live_app.source.members', return_value=[10000,11000,12000]):
            self.assertEqual(len(reader.sample(all_players=True)), 3)
            self.assertEqual(reader.offset, 160)
