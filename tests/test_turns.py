import copy
import struct
import unittest
from unittest.mock import Mock

from hbr_live_app.turns import CommandLedger, TurnReader
from hbr_live_app.model import BattleModel


def context(count=1, turn=1, additional=False, od=False, selecting=False, activation=1):
    return dict(command_count=count, turn=turn, od=od, bonus=int(od), bonus_max=int(od),
                od_activation=activation if od else 0, od_before_enemy=od,
                additional=additional, extra=False, extra_turn=0, selecting=selecting)


def event(key, value=10):
    return dict(event_id=key, actor='角色', skill='技能', hits=[], value=value, settled=False)


class GroupTests(unittest.TestCase):
    def test_real_nanami_missing_context_recovers_into_turn_two(self):
        import json
        from pathlib import Path
        ledger, model = CommandLedger(), BattleModel()
        frames = json.loads((Path(__file__).parent / 'fixtures/missing_turn_context.json').read_text(encoding='utf-8'))
        totals = {}
        for frame in frames:
            totals.update({e['event_id']: e['value'] for e in frame['events']})
            events = ledger.update(frame['events'], frame['context'])
            model.update(dict(enemies=[], events=events))
        self.assertEqual(model.actions[8]['command']['turn'], 2)
        self.assertEqual(model.actions[8]['command']['command_visit'], 5)
        self.assertEqual(model.total, sum(totals.values()))
        self.assertEqual(len(model.actions), len(totals))

    def test_missing_sample_repairs_without_another_hit_event(self):
        ledger = CommandLedger()
        ctx = dict(context(5, turn=2), command_visit=5)
        ledger.update([], ctx)
        first = ledger.update([event(8)], None)[0]
        self.assertIsNone(first['command'])
        recovered = ledger.update([], ctx)
        self.assertEqual(recovered[0]['event_id'], 8)
        self.assertEqual(recovered[0]['command']['turn'], 2)
        self.assertIsNone(first['command'])
        self.assertEqual(ledger.update([], ctx), [])

    def test_gap_across_batches_is_not_reassigned(self):
        ledger = CommandLedger()
        ledger.update([], context(1))
        ledger.update([event(1)], None)
        self.assertEqual(ledger.update([], context(2, turn=2)), [])
        self.assertIsNone(ledger.update([event(1)], context(2, turn=2))[0]['command'])

    def test_repeated_additional_od_and_next_turn(self):
        ledger = CommandLedger()
        contexts = [context(1), context(2, additional=True), context(3, additional=True),
                    context(4, od=True), context(5, additional=True, od=True), context(6, turn=2)]
        groups = []
        for index, ctx in enumerate(contexts, 1):
            ledger.update([], dict(ctx, selecting=True))
            result = ledger.update([event(index * 10), event(index * 10 + 1)], ctx)
            self.assertEqual(result[0]['command'], result[1]['command'])
            groups.append(result[0]['command'])
        self.assertEqual([g['sequence'] for g in groups], [1, 2, 3, 4, 5, 6])
        self.assertEqual([g['turn'] for g in groups], [1, 1, 1, 1, 1, 2])
        self.assertTrue(groups[4]['additional'] and groups[4]['od'])

    def test_final_hits_keep_original_group_and_totals(self):
        ledger, model = CommandLedger(), BattleModel()
        first = ledger.update([event(1)], context(1, additional=True, od=True))[0]
        saved = copy.deepcopy(first)
        model.update(dict(enemies=[], events=[first]))
        final = ledger.update([dict(event(1, 90), settled=True), event(2)], context(2, turn=2))
        model.update(dict(enemies=[], events=final))
        self.assertEqual(final[0]['command'], saved['command'])
        self.assertEqual(first, saved)
        self.assertEqual(model.total, 100)
        exported = model.export()
        self.assertEqual(exported['actions'][0]['command']['turn'], 1)
        self.assertEqual(exported['actions'][1]['command']['turn'], 2)

    def test_selection_without_execution_is_not_an_action(self):
        ledger = CommandLedger()
        ledger.update([], context(1, selecting=True))
        ledger.update([], context(2, od=True, selecting=True))
        self.assertEqual(ledger.groups, {})
        result = ledger.update([event(1)], context(2, od=True))
        self.assertEqual(result[0]['command']['sequence'], 1)
        self.assertEqual(result[0]['command']['command_count'], 2)

    def test_pause_counter_gap_and_missing_context(self):
        ledger = CommandLedger()
        ledger.update([event(1)], context(3))
        later = ledger.update([event(2)], context(8, turn=3))[0]
        self.assertEqual(later['command']['sequence'], 2)
        self.assertEqual(later['command']['command_count'], 8)
        unknown = ledger.update([event(3)], None)[0]
        self.assertIsNone(unknown['command'])
        self.assertIsNone(ledger.update([event(3)], context(9))[0]['command'])

    def test_pending_context_survives_flags_reset_during_execution(self):
        ledger = CommandLedger()
        ledger.update([], context(1, additional=True, od=True, selecting=True))
        result = ledger.update([event(1)], context(1))
        self.assertTrue(result[0]['command']['additional'])
        self.assertTrue(result[0]['command']['od'])


