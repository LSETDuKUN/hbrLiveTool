import json
from pathlib import Path
import unittest
from hbr_live_app.enemy_preview import EnemyPreview


class PreviewLifecycle(unittest.TestCase):
    def setUp(self):
        data = json.loads((Path(__file__).parent/'fixtures/amon_rules.json').read_text(encoding='utf-8'))
        self.info = dict(patterns=data['pattern'], extra_patterns=data['extra_gauge']['pattern'],
                         skills={s['id']: s for s in data['skills']})
        self.live = dict(dp=1600000, dp_pattern=data['pattern']['dp']['l'],
                         hp_pattern=data['pattern']['hp']['l'], dp_extra=True, dp_index=0,
                         dp_active_pattern=data['pattern']['dp']['l'], dp_order=0, hp_order=0,
                         overridden=False, down=0)
        self.tracker = EnemyPreview()

    def preview(self, selecting=False, **changes):
        self.live.update(changes)
        return self.tracker.update(1, self.info, self.live, dict(selecting=selecting, turn=1))

    def test_player_animation_keeps_preview_and_break_updates_it(self):
        first = self.preview(True)
        active = self.preview()
        self.assertEqual(first['branches'], active['branches'])
        broken = self.preview(dp_index=1, dp_active_pattern='BigotryGateAmonDefaultHard_DP2', dp=1200000)
        self.assertEqual(broken['branches'][0]['skills'], ['Planar Collapse'])

    def test_queue_progress_and_double_action_do_not_skip_current_batch(self):
        first = self.preview(True)
        queued = self.preview(enemy_pending=True, dp_order=1)
        self.assertEqual(queued['branches'], first['branches'])
        executing = self.preview(enemy_executing=True)
        gap = self.preview(enemy_executing=False)
        second = self.preview(enemy_executing=True)
        for result in (executing, gap, second):
            self.assertEqual(result['branches'], first['branches'])
            self.assertTrue(result['executing'])
        after = self.preview(enemy_pending=False, enemy_executing=False)
        self.assertEqual(after['order'], 2)

    def test_enemies_have_independent_latches(self):
        first = self.preview(True)
        self.preview(enemy_pending=True, enemy_executing=True, dp_order=1)
        other = self.tracker.update(2, self.info, dict(self.live, enemy_pending=False, enemy_executing=False),
                                    dict(selecting=False, turn=1))
        self.assertEqual(other['order'], 2)
        self.assertEqual(self.preview()['order'], first['order'])
