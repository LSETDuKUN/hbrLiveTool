import unittest
from unittest.mock import Mock,patch
from hbr_live_app import source


class ConnectionCacheTests(unittest.TestCase):
    def test_only_metadata_is_reused_and_process_restart_invalidates(self):
        r=Mock();r.process_identity=(1,0,123)
        r.q.side_effect=lambda a:{116:200,188:300,316:400}.get(a,0)
        r.name.side_effect=lambda a:{200:'BattleModule',400:'Object'}.get(a)
        r.scan.side_effect=[([200],None),([116],None),([200],None),([116],None)]
        with patch.object(source,'_class_cache',None):
            self.assertEqual(source.battle_classes(r),{100})
            self.assertEqual(source.battle_classes(r),{100})
            self.assertEqual(r.scan.call_count,2)
            r.process_identity=(1,0,456)
            self.assertEqual(source.battle_classes(r),{100})
            self.assertEqual(r.scan.call_count,4)

    def test_invalid_cached_metadata_is_not_trusted(self):
        r=Mock();r.process_identity=(1,2,3);r.q.return_value=0;r.name.return_value=None
        r.scan.return_value=([],None)
        with patch.object(source,'_class_cache',(r.process_identity,{100})):
            with self.assertRaises(RuntimeError):source.battle_classes(r)
        r.scan.assert_called_once_with(b'BattleModule\0')
