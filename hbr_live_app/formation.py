"""Read current front-line positions, never infer them from execution order."""
class FormationReader:
    def __init__(self, r, module):
        self.r, self.module = r, module
        self.manager = None
        self.offset = None

    def sample(self, all_players=False):
        from .source import members
        r = self.r
        manager = r.q(self.module + 144)
        if r.cls(manager) != 'BattleCharacterDataManager':
            raise RuntimeError('角色管理对象不可读')
        if manager != self.manager:
            candidates = []
            fields = r.fields(manager)['fields']
            # The full roster coexists with front/sub lists. Prefer its exact
            # validated field instead of treating all three as ambiguous.
            full = [f for f in fields if f['name'] == '<playerList>k__BackingField' and f.get('type') == 21]
            for field in full or fields:
                name = field['name'].lower()
                if 'player' not in name or 'list' not in name:
                    continue
                pointer = r.q(manager + field['offset'])
                if r.cls(pointer) != 'List`1':
                    continue
                players = members(r, pointer)
                if 3 <= len(players) <= 12 and all(r.cls(p) == 'BattlePlayerData' for p in players):
                    candidates.append(field['offset'])
            if len(candidates) != 1:
                raise RuntimeError('无法确认唯一角色列表')
            self.manager, self.offset = manager, candidates[0]
        players = members(r, r.q(manager + self.offset))
        frontline = []
        positions = []
        for player in players:
            if r.cls(player) != 'BattlePlayerData':
                raise RuntimeError('角色列表已失效')
            position = r.i(player + 36)
            positions.append(position)
            if all_players or position in (0, 1, 2):
                master = r.q(r.q(player + 488) + 16)
                frontline.append(dict(actor_id=player, position=position,
                                      actor=r.string(r.q(master + 24)) or '未命名角色'))
        if positions != [r.i(player + 36) for player in players]:
            raise RuntimeError('正在换位，等待稳定站位')
        if sorted(p['position'] for p in frontline if p['position'] in (0, 1, 2)) != [0, 1, 2]:
            raise RuntimeError('前排站位不完整或重复')
        return sorted(frontline, key=lambda p: p['position'])
