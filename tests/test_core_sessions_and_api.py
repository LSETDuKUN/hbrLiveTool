import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hbr_live_app import offline_battle as ob
from hbr_live_app.damage_autofill import autofill
from hbr_live_app.team_store import TeamStore
from hbr_live_core import (
    LiveSession,
    LocalApi,
    OfflineSession,
    create_server,
    damage_service,
     sanitize_team_payload,
    schema,
)
from test_damage_autofill import setup

ROOT = Path(__file__).resolve().parent.parent


def sample_team_with_personal_context():
    return dict(
        schema=1,
        captured_at='2026-11-17T20:00:00',
        context=dict(
            turn=3,
            fsm_address='0x7ff000123456',
            state_address='0x7ff000654321',
            frontline=[dict(actor_id=192837465, actor='Saki', position=0)],
        ),
        members=[
            dict(
                style_label=f'Style{i}',
                actor=f'角色{i}',
                style_name=f'风格{i}',
                position=i,
                dp=1200,
                hp=3200,
                dp_max=1200,
                hp_max=3200,
                stats=dict(power=500, dexterity=480, toughness=450, spirit=460, wisdom=470, luck=440),
                skills=[
                    dict(label='test', name='测试攻击', level=8),
                    dict(label=f'Skill{i}B', name='辅助技能', level=3),
                ],
                skills_complete=True,
                passives=[dict(label='Passive.Start_AttackUp01', name='被动')],
            )
            for i in range(6)
        ],
    )


