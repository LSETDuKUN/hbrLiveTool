import unittest
from unittest.mock import patch
from hbr_live_app.effect_pending import skill_rows,with_pending
from hbr_live_app.orb_defaults import enabled

class PreviewSkillTests(unittest.TestCase):
    def test_explicit_orb_overrides_role(self):
        with patch('hbr_live_app.orb_defaults.style_record',return_value={'growth_abi':{'l':'AttackUp'}}):
            self.assertTrue(enabled(dict(role='Rider',style_label='nanami'),'damage'))
            self.assertFalse(enabled(dict(role='Debuffer'),'debuff','DefenseDown'))
        with patch('hbr_live_app.orb_defaults.style_record',return_value={'growth_abi':{'l':'BuffUp'}}):
            self.assertTrue(enabled({},'buff','AttackUp'))
            self.assertFalse(enabled({},'buff','MindEye'))
        with patch('hbr_live_app.orb_defaults.style_record',return_value={}):
            self.assertFalse(enabled(dict(role='Attacker'),'damage'))

    def test_party_buff_is_distributed_once_and_live_is_unchanged(self):
        player=dict(actor_id=1,role='Buffer',statuses=[],combat_inputs=dict(selected_skill=dict(label='buff',level=1)))
        other=dict(actor_id=2,statuses=[])
        enemy=dict(address=3,statuses=[])
        part=dict(label='buff1',skill_type='AttackUp',target_type='AllyAll',power=[.5,.5],diff_for_max=0,parameters=dict(str=0,dex=0,con=0,spr=0,wis=0,luk=0),growth=[0,0])
        lookup=lambda _:dict(label='buff',parts=[part])
        with patch('hbr_live_app.effect_preview.owned_audit',return_value=[]),patch('hbr_live_app.effect_passives.enhancements',return_value=(0,[])):
            rows,skipped=skill_rows(player,enemy,[player,other],[enemy],{},[],lookup)
            self.assertEqual(skipped,[])
            self.assertEqual(rows[0]['target_ids'],[1,2])
            self.assertEqual(skill_rows(player,enemy,[player,other],[enemy],{},rows,lookup)[0],[])
        virtual,_=with_pending(other,enemy,rows)
        self.assertEqual(len(virtual['statuses']),1)
        self.assertEqual(other['statuses'],[])

    def test_navigation_support_first_then_screen_left_to_right(self):
        from hbr_live_app.preview_order import ordered_frontline
        players=[dict(actor_position=p,combat_inputs=dict(selected_skill=dict(label=k))) for p,k in [(0,'hit'),(1,'hit'),(2,'buff'),(3,'buff')]]
        lookup=lambda k:dict(parts=[dict(skill_type='AttackSkill' if k=='hit' else 'AttackUp')])
        self.assertEqual(ordered_frontline(players,lookup),[2,1,0])

    def test_style_lookup_is_scoped_to_styles(self):
        from hbr_live_app.orb_defaults import style_record
        style_record.cache_clear()
        with patch('hbr_data.store.Catalog.query',return_value=([],[('{"growth_abi":{"l":"AttackUp"}}',)],False)) as query:
            self.assertTrue(enabled(dict(style_label='STezuka03'),'damage'))
            self.assertIn('FROM styles',query.call_args.args[0])
        style_record.cache_clear()

    def test_after_damage_effect_is_not_precast(self):
        from hbr_live_app.effect_math import EffectInputs
        from dataclasses import asdict
        player=dict(actor_id=1,combat_inputs=dict(selected_skill=dict(label='attack')))
        part=dict(label='late',skill_type='DefenseDown',target_type='All',hits=[dict(type='After')])
        item=dict(caster=1,source='attack',title='late debuff',part=part,values=asdict(EffectInputs(kind='fixed',minimum=30)))
        with patch('hbr_live_app.effect_preview.proposals',return_value=[item]):
            rows,skipped=skill_rows(player,dict(address=2),[player],[dict(address=2)],{},[],lookup=lambda _:dict(parts=[part]))
        self.assertFalse(rows)
        self.assertIn('伤害后',skipped[0])
