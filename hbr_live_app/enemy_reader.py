"""Read validated enemy identity and AI progress, independently of damage collection."""
from .enemy_info import EnemyCatalog, forecast


class EnemyReader:
    def __init__(self, r):
        self.r = r
        self.layouts = {}
        self.catalog = EnemyCatalog()

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
                        r.read(enemy+fields['<existsHpExtraGauge>k__BackingField'], 1) != b'\0' or
                        r.read(enemy+fields['<existsDpExtraGauge>k__BackingField'], 1) != b'\0' or
                        r.q(domain+df['<overrideMainCommandPattern>k__BackingField']) or
                        r.q(domain+df['<overrideBreakCommandPattern>k__BackingField'])))
        if live['down'] is None:
            raise RuntimeError('倒地状态读取失败')
        preview = forecast(info, live, context) if state['hp'] > 0 else dict(text='已击败', blink=False)
        return dict(enemy_label=strings['Label'], enemy_id=identity, names=aliases,
                    action_rules=info['rules'], enemy_progress=live, forecast=preview)
