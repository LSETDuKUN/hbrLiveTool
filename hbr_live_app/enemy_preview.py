"""Keep the current enemy action visible until its whole action batch ends."""
from copy import deepcopy
from .enemy_info import forecast


class EnemyPreview:
    def __init__(self):
        self.previous = {}
        self.executing = set()

    def update(self, address, info, live, context):
        old = self.previous.get(address)
        pending = live.get('enemy_pending', False)
        selecting = bool(context and context.get('selecting'))
        if selecting or not pending:
            self.executing.discard(address)
        elif live.get('enemy_executing'):
            self.executing.add(address)
        if address in self.executing and old and old.get('branches'):
            result = deepcopy(old)
            result['blink'] = False
            result['executing'] = True
            return result
        state = dict(live)
        # The game may advance the rule cursor when queuing, before animation.
        # Keep that batch's cursor while allowing shield/condition changes.
        if pending and not selecting and old and old.get('branches'):
            phase = old['phase']
            pattern = live.get(phase+'_active_pattern') or live.get(phase+'_pattern')
            if pattern == old.get('pattern'):
                state[phase+'_order'] = old['progress_order']
        result = forecast(info, state, context)
        self.previous[address] = deepcopy(result)
        return result