class OfflineSessionTest(unittest.TestCase):
    def test_sanitize_strips_personal_and_memory_fields(self):
        raw = sample_team_with_personal_context()
        clean = sanitize_team_payload(raw)
        self.assertNotIn('captured_at', clean)
        self.assertEqual(clean['context'], dict(turn=3))
        self.assertEqual(schema.validate(clean, 'TeamPayload'), [])

    def test_save_load_and_compute_roundtrip_is_identical(self):
        _, _, lookup = setup()
        fill_fn = lambda p, e, f=None, **kw: autofill(p, e, f, lookup=lookup, **kw)

        statuses = [
            (0, ob.manual_status('AttackUp', 60, serial=1)),
            (ob.ALL_MEMBERS, ob.manual_status('Funnel', 25, count=3, serial=2)),
            (ob.ENEMY, ob.manual_status('DefenseDown', 30, serial=3)),
            (ob.ENEMY, ob.manual_status('Fragile', 40, serial=4)),
        ]
        session = OfflineSession(
            sample_team_with_personal_context(),
            title='雷队试算方案',
            skill_choices={0: (0, None), 1: (1, None)},
            enemy=dict(
                name='阿蒙',
                dp=10000,
                hp=200000,
                damage_rate=180,
                destruction_coefficient=4,
                destruction_max=300,
                rates=dict(Thunder=250, Stab=150),
                down=1,
            ),
            enemy_stat=380,
            field=dict(element='Thunder', bonus=50),
            od_level=2,
            manual_statuses=statuses,
            selected_actor_index=0,
            mode_options=dict(transcend='启用', high_boost='自动', transcend_element='雷'),
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'plan.json'
            session.save(path)
            raw_text = path.read_text(encoding='utf-8')
            self.assertNotIn('0x7ff000123456', raw_text)
            self.assertNotIn('captured_at', raw_text)
            loaded = OfflineSession.load(path)

        snap1 = session.snapshot(lookup=lookup)
        snap2 = loaded.snapshot(lookup=lookup)
        self.assertEqual(schema.validate(snap1), [])
        self.assertEqual(schema.validate(snap2), [])

        with patch('hbr_live_app.damage_autofill.catalog_skill', side_effect=lookup):
            prep1 = damage_service.prepare(
                snap1, 'offline-0', ob.ENEMY_ADDRESS, options=session.mode_options, autofill_fn=fill_fn
            )
            prep2 = damage_service.prepare(
                snap2, 'offline-0', ob.ENEMY_ADDRESS, options=loaded.mode_options, autofill_fn=fill_fn
            )
        res1 = damage_service.compute(prep1, overrides=dict(hit_weights='1, 0.25, 0.25, 0.25', main_hits=1, skill_dr=10))
        res2 = damage_service.compute(prep2, overrides=dict(hit_weights='1, 0.25, 0.25, 0.25', main_hits=1, skill_dr=10))
        self.assertTrue(res1['ok'])
        self.assertEqual(res1['damage'], res2['damage'])
        self.assertEqual(res1['raw_damage'], res2['raw_damage'])
        self.assertEqual(res1['mean'], res2['mean'])
        self.assertEqual(res1['low'], res2['low'])
        self.assertEqual(res1['high'], res2['high'])
        self.assertEqual(res1['destruction_end'], res2['destruction_end'])
        self.assertEqual(res1['summary_text'], res2['summary_text'])

    def test_offline_damage_window_session_roundtrip(self):
        import tkinter as tk
        from hbr_live_app.offline_damage_window import OfflineDamageWindow

        with tempfile.TemporaryDirectory() as tmp:
            store = TeamStore(Path(tmp) / 'teams.sqlite3')
            root = tk.Tk()
            root.withdraw()
            try:
                w = OfflineDamageWindow(root, store)
                try:
                    plan = OfflineSession(
                        sample_team_with_personal_context(),
                        title='分享方案A',
                        enemy=dict(
                            name='首领',
                            dp=5000,
                            hp=80000,
                            damage_rate=150,
                            destruction_coefficient=3,
                            destruction_max=300,
                            rates=dict(Thunder=200),
                            down=1,
                        ),
                        enemy_stat=350,
                        field=dict(element='Thunder', bonus=65),
                        od_level=1,
                        manual_statuses=[(0, ob.manual_status('AttackUp', 50, serial=1))],
                    )
                    w.load_session(plan)
                    exported = w.build_session()
                    self.assertEqual(exported.enemy_stat, 350.0)
                    self.assertEqual(exported.enemy_config['name'], '首领')
                    self.assertEqual(exported.od_level, 1)
                    self.assertEqual(exported.field_config, dict(element='Thunder', bonus=65.0))
                    self.assertEqual(len(exported.manual_statuses), 1)
                finally:
                    w.destroy()
            finally:
                root.update_idletasks()
                root.destroy()


class LiveSessionTest(unittest.TestCase):
    def test_worker_lifecycle_and_immutable_snapshots(self):
        p, e, _ = setup()
        p.update(actor='Saki', style_label='STezuka03', actor_position=0)
        e.update(name='Enemy', hp=1000, dp=200)

        def fake_runner(stop, paused, emit, outdir):
            emit(('connected', dict(run_id='live-1', path=str(outdir / 'live-1.jsonl'))))
            emit(('snapshot', dict(
                enemies=[e],
                events=[],
                player_states=[p],
                turn_context=dict(selecting=True, turn=1),
                field_state=dict(available=True, statuses=[]),
                element_gauge=dict(full=False, value=0, maximum=100, element=3, name='雷'),
                od_state=dict(available=True, active=False, level=0),
            )))
            emit(('heartbeat', 1700000000.0))
            while not stop.is_set():
                stop.wait(0.01)
            emit(('stopped', None))

        with tempfile.TemporaryDirectory() as tmp:
            session = LiveSession(session_dir=Path(tmp), runner=fake_runner)
            self.assertTrue(session.start())
            # Wait briefly for fake worker to emit connected + snapshot.
            deadline = 50
            seen = []
            while deadline > 0 and not any(k == 'snapshot' for k, _ in seen):
                seen.extend(session.events())
                deadline -= 1
                if not any(k == 'snapshot' for k, _ in seen):
                    import time
                    time.sleep(0.01)
            self.assertTrue(session.connected)
            self.assertTrue(session.pause(True))
            self.assertFalse(session.pause(False))

            snap1 = session.latest_snapshot()
            self.assertEqual(schema.validate(snap1), [])
            # Mutating returned snapshot must never mutate session.model.
            snap1['players'][0]['actor'] = 'MUTATED'
            snap1['enemies'][0]['hp'] = 0
            snap2 = session.latest_snapshot()
            self.assertEqual(snap2['players'][0]['actor'], 'Saki')
            self.assertEqual(snap2['enemies'][0]['hp'], 1000)

            session.stop(wait=True)
            session.events()
            self.assertFalse(session.connected)

    def test_cli_replay_outputs_valid_snapshot_json_without_tk(self):
        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / 'sample.jsonl'
            p, e, _ = setup()
            p.update(actor='Saki', style_label='STezuka03', actor_position=0)
            e.update(name='Boss', hp=5000, dp=1000)
            lines = [
                json.dumps(dict(schema=2, run_id='cli-test', kind='start', time=1.0)),
                json.dumps(dict(
                    time=2.0,
                    enemies=[e],
                    events=[],
                    player_states=[p],
                    turn_context=dict(selecting=True, turn=1),
                    field_state=dict(available=True, statuses=[]),
                    element_gauge=dict(full=False),
                    od_state=dict(available=True, active=False, level=0),
                )),
                json.dumps(dict(kind='end', time=3.0, reason='battle_end')),
            ]
            jsonl.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            proc = subprocess.run(
                [sys.executable, '-B', '-m', 'hbr_live_core.live_session', '--replay', str(jsonl)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            )
            snap = json.loads(proc.stdout)
            self.assertEqual(schema.validate(snap), [])
            self.assertEqual(snap['run_id'], 'cli-test')
            self.assertEqual(snap['enemies'][0]['hp'], 5000)


class LocalHttpApiTest(unittest.TestCase):
    def test_rejects_non_loopback_host(self):
        api = LocalApi()
        with self.assertRaises(ValueError):
            create_server(api, host='0.0.0.0', port=0)

    def test_endpoints_drive_prepare_pending_compute_and_sequence(self):
        _, _, lookup = setup()
        fill_fn = lambda p, e, f=None, **kw: autofill(p, e, f, lookup=lookup, **kw)
        plan = OfflineSession(
            sample_team_with_personal_context(),
            title='API测试方案',
            enemy=dict(
                name='API敌人',
                dp=1000,
                hp=50000,
                damage_rate=150,
                destruction_coefficient=4,
                destruction_max=300,
                rates=dict(Thunder=200, Stab=150),
            ),
            enemy_stat=200,
        )
        api = LocalApi(autofill_fn=fill_fn)

        with patch('hbr_live_app.damage_autofill.catalog_skill', side_effect=lookup):
            code, out = api.handle('POST', '/offline/plan', plan.to_dict())
            self.assertEqual(code, 200)
            self.assertTrue(out['ok'])

            code, snap = api.handle('GET', '/snapshot')
            self.assertEqual(code, 200)
            self.assertEqual(schema.validate(snap), [])

            code, prep = api.handle(
                'POST',
                '/damage/prepare',
                dict(actor_id='offline-0', enemy_address=ob.ENEMY_ADDRESS),
            )
            self.assertEqual(code, 200)
            self.assertTrue(prep['ok'])
            json.dumps(prep)  # Must be JSON-serialisable

            code, res = api.handle(
                'POST',
                '/damage/compute',
                dict(hit_weights=[1.0], main_hits=1, skill_dr=10),
            )
            self.assertEqual(code, 200)
            self.assertTrue(res['ok'])
            json.dumps(res)

            code, seq = api.handle('POST', '/damage/sequence', dict(action='add'))
            self.assertEqual(code, 200)
            self.assertEqual(len(seq['steps']), 1)

            code, seq = api.handle('POST', '/damage/sequence', dict(action='clear'))
            self.assertEqual(code, 200)
            self.assertEqual(len(seq['steps']), 0)


if __name__ == '__main__':
    unittest.main()
