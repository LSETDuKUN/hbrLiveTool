import unittest
from hbr_live_app.status_groups import group_statuses, effect_line


def status(kind,**kwargs):
    return dict(label='SpecialStatus.'+kind,name=kind,value='20%',**kwargs)


class StatusGroupTests(unittest.TestCase):
    def test_groups_keep_instances_durations_and_elements_separate(self):
        states=[status('AttackUp',element_type=0),status('AttackUp',element_type=3),
                status('MindEye'),status('Zone'),status('Funnel'),status('CriticalRateUp'),
                status('DefenseDown',duration='永久'),status('DefenseDown',duration='剩余计数 2'),status('Fragile'),
                status('ResistDown'),status('AttackDown')]
        groups,other=group_statuses(dict(statuses=states))
        self.assertEqual([len(groups[k]) for k in ('boost','funnel','critical','debuff','resist','negative')],[3,1,1,3,1,1])
        self.assertEqual(other,[states[3]])
        self.assertIn('雷属性',effect_line(states[1]))
        self.assertIn('永久',effect_line(states[6]))

    def test_unconfirmed_pending_and_hidden_are_collapsed(self):
        states=[status('Unknown'),status('AttackUp',pending_add=True),status('MindEye',hidden=True),
                status('AttackUp',effective=False)]
        groups,other=group_statuses(dict(statuses=states))
        self.assertFalse(any(groups.values()))
        self.assertEqual(other,states)
