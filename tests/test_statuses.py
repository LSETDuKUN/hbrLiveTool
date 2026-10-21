import json
import struct
import unittest
from pathlib import Path
from unittest.mock import patch
from hbr_live_app.statuses import StatusReader, status_value, filter_confirmed_only_funnels
from hbr_live_app.model import BattleModel


class RecordedMemory:
    def __init__(self, data):
        self.objects = {int(o['address'],16):o for o in data['objects']}
        self.pointers = {}; self.memory = {}; self.strings = {}
        classes = {name:i+100 for i,name in enumerate(sorted({o['class'] for o in data['objects']}))}
        for address,o in self.objects.items():
            self.pointers[address] = classes[o['class']]
            for f in o['fields']:
                at = address+f['offset']
                if 'object' in f:
                    self.pointers[at] = int(f['object']['address'],16)
                elif 'text' in f:
                    self.pointers[at] = at+10**14
                    self.strings[at+10**14] = f['text']
                elif 'value' in f:
                    fmt = {2:'?',8:'i',9:'I',10:'q',11:'Q',12:'f',13:'d'}[f['type']]
                    self.memory[at] = struct.pack('<'+fmt,f['value'])
                elif 'raw4' in f:
                    self.memory[at] = bytes.fromhex(f['raw4'])
    def q(self,a):return self.pointers.get(a,0)
    def read(self,a,n):return self.memory.get(a,b'')[:n]
    def fields(self,a):return self.objects[a]
    def cls(self,a):return self.objects.get(a,{}).get('class')
    def string(self,a):return self.strings.get(a)
    def i(self,a):
        raw=self.read(a,4)
        return struct.unpack('<i',raw)[0] if len(raw)==4 else None