class ReaderTests(unittest.TestCase):
    def make_reader(self, changing=False, truncated=False):
        reader = TurnReader.__new__(TurnReader)
        reader.r = Mock()
        reader._resolve = Mock(return_value=(200, 400, 500, 300, 100))
        reader.visit, reader.command_count = 0, 0
        reader.last_selection, reader.was_selecting = None, False
        reader.r.string.return_value = 'コマンド選択' 
        raw = bytearray(49)
        for offset, value in ((0, 1), (20, 1), (24, 1), (32, 1)):
            struct.pack_into('<i', raw, offset, value)
        raw[28] = raw[29] = raw[48] = 1
        reader.r.read.side_effect = [struct.pack('<I', 5), b'' if truncated else bytes(raw),
                                    struct.pack('<I', 6 if changing else 5)]
        reader.r.q.return_value = 100
        return reader

    def test_od_additional_overlap_and_unsigned_count(self):
        actual = self.make_reader().sample()
        self.assertEqual({k: actual[k] for k in context()}, context(5, additional=True, od=True, selecting=True))
        self.assertEqual(actual['command_visit'], 1)

    def test_transition_race_is_not_a_new_group(self):
        self.assertIsNone(self.make_reader(changing=True).sample())

    def test_read_failure_is_not_turn_zero(self):
        with self.assertRaisesRegex(RuntimeError, '读取中断'):
            self.make_reader(truncated=True).sample()


