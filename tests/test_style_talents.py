import unittest
from hbr_data.talents import style_talents,expand_resonance


class TalentTests(unittest.TestCase):
    def test_resonance_lists_preserve_breakthrough_level(self):
        row=dict(group='共鸣天赋',tier=None,path='/resonance',data={'list':[
            dict(lb_lv=0,passive=dict(label='first',desc='one')),
            dict(lb_lv=4,passive=dict(label='last',desc='five'))]})
        result=expand_resonance([row])
        self.assertEqual([r['tier'] for r in result],[0,4])
        self.assertEqual([r['data']['desc'] for r in result],['one','five'])

    def test_unlock_tiers_and_resonance_remain_distinct(self):
        data=dict(passives=[dict(label='base')],roleabi=dict(label='role'),resonance='support',
                  limit_break=dict(bonus_per_level=[dict(step=1,bonus=[dict(label='one')]),dict(step=2,bonus=[]),
                                                   dict(step=3,bonus=[dict(label='three')])]))
        rows=style_talents(data)
        self.assertEqual([(r['data']['label'],r['tier']) for r in rows],
                         [('role',None),('base',0),('one',1),('three',3),('support',None)])
        self.assertEqual(len({r['path'] for r in rows}),5)
