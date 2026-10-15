"""Per-enemy observed skill counts; missing history remains explicitly unknown."""
import time


class EnemyObservations:
    def __init__(self):
        self.enemies = {}
        self.seen = set()
        self.last_time = None
        self.count = None
        self.active_actors = set()
        self.executing_actors = set()

    def invalidate(self):
        for data in self.enemies.values():
            data['complete'] = False
            data['uncertain'] = True

    def update(self, states, actions, now=None):
        now = time.monotonic() if now is None else now
        if self.last_time is not None and now-self.last_time > 0.6:
            self.invalidate()
        self.last_time = now
        self.count = sum(s['hp'] > 0 for s in states)
        for state in states:
            old = self.enemies.setdefault(state['address'], dict(counts={}, complete=False,
                uncertain=False, initialized=False, dp=state['dp'], recent_break=False, last_actions=[]))
            old['recent_break'] = old['dp'] > 0 and state['dp'] <= 0 or (old['recent_break'] and state['dp'] <= 0)
            old['dp'] = state['dp']
        present = set()
        actors = {a['actor'] for a in actions if not a.get('actor_is_player', True) and a['actor'] in self.enemies}
        for actor in actors-self.active_actors:
            self.enemies[actor]['last_actions'] = []
        for action in actions:
            actor = action['actor']
            if actor not in self.enemies or action.get('actor_is_player', True):
                continue
            identity = (actor, action['address'], action.get('hit_set'), action['skill'])
            present.add(identity)
            if action.get('executing') and identity not in self.seen:
                counts = self.enemies[actor]['counts']
                counts[action['skill']] = counts.get(action['skill'], 0)+1
                self.enemies[actor]['last_actions'].append(action['skill'])
                self.seen.add(identity)
        self.seen.intersection_update(present)
        self.active_actors = actors
        self.executing_actors = {a['actor'] for a in actions if a.get('executing') and a['actor'] in actors}

    def state(self, address, live, context):
        old = self.enemies.get(address)
        if not old:
            return dict(enemy_count=self.count)
        if not old['initialized']:
            old['initialized'] = True
            old['complete'] = bool(not old['uncertain'] and context and context.get('selecting')
                and context.get('turn') == 1 and live['dp_order'] == 0 and live['hp_order'] == 0)
        # Partial observations are lower bounds, not exact counts; do not use them
        # to prove equality or that a skill has never been used.
        return dict(enemy_count=self.count, played_counts=dict(old['counts']) if old['complete'] else {},
                    enemy_pending=address in self.active_actors, enemy_executing=address in self.executing_actors,
                    observed_played_counts=dict(old['counts']), played_complete=old['complete'],
                    played_source='observed', recent_break=old['recent_break'], last_actions=list(old['last_actions']))
