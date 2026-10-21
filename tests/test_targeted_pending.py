import unittest
from hbr_live_app.effect_pending import targeted_row,with_pending
from hbr_live_app.funnels import parse,describe
from hbr_live_app.effect_preview import proposals
from test_damage_autofill import setup


class TargetedTests(unittest.TestCase):
    def test_front_all_self_and_single_bind_to_id(self):
        party=[dict(actor_id=i,actor_position=i-1,statuses=[]) for i in range(1,7)]
        enemy=dict(address=90,statuses=[])
        for scope,expected in [('AllyFront',[1,2,3]),('AllyAll',[1,2,3,4,5,6]),('Self',[2]),('AllySingle',[4]),('AllyBack',[4,5,6])]:
            item=dict(title='加攻',caster=2,source='test',part=dict(skill_type='AttackUp',target_type=scope))
            row=targeted_row(item,20,party,[enemy],party[3],enemy)
            self.assertEqual(row['target_ids'],expected)
            for player in party:
                applied,_=with_pending(player,enemy,[row])
                self.assertEqual(bool(applied['statuses']),player['actor_id'] in expected)
                self.assertFalse(player['statuses'])

    def test_funnel_preview_preserves_bead_count_and_rate(self):
        p,e,_=setup()
        part=dict(skill_type='Funnel',target_type='AllyAll',label='beads',power=[3,0],value=[.25,0],
                  diff_for_max=0,parameters=dict(str=0,dex=0,con=0,spr=0,wis=0,luk=0),growth=[0,0],
                  effect=dict(limitType='Only',exitCond='PlayerTurnEnd'))
        items=proposals(p,e,lookup=lambda _:dict(label='beads',parts=[part]))
        self.assertEqual(items[0]['funnel_count'],3)
        self.assertEqual(items[0]['values']['minimum'],25)
        row=targeted_row(items[0],25,[p],[e],p,e)
        self.assertEqual(row['state']['values']['numValue'],3)
        self.assertEqual(row['state']['values']['rateValueInt'],2500)
        self.assertEqual(row['state']['buff_limit_type'],4)
        self.assertEqual(parse('3 × 25% + 2*10'),[.25]*3+[.1]*2)
        self.assertEqual(describe([.25]*3),'3 × 25%')
        with self.assertRaises(ValueError):parse('75%')

