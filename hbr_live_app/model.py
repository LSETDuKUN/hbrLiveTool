"""Actual resources never come from subtracting display damage totals."""
from collections import OrderedDict


class BattleModel:
    def __init__(self):
        self.actions = OrderedDict()
        self.planned_actions = OrderedDict()
        self.enemies = OrderedDict()
        self.run_id = None
        self.turn_context = None
        self.players = []
        self.element_gauge = None
        self.field_state = None
        self.od_state = None
        self.od_markers=[]
        self.od_active=False
        self.execution_revision=0
        self.executions=set()

    def update(self, packet):
        context=packet.get('turn_context') or {}
        keys=set()
        visit=context.get('command_visit',context.get('command_count'))
        if visit and context.get('selecting') is False:keys.add((context.get('turn'),visit))
        for event in packet.get('events',[]):
            group=event.get('command') or {}
            if not event.get('instant') and group.get('id') is not None:
                keys.add((group.get('turn'),group['id']))
        fresh=keys-self.executions
        if fresh:self.execution_revision+=1;self.executions.update(fresh)
        od=packet.get('od_state') or {}
        active=od.get('active') if od.get('available') else context.get('od')
        if active and not self.od_active:
            def anchor(events, incoming):
                new={e['event_id'] for e in incoming if e['event_id'] not in events and e.get('command') and not e['command'].get('od')}
                return len(events)+len(new)
            actual=list(packet.get('events',[]))
            planned=[e for e in actual if e.get('instant')]+list(packet.get('planned_events',[]))
            turn=context.get('turn')
            prior=any(g.get('turn')==turn and not g.get('od') and g.get('kind')!='instant'
                      for e in [*self.actions.values(),*actual,*self.planned_actions.values(),*planned] if (g:=e.get('command')))
            self.od_markers.append(dict(turn=turn,level=od.get('level') or context.get('od_level') or context.get('bonus_max'),
                timing='后置' if prior or context.get('od_before_enemy') else '前置' if context.get('od_before_enemy') is not None else '时点未知',
                actual=anchor(self.actions,actual),planned=anchor(self.planned_actions,planned)))
        if active is not None:self.od_active=active
        if active and self.od_markers and not self.od_markers[-1]['level']:
            self.od_markers[-1]['level']=od.get('level') or context.get('bonus_max')
        if 'od_state' in packet:self.od_state=packet['od_state']
        if 'field_state' in packet:
            self.field_state = packet['field_state']
        if 'element_gauge' in packet:
            self.element_gauge = packet['element_gauge']
        if 'player_states' in packet:
            self.players = packet['player_states']
        if 'turn_context' in packet:
            self.turn_context = packet['turn_context']
        present = {s['address'] for s in packet['enemies']}
        for key, old in self.enemies.items():
            old['active'] = key in present
        for state in packet['enemies']:
            key = state['address']
            old = self.enemies.get(key)
            data = dict(state, active=True)
            for pool in ('dp', 'hp'):
                value = state[pool]
                data[pool + '_reference'] = max(value, old[pool + '_reference'] if old else value)
                data[pool + '_change'] = value - old[pool] if old else 0
                data[pool + '_rises'] = (old[pool + '_rises'] if old else 0) + int(old is not None and value > old[pool])
            self.enemies[key] = data
        for event in packet.get('events', []):
            self.actions[event['event_id']] = event
            if event.get('instant'):
                self.planned_actions[event['event_id']] = event
        for event in packet.get('planned_events', []):
            self.planned_actions[event['event_id']] = event

    @property
    def total(self):
        return sum(e['value'] for e in self.actions.values())

    @property
    def command_damage(self):
        totals = OrderedDict()
        for event in self.actions.values():
            group = event.get('command')
            key = event.get('damage_group_id')
            if key is None:
                key = group['id'] if group else f'unknown:{event["event_id"]}'
            totals[key] = totals.get(key, 0) + event['value']
        current = next(reversed(totals), None)
        return dict(current_id=current, current=totals.get(current, 0), maximum=max(totals.values(), default=0))

    def export(self):
        return {'schema': 2, 'run_id': self.run_id, 'display_damage': self.total,
                'command_damage': self.command_damage,
                'turn_context': self.turn_context,
                'player_states': self.players,
                'element_gauge': self.element_gauge,
                'field_state': self.field_state,
                'od_state': self.od_state, 'od_markers':list(self.od_markers),
                'planned_actions': list(self.planned_actions.values()),
                'enemies': list(self.enemies.values()), 'actions': list(self.actions.values())}
