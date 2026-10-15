import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from PIL import Image
from hbr_live_app.axis_export import save_axis


class AxisExportTests(unittest.TestCase):
    def test_portrait_exports_embed_images_and_align_actor_skill_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            avatar = Path(tmp)/'avatar.png'
            Image.new('RGBA', (56,56), '#00ff00').save(avatar)
            data = self.data()
            data['actions'][0].update(style_label='actor', actor_id=1,
                targets=[dict(address=2,is_player=True,name='目标',style_label='target')])
            with patch('hbr_live_app.axis_portraits.portrait_path', return_value=avatar):
                out = Path(tmp)/'axis.png'
                save_axis(data, out, portraits=True)
                with Image.open(out) as image:
                    green = [(x,y) for y in range(112,image.height) for x in range(220,680)
                             if image.getpixel((x,y)) == (0,255,0)]
                    self.assertEqual(len(green), 56*56*2)
                    self.assertEqual(max(y for x,y in green)-min(y for x,y in green),55)
                page = Path(tmp)/'axis.html'
                save_axis(data,page,portraits=True)
                text = page.read_text(encoding='utf-8')
                self.assertEqual(text.count('data:image/png;base64,'),2)
                self.assertNotIn(str(avatar),text)
                self.assertIn('技能&lt;&amp;&gt;',text)

    def data(self):
        return dict(run_id='test', actions=[dict(event_id=1, actor='角色<&>', style_name='风格',
            actor_position=1, skill='技能<&>', value=12, hits=[], settled=True)])

    def test_html_escapes_names_keeps_details_and_screen_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'axis.html'
            save_axis(self.data(), path)
            text = path.read_text(encoding='utf-8')
            self.assertIn('技能&lt;&amp;&gt;', text)
            self.assertNotIn('角色<&>', text)
            self.assertIn('展开完整记录', text)
            self.assertLess(text.index('技能&lt;'), text.index('<td>/</td>'))

    def test_png_exports_even_if_panel_hidden_and_paginates_long_axes(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self.data()
            data['actions'] = [dict(data['actions'][0], event_id=n) for n in range(110)]
            paths = save_axis(data, Path(tmp)/'axis.png')
            self.assertGreater(len(paths), 1)
            for path in paths:
                with Image.open(path) as image:
                    self.assertEqual(image.width, 1600)
                    self.assertLessEqual(image.height, 7220)
