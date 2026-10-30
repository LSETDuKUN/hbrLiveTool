"""Command-selection visits identify batches; a batch freezes its turn context."""
import struct
import copy


class TurnReader:
    def __init__(self, r, module):
        self.r, self.module = r, module
        self.validated = None
        self.visit = 0
        self.last_selection = None
        self.was_selecting = False
        self.command_count = 0
        self._resolve()

    def _resolve(self):
        r = self.r
        info = r.q(self.module + 64)
        state = r.q(self.module + 16)
        sub = r.q(state + 168)
        fsm = r.q(sub + 48)
        current = r.q(fsm + 224)
        chain = (info, state, sub, fsm, current)
        if chain != self.validated:
            for address, name in zip(chain, ('BattleInfoManager', 'BattleState',
                                            'SubStateModule', 'ArborFSM', 'State')):
                if r.cls(address) != name:
                    raise RuntimeError('回合对象布局不匹配')
            self._check(info, {'<squadTurn>k__BackingField': (16, 8),
                '<extraTurn>k__BackingField': (28, 8), '<isExtraTurn>k__BackingField': (32, 2),
                '<maxOverDriveTurn>k__BackingField': (36, 8), '<overDriveTurn>k__BackingField': (40, 8),
                '<isOverDriveTurn>k__BackingField': (44, 2),
                '<isOverDriveBeforeEnemyTurn>k__BackingField': (45, 2),
                '<overDriveCount>k__BackingField': (48, 8), '<isAdditionalTurn>k__BackingField': (64, 2)})
            self._check(state, {'battleStateMachine': (168, 18)})
            self._check(sub, {'<instance>k__BackingField': (48, 18)})
            self._check(fsm, {'_CurrentState': (224, 18)})
            self._check(current, {'name': (80, 14), '<transitionCount>k__BackingField': (88, 9)})
            self.validated = chain
        return chain

    def _check(self, address, expected):
        actual = {f['name']: (f['offset'], f['type']) for f in self.r.fields(address)['fields']}
        if any(actual.get(name) != layout for name, layout in expected.items()):
            raise RuntimeError('回合字段布局不匹配')

    def sample(self):
        r = self.r
        chain = self._resolve()
        info, state, sub, fsm, current = chain
        before = r.read(current + 88, 4)
        raw = r.read(info + 16, 49)
        phase = r.string(r.q(current + 80))
        after = r.read(current + 88, 4)
        if len(before) != 4 or len(raw) != 49 or len(after) != 4 or phase is None:
            raise RuntimeError('回合字段读取中断')
        if before != after or chain != self._resolve():
            return None  # Transition in flight: do not invent a batch.
        number = lambda offset: struct.unpack_from('<i', raw, offset - 16)[0]
        flag = lambda offset: bool(raw[offset - 16])
        turn, bonus, maximum = number(16), number(40), number(36)
        if not 1 <= turn <= 100000 or not 0 <= bonus <= maximum <= 1000:
            raise RuntimeError('回合数值越界')
        # Auto uses its own command preparation node and skips manual selection.
        selecting = phase in ('コマンド選択', 'オート')
        phase_count = struct.unpack('<I', before)[0]
        if selecting:
            selection = (fsm, current, phase_count)
            if not self.was_selecting or selection != self.last_selection:
                self.visit += 1
            self.last_selection = selection
            self.command_count = phase_count
        self.was_selecting = selecting
        extra_actors=None
        if flag(64) or flag(32):
            try:
                from .source import members
                if not hasattr(self,'additional_field'):
                    fields={f['name']:f for f in r.fields(info)['fields']}
                    self.additional_field=fields.get('<additionalTurnCharacters>k__BackingField')
                field=self.additional_field
                if field and field['type']==21:
                    pointer=r.q(info+field['offset'])
                    if r.cls(pointer)=='List`1':
                        values=members(r,pointer)
                        if values and all(r.cls(p)=='BattlePlayerData' for p in values):extra_actors=values
            except (RuntimeError,ValueError,TypeError,KeyError):
                pass  # Optional membership must not disable the turn reader.
        return dict(command_count=self.command_count, command_visit=self.visit, turn=turn,
                    extra_actor_ids=extra_actors,
                    od=flag(44), bonus=bonus, bonus_max=maximum, od_activation=number(48),
                    od_before_enemy=flag(45), additional=flag(64), extra=flag(32),
                    extra_turn=number(28), selecting=selecting, phase=phase,
                    phase_count=phase_count, state_address=hex(current), fsm_address=hex(fsm))


