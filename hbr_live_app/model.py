"""Actual resources never come from subtracting display damage totals."""
from collections import OrderedDict


class BattleModel:
    def __init__(self):
        self.actions = OrderedDict()
        self.enemies = OrderedDict()
        self.run_id = None
        self.turn_context = None

    def update(self, packet):
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

    def export(self):
        return {'schema': 2, 'run_id': self.run_id, 'display_damage': self.total,
                'turn_context': self.turn_context,
                'enemies': list(self.enemies.values()), 'actions': list(self.actions.values())}
