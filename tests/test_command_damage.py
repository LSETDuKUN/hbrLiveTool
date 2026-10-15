import unittest
from hbr_live_app.model import BattleModel
from hbr_live_app.turns import CommandLedger
from hbr_live_app.history import table_rows
from hbr_live_app.events import ActionLedger


def event(key, value, command=1, **kwargs):
    return dict(event_id=key, value=value, actor='角色', skill='技能', hits=[], settled=False,
                actor_position=1, command=dict(id=command, turn=1, od=False), **kwargs)


class CommandDamageTests(unittest.TestCase):
    def test_peak_current_updates_not_double_counted_and_late_hits_keep_batch(self):
        m = BattleModel()
        def put(*events): m.update(dict(enemies=[], events=events))
        self.assertEqual(m.command_damage['maximum'], 0)
        put(event(1, 1000))
        put(event(1, 11086))
        put(event(2, 100, skill_label='Passive.Pursuit_A'))
        self.assertEqual(m.command_damage['current'], 11186)
        put(event(3, 0, command=2))
        self.assertEqual(m.command_damage['current'], 0)
        put(event(3, 2000, command=2), event(2, 200, skill_label='Passive.Pursuit_A'))
        self.assertEqual(m.command_damage, dict(current_id=2, current=2000, maximum=11286))
        put(event(3, 20000, command=2))
        self.assertEqual(m.command_damage['maximum'], 20000)
        put(event(4, 99999, command='instant:4', instant=True))
        self.assertEqual(m.command_damage['maximum'], 99999)
        self.assertEqual(m.command_damage['current'], 99999)

    def test_pursuit_collapses_without_mutating_raw_events(self):
        events = [event(1, 100), event(2, 50, skill_label='Passive.Pursuit_A')]
        row = next(iter(table_rows(events).values()))
        self.assertEqual(len(row['slots'][0]), 1)
        self.assertIn('追', row['values'][1])
        self.assertEqual(len(row['events']), 2)
        self.assertNotIn('pursuit_count', events[0])
        self.assertEqual(table_rows([events[1]]), {})

    def test_instant_has_own_row_does_not_consume_command_and_keeps_late_hits(self):
        ledger = CommandLedger()
        context = dict(command_count=1, command_visit=1, selecting=True, turn=1, od=False)
        first = ledger.update([event(1, 100, instant=True)], context)[0]
        self.assertEqual(first['command']['kind'], 'instant')
        self.assertEqual(len(ledger.groups), 0)
        updates = ledger.update([event(2, 200)], dict(context, selecting=False))
        next_event = updates[-1]
        model = BattleModel()
        model.update(dict(enemies=[], events=[first]))
        self.assertEqual(model.command_damage['current'], 100)
        model.update(dict(enemies=[], events=updates))
        self.assertEqual(model.command_damage['current'], 300)
        self.assertEqual(model.total, 300)
        self.assertEqual(next_event['command']['id'], 1)
        late = ledger.update([event(1, 300, instant=True)], dict(context, command_count=2))[0]
        self.assertEqual(late['command'], first['command'])
        self.assertEqual(len(table_rows([first, next_event])), 2)

    def test_zero_damage_button_is_observed_by_execution(self):
        ledger = ActionLedger()
        results = ledger.update([dict(address=1, actor=2, skill='button', hit_set=0,
            actor_name='小按钮', skill_name='鬼神化', instant=True, actor_is_player=True,
            executing=True, hits=[])], set())
        self.assertTrue(results[0]['instant'])
        self.assertEqual(results[0]['value'], 0)
