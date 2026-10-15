"""Observe instant mode/style changes that never enter the action queue."""
import time


class PlayerTransitions:
    def __init__(self):
        self.previous = {}
        self.serial = 0
        self.layouts = {}
        self.last_time = None

    def invalidate(self):
        self.previous.clear()

    def sample(self, r, formation, names):
        states = []
        for player in formation.sample(all_players=True):
            address = player['actor_id']
            key = r.q(address)
            if key not in self.layouts:
                self.layouts[key] = {f['name']: f for f in r.fields(address)['fields']
                                     if f['declared'] == 'BattlePlayerData'}
            fields = self.layouts[key]
            state = dict(actor_id=address, actor_position=player['position'],
                         style_label=player['actor'], actor=names.actor(player['actor']),
                         style_name=names.style(player['actor']))
            for name, target, kind in [('_reinforcedModeUsedCount', 'mode_count', 8),
                                       ('_isAnotherCardForm', 'another_form', 2)]:
                field = fields.get(name)
                if field and field['type'] == kind:
                    if kind == 8:
                        value = r.i(address+field['offset'])
                        if value is not None and 0 <= value < 100000:
                            state[target] = value
                    else:
                        raw = r.read(address+field['offset'], 1)
                        if raw in (b'\0', b'\1'):
                            state[target] = raw == b'\1'
            states.append(state)
        return states

    def update(self, states, now=None):
        now = time.monotonic() if now is None else now
        if self.last_time is not None and now-self.last_time > 1:
            self.invalidate()
        self.last_time = now
        events = []
        for state in states:
            old = self.previous.get(state['actor_id'])
            if old:
                labels = []
                if state.get('mode_count', 0) > old.get('mode_count', state.get('mode_count', 0)):
                    labels.append('鬼神化' if state['style_label'] == 'STezuka03' else '强化模式启动')
                if old['style_label'] != state['style_label']:
                    labels.append('风格切换：'+(old['style_name'] or old['style_label'])+' → '+
                                  (state['style_name'] or state['style_label']))
                elif 'another_form' in old and 'another_form' in state and old['another_form'] != state['another_form']:
                    labels.append('形态切换：'+('另一形态' if state['another_form'] else '基础形态'))
                if labels:
                    self.serial += 1
                    events.append(dict(state, event_id=f'state:{self.serial}', skill=' / '.join(labels),
                        skill_label='Observed.PlayerTransition', instant=True, value=0, hits=[], targets=[],
                        settled=True, transition_before=dict(old), transition_after=dict(state)))
        self.previous = {s['actor_id']: dict(s) for s in states}
        return events
