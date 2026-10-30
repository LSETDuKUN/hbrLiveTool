import json
import unittest
from pathlib import Path
from hbr_live_app.enemy_info import forecast


class ExCrimsonTests(unittest.TestCase):
    def test_exact_ex_rules_resolve_logged_progress_and_two_action_branches(self):
        data=json.loads((Path(__file__).parent/'fixtures/ex_redcrimson_cn.json').read_text(encoding='utf-8'))
        self.assertEqual(data['id'],13425012)
        info=dict(patterns=data['pattern'],skills={s['id']:s for s in data['skills']},extra_patterns={})
        live=dict(dp=50000000,dp_pattern='Ex_RedCrimson',dp_order=2,hp_order=0,
            hp_pattern='',down=0,charged=False,overridden=False,dp_extra=False,hp_extra=False)
        context=dict(turn=3,selecting=True,od=False,additional=False,extra=False)
        result=forecast(info,live,context)
        self.assertEqual(result['order'],3)
        self.assertEqual(len(result['branches']),4)
        for branch in result['branches']:
            self.assertEqual(len(branch['skills']),2)
            self.assertEqual(branch['share'],.25)
        result=forecast(info,dict(live,dp_order=4),context)
        self.assertIn('受副作用影响无法行动',result['text'])
