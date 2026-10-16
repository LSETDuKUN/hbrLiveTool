"""Read validated enemy identity and AI progress, independently of damage collection."""
from .enemy_info import EnemyCatalog
from .enemy_observations import EnemyObservations
from .enemy_preview import EnemyPreview


class EnemyReader:
    def __init__(self, r):
        self.r = r
        self.layouts = {}
        self.catalog = EnemyCatalog()
        self.observations = EnemyObservations()
        self.previews = EnemyPreview()

    def offsets(self, obj, cls, required):
        r = self.r
        if r.cls(obj) != cls:
            raise RuntimeError('敌方资料布局不可读')
        key = (r.q(obj), cls)
        if key not in self.layouts:
            fields = r.fields(obj)['fields']
            self.layouts[key] = {(f['declared'], f['name']): (f['offset'], f['type']) for f in fields}
        result = {}
        for name, (declared, kind) in required.items():
            offset, actual = self.layouts[key].get((declared, name), (None, None))
            if actual != kind:
                raise RuntimeError('敌方字段类型不兼容')
            result[name] = offset
        return result

    def sample(self, state, context):
        r, enemy = self.r, state['address']
        fields = self.offsets(enemy, 'BattleEnemyData', {
            'domainEnemy': ('BattleEnemyData', 18), 'overrideEnemy': ('BattleEnemyData', 18),
            '<mainCommandPatternOrder>k__BackingField': ('BattleEnemyData', 8),
            '<breakCommandPatternOrder>k__BackingField': ('BattleEnemyData', 8),
            'isEnemyCharge': ('BattleEnemyData', 2),
            '<existsHpExtraGauge>k__BackingField': ('BattleEnemyData', 2),
            '<existsDpExtraGauge>k__BackingField': ('BattleEnemyData', 2),
            '<breakDownTurn>k__BackingField': ('BattleCharacterData', 8)})
        domain = r.q(enemy + fields['domainEnemy'])
        df = self.offsets(domain, 'DomainEnemy', {
            '<master>k__BackingField': ('DomainEnemy', 18),
            '<overrideMainCommandPattern>k__BackingField': ('DomainEnemy', 18),
            '<overrideBreakCommandPattern>k__BackingField': ('DomainEnemy', 18)})
        master = r.q(domain + df['<master>k__BackingField'])
        mf = self.offsets(master, 'MasterEnemy', {n: ('MasterEnemy', t) for n, t in
            [('Id', 10), ('Label', 14), ('Name', 14), ('MasterCommandPattern', 14), ('BreakMasterCommandPattern', 14)]})
        strings = {n: r.string(r.q(master+offset)) for n, offset in mf.items() if n != 'Id'}
        if not strings['Label']:
            raise RuntimeError('敌方资料标识缺失')
        identity = r.q(master + mf['Id'])
        info = self.catalog.lookup(strings['Label'], identity)
        aliases = [dict(kind='cn', name=strings['Name'])] if strings['Name'] else []
        aliases += [dict(n) for n in info['names'] if n['kind'] != 'cn' or not aliases]
        aliases.append(dict(kind='internal', name=state['name']))
        charged = r.read(enemy + fields['isEnemyCharge'], 1)
        if charged not in (b'\0', b'\1'):
            raise RuntimeError('蓄力状态读取失败')
        live = dict(dp=state['dp'], dp_pattern=strings['MasterCommandPattern'],
                    hp_pattern=strings['BreakMasterCommandPattern'],
                    dp_order=r.i(enemy+fields['<mainCommandPatternOrder>k__BackingField']),
                    hp_order=r.i(enemy+fields['<breakCommandPatternOrder>k__BackingField']),
                    down=r.i(enemy+fields['<breakDownTurn>k__BackingField']), charged=charged == b'\1',
                    overridden=bool(r.q(enemy+fields['overrideEnemy']) or
                        r.q(domain+df['<overrideMainCommandPattern>k__BackingField']) or
                        r.q(domain+df['<overrideBreakCommandPattern>k__BackingField'])))
        for pool in ('dp', 'hp'):
            raw = r.read(enemy+fields['<exists'+pool.capitalize()+'ExtraGauge>k__BackingField'], 1)
            live[pool+'_extra'] = raw != b'\0'
            if not live[pool+'_extra']:
                continue
            try:
                name = pool+'IndexInternal'
                off = self.offsets(enemy, 'BattleEnemyData', {name: ('BattleCharacterData', 17)})[name]
                index = r.i(enemy+off)
                live[pool+'_index'] = index
                name = '_commandPatternList' if pool == 'dp' else '_breakCommandPatternList'
                off = self.offsets(domain, 'DomainEnemy', {name: ('DomainEnemy', 21)})[name]
                sequence = r.q(domain+off)
                if r.cls(sequence) != 'List`1':
                    raise RuntimeError('行动阶段列表未确认')
                from .source import members
                groups = members(r, sequence)
                if not isinstance(index, int) or not 0 <= index < len(groups):
                    raise RuntimeError('行动阶段索引未确认')
                group = groups[index]
                name = '<groupLabel>k__BackingField'
                off = self.offsets(group, 'DomainEnemyCommandPattern', {
                    name: ('DomainEnemyCommandPattern', 14)})[name]
                live[pool+'_active_pattern'] = r.string(r.q(group+off))
            except (RuntimeError, ValueError, TypeError, KeyError):
                live[pool+'_active_pattern'] = None
        if live['down'] is None:
            raise RuntimeError('倒地状态读取失败')
        live.update(self.observations.state(enemy, live, context))
        for pool in ('dp', 'hp'):
            name = '<defaultMax' + pool.capitalize() + '>k__BackingField'
            try:
                off = self.offsets(enemy, 'BattleEnemyData', {name: ('BattleEnemyData', 10)})[name]
                maximum = r.q(enemy+off)
                if 0 <= maximum <= 10**12:
                    live[pool+'_max'] = maximum
                if 0 < maximum <= 10**12:
                    live[pool+'_rate'] = state[pool]/maximum
            except (RuntimeError, ValueError, KeyError):
                pass
        # Optional state fields are metadata-validated independently; missing
        # fields degrade individual conditions rather than the entire card.
        for name, key, kind in [('enemyChargeStep', 'charge_step', 8), ('_damageRate', 'damage_rate', 12)]:
            try:
                off = self.offsets(enemy, 'BattleEnemyData', {name: ('BattleEnemyData', kind)})[name]
                if kind == 8:
                    live[key] = r.i(enemy+off)
                else:
                    import struct
                    raw = r.read(enemy+off, 4)
                    if len(raw) == 4:
                        live[key] = struct.unpack('<f', raw)[0]
            except (RuntimeError, ValueError, KeyError):
                pass
        preview = self.previews.update(enemy, info, live, context) if state['hp'] > 0 else dict(text='已击败', blink=False)
        return dict(enemy_label=strings['Label'], enemy_id=identity, names=aliases,
                    base_resistances=info.get('base_resistances'),
                    action_rules=info['rules'], enemy_progress=live, forecast=preview)
