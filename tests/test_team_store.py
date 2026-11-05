import tempfile
import unittest
from pathlib import Path
from hbr_live_app.team_store import TeamStore, capture, STATS


def players():
    return [dict(style_label=f's{i}', actor=f'角色{i}', actor_position=i, dp=100, dp_max=100,
                 hp=50, hp_max=50, combat_inputs=dict(stats=dict.fromkeys(STATS, 400),
                 equipped_skills=[dict(label='skill',name='技能',level=7)], passive_audit=[])) for i in range(6)]


class TeamStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = TeamStore(Path(self.tmp.name)/'teams.sqlite3')

    def test_partial_and_initial_freeze(self):
        self.assertFalse(self.store.observe('run', players()[:3], {}))
        p = players()
        self.assertTrue(self.store.observe('run', p, dict(turn=1)))
        p[0]['dp']=1;p[0]['combat_inputs']['stats']['power']=999
        self.assertFalse(self.store.observe('run', p, {}))
        saved=self.store.rows(True)[0][2]['members'][0]
        self.assertEqual(saved['dp'],100)
        self.assertEqual(saved['stats']['power'],400)
        self.assertEqual(saved['skills'][0]['level'],7)
        self.store.delete('run',draft=True)
        self.assertFalse(self.store.observe('run', p, {}))
        self.assertFalse(self.store.rows(True))

    def test_same_roster_separate_builds_and_explicit_replace(self):
        for run in ('a','b'):
            self.store.observe(run,players(),{})
            self.store.save(run,run)
        self.assertEqual(len(self.store.rows()),2)
        target=self.store.rows()[0][0]
        p=players();p[0]['dp_max']=200
        self.store.observe('c',p,{})
        self.store.save('c','updated',target)
        self.assertEqual(len(self.store.rows()),2)
        self.assertFalse(self.store.rows(True))
        self.assertEqual(self.store.rows()[0][2]['members'][0]['dp_max'],200)
        reopened=TeamStore(self.store.path)
        self.assertEqual(len(reopened.rows()),2)

    def test_invalid_target_preserves_draft(self):
        self.store.observe('a',players(),{})
        with self.assertRaises(ValueError): self.store.save('a','new',999)
        self.assertEqual(len(self.store.rows(True)),1)

    def test_ui_draft_and_saved(self):
        import tkinter as tk
        from hbr_live_app.team_window import TeamWindow
        self.store.observe('a',players(),dict(turn=1))
        root=tk.Tk();root.withdraw()
        try:
            window=TeamWindow(root,self.store);root.update()
            self.assertEqual(len(window.pages),5)
            self.assertEqual(len(window.member_records),6)
            self.assertIn('角色0',window.caption.cget('text'))
            window.scope.set('角色 / 风格');window.search.set('角色2');root.update()
            self.assertEqual(len(window.member_records),1)
            self.assertIn('角色2',window.caption.cget('text'))
            window.search.set('不存在');root.update()
            self.assertFalse(window.member_records)
            self.assertFalse(window.selected())
            window.search.set('');root.update()
            window.name.delete(0,'end');window.name.insert(0,'队伍')
            window.save();root.update()
            self.assertEqual(self.store.rows()[0][1],'队伍')
            self.assertFalse(self.store.rows(True))
        finally: root.destroy()


class TeamViewTests(unittest.TestCase):
    def test_source_categories_keep_unknown_separate(self):
        from hbr_live_app.team_views import effect_group, equipment_slot, member_matches
        self.assertEqual(effect_group({'label':'Passive.Start_ThunderEnhanceRing04'}),'饰品效果')
        self.assertEqual(equipment_slot({'label':'Passive.Start_ThunderEnhanceRing04'}),'戒指')
        self.assertEqual(effect_group({'label':'Passive.SupportSkill_31C02'}),'共鸣被动')
        self.assertEqual(effect_group({'label':'Passive.Unknown'}),'天赋与其他被动')
        self.assertTrue(member_matches({'actor':'手冢 咲','style_label':'STezuka03'},'stezuka'))

    def test_character_search_across_teams(self):
        import tkinter as tk
        from hbr_live_app.team_window import TeamWindow
        with tempfile.TemporaryDirectory() as folder:
            store=TeamStore(Path(folder)/'teams.sqlite3')
            for run in ('alpha','beta'):
                store.observe(run,players(),{});store.save(run,run)
            root=tk.Tk();root.withdraw()
            try:
                w=TeamWindow(root,store)
                w.scope.set('角色 / 风格');w.search.set('角色1');root.update()
                self.assertEqual(len(w.records),2)
                self.assertEqual(len(w.member_records),2)
                w.scope.set('配队名');w.search.set('beta');root.update()
                self.assertEqual(len(w.records),1)
                self.assertEqual(len(w.member_records),6)
                child=list(w.member_records)[-1];w.tree.selection_set(child);root.update()
                self.assertEqual(w.selected()[2],'beta')
            finally:root.destroy()

class SkillDetailTests(unittest.TestCase):
    def test_team_skill_reference_excludes_shared_parts(self):
        from hbr_live_app.team_store import skill_references
        refs=skill_references(dict(selected_skill=dict(label='skill',name='同名',level=7,parts=[dict(Power=123)])))
        self.assertEqual(refs,[dict(label='skill',name='同名',level=7)])

    def test_bracelet_effects_have_own_slot(self):
        from hbr_live_app.team_views import effect_group,equipment_slot
        for label in ('Passive.Start_AttackUpOnlyNormalBracelet03','Passive.Start_AdditionalThunderOnlyNormalBracelet'):
            self.assertEqual(effect_group(dict(label=label)),'饰品效果')
            self.assertEqual(equipment_slot(dict(label=label)),'手环')

    def test_detail_renders_branches_and_missing_identity(self):
        import tkinter as tk
        from hbr_live_app.team_skill_details import show_skill
        raw=dict(label='skill',name='技能',desc='技能说明',sp_cost=13,hit_count=1,parts=[
            dict(skill_type='SkillCondition',cond='IsOverDrive()',strval=[
                dict(parts=[dict(skill_type='AttackSkill',power=[1,2])]),
                dict(parts=[dict(skill_type='AttackSkill',power=[3,4])])])])
        root=tk.Tk();root.withdraw()
        try:
            w=show_skill(root,dict(label='skill',name='技能',level=7),lookup=lambda label:raw)
            root.update()
            def texts(widget):
                result=[]
                for child in widget.winfo_children():
                    if 'text' in child.keys():result.append(str(child.cget('text')))
                    result.extend(texts(child))
                return result
            self.assertIn('OD 中',texts(w))
            self.assertIn('非 OD',texts(w))
            self.assertIn('档案技能等级  Lv.7',texts(w))
            w.destroy()
            w=show_skill(root,dict(label='unknown'),lookup=lambda label:{})
            root.update()
            self.assertIn('暂无可唯一匹配的技能资料',texts(w))
        finally:root.destroy()
