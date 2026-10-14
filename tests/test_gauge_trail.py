import unittest
from hbr_live_app.gauge_trail import GaugeTrail


class GaugeTrailTests(unittest.TestCase):
    def test_large_drop_holds_then_catches_up_without_changing_value(self):
        trail = GaugeTrail()
        trail.update(1000, 1000, 0)
        trail.update(700, 1000, 0.1)
        self.assertEqual(trail.value, 700)
        self.assertEqual(trail.display(0.3), 1000)
        self.assertTrue(700 < trail.display(0.7) < 1000)
        self.assertEqual(trail.display(1.2), 700)
        self.assertFalse(trail.active(1.2))

    def test_small_hits_snap_but_fast_multihit_burst_accumulates(self):
        trail = GaugeTrail()
        trail.update(1000, 1000, 0)
        trail.update(950, 1000, 0.1)
        self.assertEqual(trail.display(0.1), 950)
        trail.update(900, 1000, 0.2)
        self.assertFalse(trail.active(0.2))
        trail.update(850, 1000, 0.3)
        self.assertTrue(trail.active(0.3))
        self.assertEqual(trail.display(0.3), 1000)

    def test_heal_reference_change_and_repeated_snapshots(self):
        trail = GaugeTrail()
        trail.update(1000, 1000, 0)
        trail.update(700, 1000, 0.1)
        until = trail.until
        trail.update(700, 1000, 0.2)
        self.assertEqual(trail.until, until)
        trail.update(800, 1000, 0.3)
        self.assertFalse(trail.active(0.3))
        self.assertEqual(trail.display(0.3), 800)
        trail.update(100, 2000, 0.4)
        self.assertEqual(trail.display(0.4), 100)

    def test_slow_small_hits_do_not_accumulate_forever(self):
        trail = GaugeTrail()
        trail.update(1000, 1000, 0)
        for t in range(1, 10):
            trail.update(1000-t*50, 1000, t)
            self.assertFalse(trail.active(t))