class CommandLedger:
    def __init__(self):
        self.groups = {}
        self.events = {}
        self.pending = None
        self.last_context = None
        self.unresolved = {}
        self.pending_instants = {}
        self.damage_groups = {}

    @staticmethod
    def identity(context):
        if not context:
            return None
        return (context.get('command_visit', context['command_count']),
                context.get('fsm_address'), context['turn'])

    def update(self, events, context):
        if context and context['selecting']:
            self.pending = copy.deepcopy(context)
        events = list(events)
        if context:
            # Repair only a gap bracketed by the same batch, even when no new
            # hit event arrives after the missing sample. Never guess across turns.
            incoming = {e['event_id'] for e in events}
            for key, (saved, expected) in list(self.unresolved.items()):
                if expected is not None and expected == self.identity(context):
                    self.events.pop(key, None)
                    if key not in incoming:
                        events.append(saved)
                self.unresolved.pop(key)
        result = []
        for event in events:
            key = event['event_id']
            if key not in self.events:
                group = None
                if event.get('instant'):
                    group = {} if event.get('observed_before_connection') else copy.deepcopy(context or {})
                    group.update(id=f'instant:{key}', kind='instant')
                    if event.get('observed_before_connection'):group['observed_before_connection']=True
                    bucket = next(iter(self.pending_instants.values()))['damage_group_id'] if self.pending_instants else f'pending:{key}'
                    self.damage_groups[key] = bucket
                elif context and context.get('command_visit', context['command_count']) > 0:
                    count = context.get('command_visit', context['command_count'])
                    if count not in self.groups:
                        source = self.pending if self.pending and self.pending.get('command_visit', self.pending['command_count']) == count else context
                        group = copy.deepcopy({k: v for k, v in source.items() if k != 'selecting'})
                        if 'frontline' in context:
                            group['frontline'] = copy.deepcopy(context['frontline'])
                        group.update(id=count, sequence=len(self.groups) + 1)
                        self.groups[count] = group
                    group = self.groups[count]
                    for instant_key, saved in self.pending_instants.items():
                        self.damage_groups[instant_key] = group['id']
                        result.append(dict(saved, damage_group_id=group['id']))
                    self.pending_instants.clear()
                self.events[key] = group
                if context is None:
                    self.unresolved[key] = (copy.deepcopy(event), self.identity(self.last_context))
            elif key in self.unresolved:
                self.unresolved[key] = (copy.deepcopy(event), self.unresolved[key][1])
            # Final hits may arrive after Turn/OD has changed: never re-parent.
            record = dict(event, command=copy.deepcopy(self.events[key]) if self.events[key] else None)
            if key in self.damage_groups:
                record['damage_group_id'] = self.damage_groups[key]
            if event.get('instant') and isinstance(self.damage_groups.get(key), str) and self.damage_groups[key].startswith('pending:'):
                self.pending_instants[key] = copy.deepcopy(record)
            result.append(record)
        if context:
            self.last_context = copy.deepcopy(context)
        return result


def context_label(group):
    if not group:
        return '回合未识别'
    if group.get('observed_before_connection'):return '接入前 · 小按钮（时点未知）'
    parts = [f'Turn {group["turn"]}'] if group.get('turn') else ['回合未识别']
    if group.get('od'):
        from .overdrive import action_od_level
        level=action_od_level(group)
        if level:parts.append(f'OD {level}')
        parts.append(f'Bonus {group["bonus"]}')
    if group.get('additional') or group.get('extra'):
        parts.append('Extra')
    if group.get('kind') == 'instant':
        parts.append('小按钮')
    return ' / '.join(parts)
