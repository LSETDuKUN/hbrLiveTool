import unittest
from hbr_live_app.history import table_rows
from hbr_live_app.model import BattleModel


class ODMarkerTests(unittest.TestCase):
    def test_activation_before_bonus_and_after_normal_action(self):
        for timing in ('前置','后置'):
            with self.subTest(timing=timing):
                model=BattleModel()
                if timing=='后置':
                    normal=dict(event_id='normal',actor='A',skill='普攻',value=1,command=dict(id=1,turn=1))
                    model.update(dict(enemies=[],events=[normal],planned_events=[normal]))
                active=dict(enemies=[],turn_context=dict(turn=1,od=True,od_before_enemy=timing=='后置'),
                            od_state=dict(available=True,active=True,level=2))
                model.update(active)
                for mode,events in [('actual',model.actions),('planned',model.planned_actions)]:
                    rows=table_rows(events.values(),model.od_markers,mode)
                    self.assertEqual(list(rows.values())[-1]['values'][0],'OD2 · '+timing)
                bonus=dict(event_id='bonus',actor='A',skill='技能',value=2,command=dict(id=2,turn=1,od=True,bonus=1,od_level=2))
                model.update(dict(active,events=[bonus],planned_events=[bonus]))
                self.assertEqual(len(model.od_markers),1)
                labels=[row['values'][0] for row in table_rows(model.actions.values(),model.od_markers).values()]
                expected=['Turn 1'] if timing=='后置' else []
                self.assertEqual(labels,expected+['OD2 · '+timing,'Turn 1 / Bonus 1'])
