"""Actual resources never come from subtracting display damage totals."""
from collections import OrderedDict


class BattleModel:
    def __init__(self):
        self.actions = OrderedDict()
        self.enemies = OrderedDict()
        self.run_id = None
        self.turn_context = None
        self.players = []
        self.element_gauge = None
        self.field_state = None
        self.od_state = None

    def update(self, packet):
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
                'od_state': self.od_state,
                'enemies': list(self.enemies.values()), 'actions': list(self.actions.values())}
