"""Freeze command intent independently of observed hits and damage."""
import copy
import time
from .turns import CommandLedger


class PlannedActions:
    def __init__(self):
        self.pending=None
        self.seen=set()
        self.pending_time=None

    def update(self, context, players, now=None):
        now=time.monotonic() if now is None else now
        # A transition-in-flight sample has no context. Retain intent only
        # across a short gap bracketed by the exact same command identity.
        if self.pending_time is not None and now-self.pending_time>.6:
            self.pending=None
        if not context:
            return []
        identity=CommandLedger.identity(context)
        if context.get('selecting'):
            self.pending=(identity,copy.deepcopy(context),copy.deepcopy(players))
            self.pending_time=now
            return []
        if not self.pending or self.pending[0]!=identity or identity in self.seen:
            self.pending=None
            return []
        _,group,saved=self.pending
        self.pending=None
        self.seen.add(identity)
        group.update(id=context.get('command_visit',context['command_count']))
        result=[]
        for player in saved:
            position=player.get('actor_position')
            if position not in (0,1,2):continue
            if group.get('additional') or group.get('extra'):
                actors=group.get('extra_actor_ids')
                if actors is not None:
                    if player['actor_id'] not in actors:continue
                else:
                    from .status_rules import active
                    if not any(s.get('label')=='SpecialStatus.AdditionalTurn' and active(s)
                               for s in player.get('statuses',[])):continue
            skill=player.get('combat_inputs',{}).get('selected_skill') or {}
            result.append(dict(event_id=f'planned:{identity}:{player["actor_id"]}',
                actor_id=player['actor_id'],actor=player.get('actor','角色'),actor_position=position,
                style_label=player.get('style_label'),style_name=player.get('style_name'),
                skill=skill.get('name') or '预选未读到',skill_label=skill.get('label'),
                selected_skill=copy.deepcopy(skill),command=copy.deepcopy(group),
                planned=True,value=0,hits=[],targets=[],settled=True))
        return result
