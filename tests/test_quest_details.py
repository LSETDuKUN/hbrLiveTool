import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from hbr_data.assets import AssetStore, asset_urls, sync_portraits, asset_lock
from hbr_data.details import skill_detail
from hbr_data.cards import ratios, effect_category, group_effects, destruction_summary


class DetailTests(unittest.TestCase):
    def test_destruction_summary_preserves_separate_parts_and_unknowns(self):
        skill = skill_detail({"parts": [
            {"skill_type": "AttackSkill", "multipliers": {"dr": 13.8}},
            {"skill_type": "DefenseDown", "multipliers": {"dr": 99}},
            {"skill_type": "AttackSkill", "multipliers": {"dr": 0}},
            {"skill_type": "AttackSkill"}]})
        self.assertEqual(destruction_summary(skill.effects),
                         "效果 1：×13.8；效果 3：×0；效果 4：未提供")
        self.assertEqual(destruction_summary(skill.effects[:1]), "×13.8")
        self.assertEqual(destruction_summary(skill.effects[1:2]), "")

    def test_missing_hit_distribution_is_not_inferred(self):
        skill = skill_detail({"name":"X","hit_count":2,"parts":[{"power":[100,200],"parameters":{"str":2,"dex":1}}]})
        self.assertEqual(skill.hits,())
        self.assertEqual(skill.effects[0].hits,())
        self.assertIsNone(skill.effects[0].hp_multiplier)
        self.assertEqual(skill.effects[0].power,(100,200))

    def test_skill_and_effect_hit_distributions_stay_separate(self):
        value={"hit_count":2,"hits":[{"id":1,"type":"Main","power_ratio":.3},{"id":2,"type":"Main","power_ratio":.7}],
               "parts":[{"hits":[{"id":1,"type":"Before","power_ratio":0}],"multipliers":{"dr":1.5}}]}
        skill=skill_detail(value)
        self.assertEqual(ratios(skill.hits),'0.3 + 0.7')
        self.assertEqual(skill.effects[0].hits[0].kind,'Before')
        self.assertEqual(skill.effects[0].destruction_multiplier,1.5)
        self.assertEqual(value['hits'][0]['power_ratio'],.3)

    def test_mixed_skill_effects_group_without_losing_source_parts(self):
        parts = [
            {"skill_type":"AttackSkill","power":[100,200],"hits":[]},
            {"skill_type":"DefenseDown","power":[.2,.3],
             "hits":[{"id":1,"type":"Before","power_ratio":0}]},
            {"skill_type":"AttackUp","power":[.3,.4]},
            {"skill_type":"AdditionalTurn","power":[1,0]},
            {"skill_type":"UnfamiliarEffect","value":[7,0]},
        ]
        skill = skill_detail({"hit_count":3,"parts":parts})
        grouped = group_effects(skill.effects)
        self.assertEqual([(name,[effect.index for effect in effects]) for name,effects in grouped],
                         [("伤害",[0]),("增益",[2]),("减益",[1]),("其他",[3,4])])
        self.assertEqual([effect_category(effect) for effect in skill.effects],
                         ["伤害","减益","增益","其他","其他"])
        self.assertEqual(skill.effects[1].hits[0].ratio,0)
        self.assertEqual(skill.effects[4].raw,parts[4])
        self.assertEqual(skill.hits,())

    def test_portrait_paths_reject_traversal(self):
        for filename in ('../x.webp','a/b.webp','a\\b.webp',''):
            self.assertEqual(asset_urls('jp','styles',filename),[])
        self.assertIn('/en/hbr/',asset_urls('en','styles','x.webp')[1])

    def test_shared_portrait_downloads_once_and_has_lookup_api(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);image=Image.new('RGBA',(16,16),'pink');buffer=io.BytesIO();image.save(buffer,format='WEBP')
            rows=[('jp','styles','1','x.webp'),('jp','styles','2','x.webp')]
            with patch('hbr_data.assets.Catalog') as catalog,patch('hbr_data.assets.fetch',return_value=buffer.getvalue()) as fetch:
                catalog.return_value.query.return_value=([],rows,False)
                catalog.return_value.manifest.return_value={'database':'fixture'}
                sync_portraits(root,lambda _:None)
                self.assertEqual(fetch.call_count,1)
                a,b=(AssetStore(root).get('jp','styles',i) for i in ('1','2'))
                self.assertEqual(a['local_path'],b['local_path'])
                self.assertTrue(Path(a['local_path']).exists())
                self.assertEqual(a['status'],'ready')
                sync_portraits(root,lambda _:None)
                self.assertEqual(fetch.call_count,1)

    def test_bad_response_is_not_cached_as_an_image(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch('hbr_data.assets.Catalog') as catalog,patch('hbr_data.assets.fetch',return_value=b'<html>error</html>'):
                catalog.return_value.query.return_value=([],[('jp','enemies','1','enemy.webp')],False)
                catalog.return_value.manifest.return_value={'database':'fixture'}
                sync_portraits(temp,lambda _:None)
                result=AssetStore(temp).get('jp','enemies','1')
                self.assertEqual(result['status'],'error')
                self.assertIsNone(result['local_path'])

    def test_lock_releases_after_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,'test'):
                with asset_lock(Path(temp)):
                    raise ValueError('test')
            with asset_lock(Path(temp)):
                pass
