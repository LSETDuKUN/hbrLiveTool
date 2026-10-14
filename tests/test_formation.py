import unittest
from unittest.mock import Mock, patch
from hbr_live_app.formation import FormationReader


class FormationTests(unittest.TestCase):
    def setup_reader(self):
        r = Mock()
        pointers = {1144: 2000, 2160: 3000, 10488: 11000, 11488: 12000, 12488: 13000,
                    11016: 21000, 12016: 22000, 13016: 23000}
        r.q.side_effect = lambda a: pointers.get(a, a)
        classes = {2000: 'BattleCharacterDataManager', 3000: 'List`1',
                   10000: 'BattlePlayerData', 11000: 'BattlePlayerData', 12000: 'BattlePlayerData'}
        r.cls.side_effect = lambda a: classes.get(a)
        r.fields.return_value = dict(fields=[dict(name='<playerDataList>k__BackingField', offset=160)])
        positions = {10036: 2, 11036: 0, 12036: 1}
        r.i.side_effect = lambda a: positions.get(a)
        r.string.side_effect = lambda a: '角色' + str(a)
        return FormationReader(r, 1000), positions

    def test_rereads_positions_and_rejects_duplicate_slots(self):
        reader, positions = self.setup_reader()
        with patch('hbr_live_app.source.members', return_value=[10000, 11000, 12000]):
            first = reader.sample()
            self.assertEqual([p['actor_id'] for p in first], [11000, 12000, 10000])
            positions[10036], positions[11036] = 0, 2
            second = reader.sample()
            self.assertEqual([p['actor_id'] for p in second], [10000, 12000, 11000])
            self.assertEqual(first[0]['actor_id'], 11000)
            positions[12036] = 0
            with self.assertRaisesRegex(RuntimeError, '重复'):
                reader.sample()
