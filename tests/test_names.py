import unittest
from unittest.mock import patch
from hbr_live_app.names import Names
from hbr_live_app.events import ActionLedger
from hbr_live_app.history import table_rows
from test_battle import entry


class StyleTests(unittest.TestCase):
    def test_exact_style_lookup_and_shared_cache(self):
        with patch('hbr_data.store.Catalog.query', side_effect=[
            ([], [('角色 — Character', '风格甲')], False),
            ([], [('角色 — Character', '风格乙')], False),
        ]) as query:
            names = Names()
            self.assertEqual(names.actor('Card01'), '角色')
            self.assertEqual(names.style('Card01'), '风格甲')
            self.assertEqual(names.style('Card02'), '风格乙')
            self.assertEqual(query.call_count, 2)
            self.assertEqual(query.call_args.args[1], ('Card02',))

    def test_missing_catalog_preserves_label(self):
        with patch('hbr_data.store.Catalog.query', side_effect=OSError):
            names = Names()
            self.assertEqual(names.actor('Card01'), 'Card01')
            self.assertEqual(names.style('Card01'), '')

    def test_style_survives_event_settlement_and_table(self):
        ledger = ActionLedger()
        action = dict(entry([100], 1), style_label='Card02', style_name='完整风格名称', actor_position=1)
        first = ledger.update([action], {4})[0]
        last = ledger.update([], {4})[0]
        for event in (first, last):
            self.assertEqual(event['style_label'], 'Card02')
            self.assertEqual(event['style_name'], '完整风格名称')
            row = next(iter(table_rows([event]).values()))
            self.assertEqual(row['values'][1], 'Saki / 完整风格名称\n凌空铁锤')
            self.assertEqual(event['actor_position'], 1)