class StatusTests(unittest.TestCase):
    def test_recorded_charge_has_own_group_and_preserves_unknown_critical_scale(self):
        from hbr_live_app.status_groups import group_statuses
        folder = Path(__file__).parent/'fixtures'
        data = json.loads((folder/'owned_statuses.json').read_text(encoding='utf8'))
        trees = json.loads((folder/'charge_statuses.json').read_text(encoding='utf8'))
        data['objects'] += [o for tree in trees for o in tree.values()]
        reader = StatusReader(RecordedMemory(data))
        reader.skill_name = lambda label: label
        reader.source_effect = lambda label, kind: {}
        manager = reader.prop(int(data['roots'][0],16), 'specialStatusManager')
        with patch('hbr_live_app.source.members', return_value=[int(t['player']['address'],16) for t in trees]):
            reader.read_manager(manager)
        states = next(iter(reader.cache[manager].values()))
        charge = states[0]
        self.assertEqual(charge['name'], '充能 / 蓄力')
        self.assertIn('+39.18%', charge['value'])
        self.assertIn('暴击率提升（数值待核实）', charge['value'])
        self.assertEqual(charge['values']['rateValueInt'], 200000)
        self.assertEqual(charge['remaining'], 1)
        groups, other = group_statuses(dict(statuses=states))
        self.assertEqual(groups['charge'], states)
        self.assertFalse(other)
        self.assertFalse(groups['boost'] or groups['critical'])

    def test_recorded_element_field_and_weakness_values(self):
        folder=Path(__file__).parent/'fixtures'
        baseline=json.loads((folder/'owned_statuses.json').read_text(encoding='utf8'))
        trees=json.loads((folder/'thunder_field_resist.json').read_text(encoding='utf8'))
        baseline['objects'] += [o for tree in trees for o in tree.values()]
        for element,title in [('Fire','火'),('Ice','冰'),('Thunder','雷'),('Light','光'),('Dark','暗')]:
            reader=StatusReader(RecordedMemory(baseline));reader.skill_name=lambda label:label
            reader.source_effect=lambda label,kind:dict(elements=[element])
            manager=reader.prop(int(baseline['roots'][0],16),'specialStatusManager')
            with patch('hbr_live_app.source.members',return_value=[int(t['player']['address'],16) for t in trees]):
                reader.read_manager(manager)
            field=reader.cache[manager][0][0]
            self.assertEqual(field['name'],title+'属性场地')
            self.assertEqual(field['value'],'+95%（系数 1.95）')
            self.assertEqual(field['duration'],'永久')
            resist=next(s for ss in reader.cache[manager].values() for s in ss if s['label']=='SpecialStatus.ResistDown')
            self.assertEqual(resist['value'],'59.4%')

    def test_recorded_only_funnels_keep_one_without_combining_hits(self):
        folder=Path(__file__).parent/'fixtures'
        data=json.loads((folder/'owned_statuses.json').read_text(encoding='utf8'))
        funnels=json.loads((folder/'only_funnels.json').read_text(encoding='utf8'))
        data['objects'] += [o for tree in funnels for o in tree.values()]
        r=RecordedMemory(data);reader=StatusReader(r);reader.skill_name=lambda label:label
        manager=reader.prop(int(data['roots'][0],16),'specialStatusManager')
        with patch('hbr_live_app.source.members',return_value=[int(t['player']['address'],16) for t in funnels]):
            reader.read_manager(manager)
        items=next(iter(reader.cache[manager].values()))
        visible=[s for s in items if s.get('effective') is not False]
        self.assertEqual(len(visible),1)
        self.assertEqual(visible[0]['value'],'5 颗 × 12% / 颗')
        self.assertEqual(visible[0]['remaining'],2)
        self.assertEqual(len(items),2)

    def test_only_filter_preserves_permanent_and_unknown_competition(self):
        def funnel(kind,rate=1200,limit=4):
            return dict(label='SpecialStatus.Funnel',duration_kind=kind,buff_limit_type=limit,
                        values=dict(numValue=5,rateValueInt=rate))
        items=[funnel('turn'),funnel('permanent'),funnel('count'),funnel('turn',1300),funnel('turn',limit=0)]
        self.assertTrue(all(s.get('effective') is not False for s in filter_confirmed_only_funnels(items)))

    def test_ownerless_rice_field_is_global_and_never_assigned_to_players(self):
        folder=Path(__file__).parent/'fixtures'
        data=json.loads((folder/'owned_statuses.json').read_text(encoding='utf8'))
        rice=json.loads((folder/'rice_field.json').read_text(encoding='utf8'))
        data['objects'] += list(rice.values())
        r=RecordedMemory(data);reader=StatusReader(r);reader.skill_name=lambda label:label
        actor=int(data['roots'][0],16)
        manager=reader.prop(actor,'specialStatusManager')
        old_prop=reader.prop
        reader.prop=lambda obj,name,default=None:manager if obj==1 and name=='specialStatusManager' else old_prop(obj,name,default)
        with patch('hbr_live_app.source.members',return_value=[int(rice['player']['address'],16)]):
            self.assertEqual(reader.sample(actor)['statuses'],[])
            field=reader.sample_fields(1)
        self.assertTrue(field['available'])
        self.assertEqual(field['statuses'][0]['name'],'稻场')
        self.assertEqual(field['statuses'][0]['duration_kind'],'permanent')
        self.assertEqual(field['statuses'][0]['values']['rateValueInt'],15500)
        self.assertEqual(field['statuses'][0]['value'],'')

    def test_recorded_shared_manager_does_not_mix_ally_and_enemy(self):
        data=json.loads((Path(__file__).parent/'fixtures/owned_statuses.json').read_text(encoding='utf8'))
        r=RecordedMemory(data);reader=StatusReader(r)
        reader.skill_name=lambda label:label
        with patch('hbr_live_app.source.members',return_value=[int(a,16) for a in data['statuses']]):
            samples=[reader.sample(int(a,16)) for a in data['roots']]
        self.assertTrue(all(s['statuses_available'] for s in samples))
        self.assertEqual([s['label'] for s in samples[1]['statuses']],['SpecialStatus.MindEye'])
        self.assertEqual(samples[1]['statuses'][0]['value'],'+150.95%')
        self.assertEqual({s['label'] for s in samples[-1]['statuses']},{'SpecialStatus.Fragile','SpecialStatus.DefenseDown'})
        self.assertEqual({s['value'] for s in samples[-1]['statuses']},{'+33%','21.55%'})
        self.assertEqual(samples[0]['statuses'],[])
        self.assertEqual(samples[2]['statuses'],[])

    def test_unverified_fields_not_assumed_percent(self):
        self.assertEqual(status_value('Unknown',dict(rateValueInt=1000)),'')
        self.assertEqual(status_value('SpLimitOverwrite',dict(numValue=30)),'30')

    def test_current_roster_is_replaced_on_swap_and_unavailable(self):
        m=BattleModel()
        for players in ([dict(actor_id=1,actor_position=0)], [dict(actor_id=2,actor_position=0)], []):
            m.update(dict(enemies=[],player_states=players))
            self.assertEqual(m.export()['player_states'],players)
