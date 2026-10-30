import unittest
from hbr_live_app.planned_actions import PlannedActions
from hbr_live_app.model import BattleModel


class PlannedTests(unittest.TestCase):
    def test_execution_epoch_changes_once_per_real_command_not_buttons_or_updates(self):
        m=BattleModel();c=dict(turn=1,command_visit=1,selecting=True)
        m.update(dict(enemies=[],turn_context=c))
        self.assertEqual(m.execution_revision,0)
        m.update(dict(enemies=[],events=[dict(event_id='button',instant=True,value=0)]))
        self.assertEqual(m.execution_revision,0)
        m.update(dict(enemies=[],turn_context=dict(c,selecting=False)))
        m.update(dict(enemies=[],events=[dict(event_id='hit',value=10,command=dict(turn=1,id=1))]))
        self.assertEqual(m.execution_revision,1)
        m.update(dict(enemies=[],turn_context=dict(c,selecting=True,command_visit=2)))
        self.assertEqual(m.execution_revision,1)
        m.update(dict(enemies=[],turn_context=dict(c,selecting=False,command_visit=2)))
        self.assertEqual(m.execution_revision,2)
    def test_extra_only_records_eligible_actor(self):
        for ids in ([2],None):
            t=PlannedActions();c=dict(command_count=1,turn=1,selecting=True,additional=True,extra_actor_ids=ids)
            players=[dict(actor_id=i,actor_position=i-1,actor=str(i),combat_inputs={'selected_skill':{'name':'技能'}},
                          statuses=[dict(label='SpecialStatus.AdditionalTurn',duration_kind='count',remaining=1)] if i==2 else []) for i in (1,2,3)]
            t.update(c,players)
            self.assertEqual([e['actor_id'] for e in t.update(dict(c,selecting=False),[])],[2])

    def test_instant_actions_are_shared_but_damage_counted_once(self):
        m=BattleModel();event=dict(event_id='button',instant=True,value=25)
        m.update(dict(enemies=[],events=[event]));m.update(dict(enemies=[],events=[event]))
        self.assertEqual(m.total,25)
        self.assertEqual(list(m.planned_actions),['button'])

    def test_last_selection_is_frozen_even_without_actual_skill(self):
        t=PlannedActions()
        c=dict(command_count=1,command_visit=1,turn=1,selecting=True)
        p=dict(actor_id=10,actor='咲',actor_position=0,combat_inputs={'selected_skill':{'name':'铁锤','label':'hammer'}})
        self.assertEqual(t.update(c,[p]),[])
        p['combat_inputs']['selected_skill']['name']='三枪'
        t.update(c,[p])
        p['combat_inputs']['selected_skill']['name']='被清空'
        events=t.update(dict(c,selecting=False),[])
        self.assertEqual(events[0]['skill'],'三枪')
        self.assertEqual(t.update(dict(c,selecting=False),[]),[])
        m=BattleModel();m.update(dict(enemies=[],planned_events=events))
        self.assertEqual(m.total,0)
        self.assertEqual(m.export()['planned_actions'][0]['skill'],'三枪')
        self.assertFalse(m.actions)

    def test_disconnect_does_not_invent_intent(self):
        t=PlannedActions()
        c=dict(command_count=1,turn=1,selecting=True)
        p=dict(actor_id=10,actor_position=0,combat_inputs={'selected_skill':{'name':'铁锤'}})
        t.update(c,[p],now=0);t.update(None,[],now=.7)
        self.assertEqual(t.update(dict(c,selecting=False),[],now=.8),[])

    def test_final_auto_selection_survives_short_transition_gap(self):
        t=PlannedActions();c=dict(command_count=4,command_visit=4,turn=1,selecting=True,phase='オート')
        p=dict(actor_id=10,actor_position=0,combat_inputs={'selected_skill':{'name':'三枪狂袭'}})
        t.update(c,[p],now=0)
        t.update(None,[],now=.503)
        events=t.update(dict(c,selecting=False),[],now=.537)
        self.assertEqual([e['skill'] for e in events],['三枪狂袭'])
        self.assertEqual(t.update(dict(c,selecting=False),[],now=.55),[])

    def test_gap_does_not_cross_command_identity(self):
        t=PlannedActions();c=dict(command_count=1,turn=1,selecting=True)
        p=dict(actor_id=10,actor_position=0,combat_inputs={'selected_skill':{'name':'旧选择'}})
        t.update(c,[p],now=0);t.update(None,[],now=.1)
        self.assertEqual(t.update(dict(c,turn=2,selecting=False),[],now=.2),[])