class MovingStateTests(unittest.TestCase):
    def test_real_auto_battle_events_split_into_six_batches(self):
        import json
        from pathlib import Path
        frames = json.loads((Path(__file__).parent / 'fixtures/auto_turn_events.json').read_text(encoding='utf-8'))
        reader = ReaderTests().make_reader()
        ledger = CommandLedger()
        model = BattleModel()
        original_total = {}
        for frame in frames:
            c = frame['context']
            self.assertEqual(c['command_count'], 1)  # Old implementation froze here.
            raw = bytearray(49)
            for offset, value in ((0, c['turn']), (20, c['bonus_max']), (24, c['bonus']), (32, c['od_activation'])):
                struct.pack_into('<i', raw, offset, value)
            raw[28] = c['od']
            raw[48] = c['additional']
            reader.r.read.side_effect = [struct.pack('<I', c['phase_count']), bytes(raw), struct.pack('<I', c['phase_count'])]
            reader.r.string.return_value = c['phase']
            events = ledger.update(frame['events'], reader.sample())
            model.update(dict(enemies=[], events=events))
            original_total.update({e['event_id']: e['value'] for e in frame['events']})
        self.assertEqual([(g['turn'], g['additional']) for g in ledger.groups.values()],
                         [(1, False), (1, True), (1, True), (2, False), (3, False), (3, True)])
        self.assertEqual(model.total, sum(original_total.values()))
        self.assertEqual(len(model.actions), len(original_total))

    def test_recorded_state_transitions_from_live_probe(self):
        import json
        from pathlib import Path
        frames = json.loads((Path(__file__).parent / 'fixtures/turn_state_transitions.json').read_text(encoding='utf-8'))
        reader = ReaderTests().make_reader()
        ledger = CommandLedger()
        result = []
        seen = set()
        for frame in frames:
            raw = bytearray(49)
            for offset, value in ((0, frame['turn']), (20, frame['maximum']),
                                  (24, frame['bonus']), (32, frame['activation'])):
                struct.pack_into('<i', raw, offset, value)
            raw[28] = raw[29] = frame['od']
            raw[48] = frame['additional']
            reader.r.read.side_effect = [struct.pack('<I', frame['count']), bytes(raw), struct.pack('<I', frame['count'])]
            reader.r.string.return_value = frame['phase']
            ctx = reader.sample()
            events = []
            if frame['phase'] == '味方ターンの行動を実行' and ctx['command_visit'] not in seen:
                seen.add(ctx['command_visit'])
                events = [event(len(seen))]
            result.extend(ledger.update(events, ctx))
        self.assertEqual([(e['command']['turn'], e['command']['od'], e['command']['additional']) for e in result],
                         [(1, False, True), (1, False, True), (1, True, False), (1, True, True), (2, False, False)])
        self.assertEqual([e['command']['sequence'] for e in result], [1, 2, 3, 4, 5])

    def test_current_state_replacement_constant_old_counter_and_repeated_extra(self):
        from unittest.mock import patch
        r = Mock()
        pointers = {1064: 2000, 1016: 3000, 3168: 4000, 4048: 5000, 5224: 6000}
        classes = {2000: 'BattleInfoManager', 3000: 'BattleState', 4000: 'SubStateModule',
                   5000: 'ArborFSM', 6000: 'State', 7000: 'State', 8000: 'State', 9000: 'ArborFSM'}
        r.q.side_effect = lambda address: pointers.get(address, address)
        r.cls.side_effect = lambda address: classes.get(address)
        current_name = ['コマンド選択']
        r.string.side_effect = lambda _: current_name[0]
        values = dict(turn=1, additional=False, count=1)
        def read(address, size):
            if address == 2016:
                raw = bytearray(49)
                struct.pack_into('<i', raw, 0, values['turn'])
                raw[48] = values['additional']
                return bytes(raw)
            # The old command object's counter remains readable but frozen.
            return struct.pack('<I', 1 if address == 6088 else values['count'])
        r.read.side_effect = read
        with patch.object(TurnReader, '_check'):
            reader = TurnReader(r, 1000)
            ledger = CommandLedger()
            ledger.update([], reader.sample())
            pointers[5224] = 7000
            current_name[0] = '味方ターンの行動を実行'
            first = ledger.update([event(1)], reader.sample())[0]
            for index in (2, 3):
                # A new/current command object uses the same count, and the same
                # Turn + additional flag repeats. Both visits must stay separate.
                pointers[5224] = 8000
                current_name[0] = 'コマンド選択'
                values['additional'] = True
                ledger.update([], reader.sample())
                pointers[5224] = 7000
                current_name[0] = '味方ターンの行動を実行'
                result = ledger.update([event(index)], reader.sample())[0]
                self.assertEqual(result['command']['sequence'], index)
                self.assertTrue(result['command']['additional'])
            # Refresh the FSM path as well, not just the current node pointer.
            pointers[4048] = 9000
            pointers[9224] = 8000
            current_name[0] = 'コマンド選択'
            values.update(turn=2, additional=False)
            ledger.update([], reader.sample())
            pointers[9224] = 7000
            current_name[0] = '味方ターンの行動を実行'
            result = ledger.update([event(4), dict(event(1, 50), settled=True)], reader.sample())
            self.assertEqual(result[0]['command']['turn'], 2)
            self.assertEqual(result[0]['command']['sequence'], 4)
            self.assertEqual(result[1]['command'], first['command'])
