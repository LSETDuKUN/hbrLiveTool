import unittest
import tempfile
from pathlib import Path
from hbr_live_app.history import skill_summary,summary_text
from hbr_live_app.axis_export import save_axis


class PlanSummaryTests(unittest.TestCase):
    def test_od_levels_colour_both_image_layouts(self):
        from PIL import Image,ImageColor
        from hbr_live_app import theme
        from hbr_live_app.overdrive import action_background,action_od_level
        self.assertIsNone(action_od_level(dict(od=False,bonus_max=3)))
        self.assertEqual(action_od_level(dict(od=True,od_level=2,bonus_max=3)),2)
        colours=[]
        with tempfile.TemporaryDirectory() as tmp:
            for level in (1,2,3):
                group=dict(id=1,turn=1,od=True,bonus=1,bonus_max=level)
                event=dict(event_id='a',actor='角色',actor_id=1,actor_position=0,skill='测试',command=group,value=0)
                colour=action_background(group,theme.CARD);colours.append(colour)
                for portraits in (False,True):
                    path=Path(tmp)/'axis.png'
                    save_axis(dict(actions=[event]),path,portraits)
                    with Image.open(path) as im:self.assertEqual(im.getpixel((2,130)),ImageColor.getrgb(colour))
                path=Path(tmp)/'axis.html';save_axis(dict(actions=[event]),path)
                self.assertIn('background:'+colour,path.read_text(encoding='utf-8'))
        self.assertEqual(len(set(colours)),3)
    def test_png_background_follows_each_theme_with_or_without_portraits(self):
        from PIL import Image,ImageColor
        from hbr_live_app import theme
        previous=theme.NAME
        try:
            with tempfile.TemporaryDirectory() as tmp:
                for palette in theme.PALETTES:
                    theme.use(palette)
                    for portraits in (True,False):
                        for mode in ('actual','planned'):
                            path=Path(tmp)/'axis.png'
                            save_axis(dict(actions=[],history_mode=mode),path,portraits)
                            with Image.open(path) as image:
                                self.assertEqual(image.getpixel((0,0)),ImageColor.getrgb(theme.BG))
        finally:theme.use(previous)

    def test_dedup_styles_unknown_and_instant(self):
        e=dict(actor_id=1,actor='咲',style_label='one',skill='铁锤',skill_label='hammer')
        events=[e,e,dict(e,instant=True,skill='鬼神化',skill_label='oni'),
            dict(e,style_label='two'),dict(e,skill='未知技能'),dict(e,skill_label='Passive.Pursuit_1')]
        summary=skill_summary(events)
        self.assertEqual(len(summary),2)
        self.assertEqual(len(summary[0]['skills']),2)
        self.assertNotIn('×',summary_text(summary[0]))
        self.assertEqual(summary[0]['unknown'],1)
        self.assertIn('鬼神化（小按钮）',summary_text(summary[0]))

    def test_export_only_planned_has_summary_and_escapes_text(self):
        e=dict(event_id='1',actor_id=1,actor='咲',actor_position=0,skill='<铁锤>',value=0,hits=[],targets=[],command=dict(id=1,turn=1))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'plan.html';data=dict(actions=[e],history_mode='planned')
            save_axis(data,path)
            text=path.read_text(encoding='utf-8')
            self.assertIn('计划技能汇总',text);self.assertIn('&lt;铁锤&gt;',text)
            from PIL import Image
            planned=Path(tmp)/'planned.png';actual=Path(tmp)/'actual.png'
            save_axis(data,planned,portraits=True)
            data['history_mode']='actual';save_axis(data,path)
            self.assertNotIn('计划技能汇总',path.read_text(encoding='utf-8'))
            save_axis(data,actual,portraits=True)
            with Image.open(planned) as p,Image.open(actual) as a:
                self.assertEqual(p.width,a.width)
                self.assertGreater(p.height,a.height)
