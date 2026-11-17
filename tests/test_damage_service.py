import subprocess
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from hbr_live_app.damage_autofill import autofill
from hbr_live_app.damage_sequence import DamageSequence
from hbr_live_core import damage_service, schema
from test_damage_autofill import setup, status

ROOT = Path(__file__).resolve().parent.parent


def make_snapshot():
    p, e, lookup = setup()
    p.update(actor='A', name='A', actor_position=0)
    q = deepcopy(p)
    q.update(actor_id=2, actor='B', name='B', actor_position=1)
    r = deepcopy(p)
    r.update(actor_id=3, actor='C', name='C', actor_position=3)
    e.update(name='Boss', dp=2000, hp=50000)
    e['enemy_progress'].update(damage_rate=150, destruction_coefficient=4, destruction_max=300)
    snap = dict(
        schema_version=schema.SCHEMA_VERSION,
        connected=True,
        run_id='service-test',
        execution_revision=0,
        turn_context=dict(selecting=True, turn=1),
        players=[p, q, r],
        enemies=[e],
        field_state=dict(available=True, statuses=[]),
        element_gauge=dict(full=True, element=3, value=100, maximum=100, name='雷'),
        od_state=dict(available=True, active=True, level=2),
    )
    return snap, lookup


class DamageServiceTest(unittest.TestCase):
    def test_prepare_apply_pending_and_compute_chain_without_tk(self):
        snap, lookup = make_snapshot()
        fill_fn = lambda p, e, f=None, **kw: autofill(p, e, f, lookup=lookup, **kw)

        with patch('hbr_live_app.damage_autofill.catalog_skill', side_effect=lookup):
            prepared = damage_service.prepare(
                snap,
                actor_id=1,
                enemy_address=2,
                options=dict(transcend='auto', high_boost='auto', enemy_stat=120),
                autofill_fn=fill_fn,
            )
        self.assertTrue(prepared['ok'])
        self.assertEqual(prepared['enemy']['combat_inputs']['_defenseRefParam'], 120)
        self.assertEqual(prepared['values']['od'], '1.2')

        # Pre-add a front-line funnel buff and an enemy fragile debuff.
        funnel_item = dict(
            title='连击珠',
            caster=1,
            source='beads',
            funnel_count=3,
            part=dict(
                label='beads',
                skill_type='Funnel',
                target_type='AllyFront',
                effect=dict(limitType='Only', exitCond='PlayerTurnEnd'),
            ),
        )
        fragile_item = dict(
            title='脆弱',
            caster=1,
            source='frag',
            part=dict(
                label='frag',
                skill_type='Fragile',
                target_type='Single',
                effect=dict(exitCond='EnemyTurnEnd'),
            ),
        )
        prepared = damage_service.apply_pending(prepared, 'add', (funnel_item, 25), autofill_fn=fill_fn)
        self.assertEqual(float(prepared['values']['chain']), 75.0)
        self.assertEqual(prepared['chain_expression'], '3 × 25%')

        # Preserve manual edit on an unrelated multiplier when adding another pending effect.
        manual_values = dict(prepared['values'], attack='200')
        prepared = damage_service.apply_pending(
            prepared,
            'add',
            (fragile_item, 40),
            current_values=manual_values,
            autofill_fn=fill_fn,
        )
        self.assertEqual(float(prepared['values']['attack']), 200.0)
        self.assertEqual(float(prepared['values']['fragile']), 40.0)
        self.assertEqual(len(prepared['pending_lines']), 2)

        # Compute cross-pool damage with hit weights.
        res = damage_service.compute(
            prepared,
            overrides=dict(
                hit_weights=[1.0, 0.25, 0.25, 0.25],
                main_hits=1,
                skill_dr=10,
                damage_metric='applied',
            ),
        )
        self.assertTrue(res['ok'], res['errors'])
        self.assertEqual(schema.validate(res, 'CalcResult'), [])
        self.assertIsNotNone(res['damage'])
        self.assertIsNotNone(res['mean'])
        self.assertIsNotNone(res['low'])
        self.assertIsNotNone(res['high'])
        self.assertEqual(res['destruction_start'], 150.0)
        self.assertGreater(res['destruction_end'], 150.0)
        self.assertIn('平均实际扣除', res['summary_text'])

    def test_sequence_workflow_carries_enemy_state(self):
        snap, lookup = make_snapshot()
        fill_fn = lambda p, e, f=None, **kw: autofill(p, e, f, lookup=lookup, **kw)
        seq = DamageSequence()

        with patch('hbr_live_app.damage_autofill.catalog_skill', side_effect=lookup):
            prep1 = damage_service.prepare(snap, 1, 2, sequence=seq, autofill_fn=fill_fn)
            res1 = damage_service.compute(prep1, overrides=dict(hit_weights='1', main_hits=1, skill_dr=8))
            self.assertTrue(res1['ok'])
            step_out = damage_service.sequence_add(seq, prep1, res1)
            self.assertEqual(len(step_out['steps']), 1)

            # Next actor inherits remaining DP/HP and updated destruction rate.
            prep2 = damage_service.prepare(snap, 2, 2, sequence=seq, autofill_fn=fill_fn)
            self.assertTrue(prep2['ok'])
            self.assertEqual(float(prep2['params']['enemy_dp']), step_out['current']['dp'])
            self.assertAlmostEqual(float(prep2['values']['destruction']), step_out['current']['rate'])

            undo_out = damage_service.sequence_undo(seq)
            self.assertEqual(len(undo_out['steps']), 0)
            clear_out = damage_service.sequence_clear(seq)
            self.assertIsNone(clear_out['current'])

    def test_validation_returns_field_errors(self):
        res = damage_service.compute(None, overrides=dict(pool='auto', hit_weights=''))
        self.assertFalse(res['ok'])
        self.assertIn('enemy_dp', res['errors'])
        self.assertIn('hit_weights', res['errors'])

        res_bad_num = damage_service.compute(None, overrides=dict(pool='hp', attack='not-a-number'))
        self.assertFalse(res_bad_num['ok'])
        self.assertIn('attack', res_bad_num['errors'])

    def test_service_and_window_produce_identical_results(self):
        import tkinter as tk
        from hbr_live_app.damage_window import DamageWindow

        snap, lookup = make_snapshot()
        fill_fn = lambda p, e, f=None, **kw: autofill(p, e, f, lookup=lookup, **kw)

        with patch('hbr_live_app.damage_autofill.catalog_skill', side_effect=lookup):
            prep = damage_service.prepare(snap, 1, 2, autofill_fn=fill_fn)
            prep = damage_service.apply_pending(
                prep,
                'add',
                (
                    dict(
                        title='减防',
                        caster=1,
                        source='def',
                        part=dict(
                            label='def',
                            skill_type='DefenseDown',
                            target_type='Single',
                            effect=dict(exitCond='EnemyTurnEnd'),
                        ),
                    ),
                    30,
                ),
                autofill_fn=fill_fn,
            )
            svc_res = damage_service.compute(prep, overrides=dict(hit_weights='0.5, 0.5', main_hits=2, skill_dr=10))

        root = tk.Tk()
        root.withdraw()
        try:
            with patch('hbr_live_app.damage_window.autofill', side_effect=fill_fn), patch(
                'hbr_live_app.damage_autofill.catalog_skill', side_effect=lookup
            ):
                w = DamageWindow(root, lambda: snap)
                try:
                    w.update_pending(
                        'add',
                        (
                            dict(
                                title='减防',
                                caster=1,
                                source='def',
                                part=dict(
                                    label='def',
                                    skill_type='DefenseDown',
                                    target_type='Single',
                                    effect=dict(exitCond='EnemyTurnEnd'),
                                ),
                            ),
                            30,
                        ),
                    )
                    w.hit_weights.set('0.5, 0.5')
                    w.params['main_hits'].set('2')
                    w.params['skill_dr'].set('10')
                    w.compute()
                    self.assertEqual(w.summary.cget('text'), svc_res['summary_text'])
                    self.assertEqual(w.prob_summary.cget('text'), svc_res['prob_summary'])
                    self.assertEqual(w.result.get('1.0', 'end').strip(), svc_res['detail_text'].strip())
                    self.assertEqual(
                        w.destruction_report.get('1.0', 'end').strip(),
                        svc_res['destruction_report'].strip(),
                    )
                    self.assertAlmostEqual(w.plot_data['mean'], svc_res['plot_data']['mean'])
                finally:
                    w.destroy()
        finally:
            root.update_idletasks()
            root.destroy()

    def test_damage_service_never_imports_tkinter(self):
        code = 'import sys, hbr_live_core.damage_service; print("tkinter" in sys.modules)'
        out = subprocess.run(
            [sys.executable, '-B', '-c', code],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        self.assertEqual(out, 'False')


if __name__ == '__main__':
    unittest.main()
