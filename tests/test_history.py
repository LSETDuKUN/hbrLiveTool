import unittest
from hbr_live_app.history import table_rows
from hbr_live_app.turns import CommandLedger
from test_turns import context, event


class TableTests(unittest.TestCase):
    def test_full_front_line_and_single_extra_stay_in_their_slots(self):
        ledger = CommandLedger()
        actions = [dict(event(i + 1), actor=f'角色{i}', actor_id=i, actor_position=i) for i in (2, 0, 1)]
        events = ledger.update(actions, context(1))
        events += ledger.update([dict(event(4), actor='角色1', actor_id=1, actor_position=1)], context(2, additional=True))
        rows = list(table_rows(events).values())
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['values'], ('Turn 1', '角色0\n技能', '角色1\n技能', '角色2\n技能'))
        self.assertEqual(rows[1]['values'], ('Turn 1 / Extra', '/', '角色1\n技能', '/'))
        self.assertEqual([e['actor'] for e in rows[0]['events']], ['角色2', '角色0', '角色1'])

    def test_repeated_skills_and_unknown_positions_do_not_drop_events(self):
        ledger = CommandLedger()
        events = ledger.update([dict(event(1), actor_position=0), dict(event(2), actor_position=0, skill='再次行动'),
                                dict(event(3), actor='未知位置')], context(1))
        row = next(iter(table_rows(events).values()))
        self.assertIn('技能 / 再次行动', row['values'][1])
        self.assertEqual(row['values'][2], '/')
        self.assertEqual(row['unplaced'][0]['actor'], '未知位置')
        self.assertEqual(len(row['events']), 3)
        self.assertTrue(row['position_unknown'])

    def test_batch_roster_takes_precedence_and_changes_between_batches(self):
        ledger = CommandLedger()
        roster = [dict(actor_id=i, position=i, actor=f'角色{i}') for i in range(3)]
        ctx = dict(context(1), frontline=roster)
        # Event position may be read after a later swap; use the frozen roster.
        first = ledger.update([dict(event(1), actor_id=0, actor='角色0', actor_position=2)], ctx)[0]
        roster[0]['position'], roster[2]['position'] = 2, 0
        second = ledger.update([dict(event(2), actor_id=0, actor='角色0', actor_position=0)],
                               dict(context(2), frontline=roster))[0]
        rows = list(table_rows([first, second]).values())
        self.assertIn('角色0', rows[0]['values'][1])
        self.assertEqual(rows[0]['values'][3], '/')
        self.assertIn('角色0', rows[1]['values'][3])
        self.assertEqual(rows[1]['values'][1], '/')
