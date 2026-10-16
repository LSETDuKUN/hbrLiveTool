import unittest
from hbr_live_app.resistances import resistance_lines


class ResistanceTests(unittest.TestCase):
    def state(self):
        return dict(base_resistances={'thunder':-300,'fire':0},statuses_available=True,
                    statuses=[dict(label='SpecialStatus.ResistDown',element_key='Thunder',values=dict(rateValueInt=-5940))])

    def test_base_and_observed_delta_are_explicitly_reference_and_estimate(self):
        line=resistance_lines(self.state())[0]
        self.assertIn('300%（资料）',line)
        self.assertIn('59.4%',line)
        self.assertIn('359.4%（加成推算）',line)

    def test_multiple_instances_are_not_blindly_summed(self):
        s=self.state();s['statuses']*=2
        self.assertIn('暂不合算',resistance_lines(s)[0])

    def test_pending_effect_and_unavailable_sample_do_not_get_added(self):
        s=self.state();s['statuses'][0]['pending_add']=True
        self.assertNotIn('推算',resistance_lines(s)[0])
        s=self.state();s['statuses_available']=False
        self.assertNotIn('推算',resistance_lines(s)[0])
