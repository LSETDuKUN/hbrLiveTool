import json
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from hbr_live_app import theme
from hbr_live_app.components import Field, Fold, FormGrid, ResultStat, RoundedCard, Section
from hbr_live_app.damage_autofill import autofill
from hbr_live_app.team_store import STATS, TeamStore
from hbr_live_core.http_api import LocalApi, create_server
from test_damage_autofill import setup

ROOT = Path(__file__).resolve().parent.parent


def six_players():
    return [
        dict(
            style_label=f'Style{i}',
            actor=f'角色{i}',
            style_name=f'风格{i}',
            actor_position=i,
            dp=1000,
            dp_max=1000,
            hp=3000,
            hp_max=3000,
            combat_inputs=dict(
                stats=dict.fromkeys(STATS, 450),
                equipped_skills=[dict(label='test', name='测试攻击', level=7)],
                passive_audit=[
                    dict(
                        label='Passive.Start_ThunderEnhanceRing04',
                        name='雷之戒',
                        classification='饰品',
                        timing='常驻',
                        condition='',
                        description='雷属性技能攻击力提升',
                        parts=[],
                        catalog_found=True,
                    )
                ],
            ),
        )
        for i in range(6)
    ]


class WebUiServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = TeamStore(Path(self.tmp.name) / 'teams.sqlite3')
        self.store.observe('run-1', six_players(), dict(turn=1))

        p, e, self.lookup = setup()
        self.fill_fn = lambda pl, en, f=None, **kw: autofill(pl, en, f, lookup=self.lookup, **kw)
        self.live_snap = dict(
            connected=True,
            run_id='live-web',
            execution_revision=0,
            turn_context=dict(selecting=True, turn=1),
            players=[dict(p, actor='咲', name='咲', actor_position=0)],
            enemies=[dict(e, name='Boss', hp=80000, dp=4000)],
            field_state=dict(available=True, statuses=[]),
            element_gauge=dict(full=False),
            od_state=dict(available=True, active=False, level=0),
        )
        self.api = LocalApi(
            snapshot_provider=lambda: self.live_snap,
            team_store=self.store,
            autofill_fn=self.fill_fn,
            catalog_lookup=self.lookup,
        )

    def _get(self, path):
        return self.api.handle_http('GET', path)

    def _post(self, path, payload):
        status, _, raw = self.api.handle_http('POST', path, json.dumps(payload).encode('utf-8'))
        return status, json.loads(raw.decode('utf-8'))

    def test_serves_static_web_workbench_assets(self):
        status, ctype, html = self._get('/')
        self.assertEqual(status, 200)
        self.assertIn('text/html', ctype)
        text = html.decode('utf-8')
        self.assertIn('伤害试算（三栏）', text)
        self.assertIn('配队档案', text)
        self.assertIn('星屑资料室', text)

        status, ctype, css = self._get('/style.css')
        self.assertEqual(status, 200)
        self.assertIn('text/css', ctype)
        self.assertIn('.three-col-grid', css.decode('utf-8'))

        status, ctype, js = self._get('/app.js')
        self.assertEqual(status, 200)
        self.assertIn('javascript', ctype)
        self.assertIn('MULTIPLIER_GROUPS', js.decode('utf-8'))

    def test_teams_archive_and_offline_calculator_flow_over_http(self):
        # 1. List drafts and save as a named team.
        _, _, raw = self._get('/teams')
        data = json.loads(raw.decode('utf-8'))
        self.assertEqual(len(data['drafts']), 1)
        self.assertEqual(len(data['teams']), 0)
        self.assertEqual(
            data['drafts'][0]['payload']['members'][0]['passives_enriched'][0]['slot'],
            '戒指',
        )

        status, saved = self._post('/teams/save', dict(run_id='run-1', name='雷队主力'))
        self.assertEqual(status, 200)
        self.assertEqual(len(saved['teams']), 1)
        self.assertEqual(len(saved['drafts']), 0)
        team_key = saved['teams'][0]['key']

        # 2. Query skill detail endpoint.
        _, _, sk_raw = self._get('/skills/detail?label=test')
        sk = json.loads(sk_raw.decode('utf-8'))
        self.assertTrue(sk['found'])
        self.assertEqual(sk['detail']['effects'][0]['kind'], 'AttackSkill')

        # 3. Create a manual status via /offline/status and activate an offline plan from team_key.
        status, st = self._post('/offline/status', dict(kind='AttackUp', value=50, target='all'))
        self.assertEqual(status, 200)
        self.assertTrue(st['ok'])

        status, plan_res = self._post(
            '/offline/plan',
            dict(
                team_key=team_key,
                title='雷队主力试算',
                enemy=dict(
                    name='测试首领',
                    dp=2000,
                    hp=50000,
                    defense=150,
                    damage_rate=160,
                    destruction_coefficient=4,
                    destruction_max=300,
                    rates=dict(Thunder=200, Stab=150),
                ),
                field=dict(element='Thunder', bonus=50),
                od_level=1,
                manual_statuses=[dict(target='all', status=st['status'])],
                activate=True,
            ),
        )
        self.assertEqual(status, 200)
        self.assertTrue(plan_res['ok'])

        # 4. Prepare and compute over HTTP.
        with patch('hbr_live_app.damage_autofill.catalog_skill', side_effect=self.lookup):
            status, prep = self._post(
                '/damage/prepare',
                dict(actor_id='offline-0', enemy_address='offline-enemy'),
            )
            self.assertEqual(status, 200)
            self.assertTrue(prep['ok'])

            status, comp = self._post(
                '/damage/compute',
                dict(
                    overrides=dict(
                        hit_weights='0.5, 0.5',
                        main_hits='2',
                        skill_dr='10',
                    )
                ),
            )
            self.assertEqual(status, 200)
            self.assertTrue(comp['ok'])
            self.assertGreater(comp['damage'], 0)
            self.assertIsNotNone(comp['plot_data'])

            # 5. Switch back to live mode.
            status, mode_res = self._post('/mode', dict(mode='live'))
            self.assertEqual(status, 200)
            self.assertEqual(mode_res['mode'], 'live')
            self.assertEqual(mode_res['snapshot']['run_id'], 'live-web')


