import tempfile
from pathlib import Path
import unittest
from PIL import Image
from hbr_live_app.axis_export import save_axis


class AxisExportTests(unittest.TestCase):
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