class DesignSystemAndGalleryTest(unittest.TestCase):
    def test_design_tokens_and_components(self):
        self.assertEqual(theme.SPACING, (4, 8, 12, 16, 24))
        self.assertEqual(theme.SEMANTIC_DAMAGE, theme.PINK)
        self.assertEqual(theme.SEMANTIC_BUFF, theme.CYAN)
        self.assertEqual(theme.SEMANTIC_DEBUFF, theme.ROSE)
        self.assertEqual(theme.SEMANTIC_DESTRUCTION, theme.GOLD)

        root = tk.Tk()
        root.withdraw()
        try:
            sec = Section(root, '章节', hint='说明', collapsible=True)
            sec.pack(fill='x')
            self.assertTrue(sec.opened.get())
            sec.toggle()
            self.assertFalse(sec.opened.get())
            sec.toggle()

            grid = FormGrid(sec.body, [('attack', '普通加攻', '%'), ('fragile', '脆弱', '%')], columns=2)
            grid.pack(fill='x')
            grid.fields['attack'].set('120')
            self.assertEqual(grid.fields['attack'].get(), '120')
            grid.set_errors({'fragile': '字段错误提示'})
            self.assertEqual(grid.fields['fragile'].error_label.cget('text'), '字段错误提示')
            grid.set_errors({})
            self.assertEqual(grid.fields['fragile'].error_label.cget('text'), '')

            fold = Fold(root, '折叠区', prominent=True, opened=False)
            fold.pack(fill='x')
            self.assertFalse(fold.opened.get())
            fold.toggle()
            self.assertTrue(fold.opened.get())

            stat = ResultStat(root, '平均伤害', value='100,000', caption='90% 区间')
            stat.pack(fill='x')
            stat.set_stat('250,000', caption='更新后区间')
            self.assertEqual(stat.value_label.cget('text'), '250,000')

            # Redraw signature cache skips redundant _layout repaints when dimensions are unchanged.
            card = RoundedCard(root)
            card.pack(fill='x')
            root.update_idletasks()
            card._layout()
            with patch.object(card, 'draw') as draw_mock:
                card._layout()
                draw_mock.assert_not_called()
        finally:
            import gc
            for child in list(root.winfo_children()):
                child.destroy()
            gc.collect()
            root.update_idletasks()
            root.destroy()
            gc.collect()

    def test_gallery_cli_renders_all_palettes_and_scales(self):
        proc = subprocess.run(
            [sys.executable, '-B', '-m', 'hbr_live_app.gallery', '--check'],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(proc.returncode, 0)


if __name__ == '__main__':
    unittest.main()
