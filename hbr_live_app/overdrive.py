"""Metadata-checked OD values; gauge points are hundredths of one percent."""


def read_overdrive(reader,module):
    try:
        manager=reader.prop(module,'overDriveManager')
        info=reader.r.q(module+64)
        if reader.r.cls(manager)!='BattleOverDriveManager' or reader.r.cls(info)!='BattleInfoManager':
            raise ValueError('OD 对象不可读')
        expected={'_currentPoint':8,'activatedLevel':8,'<consumedPoint>k__BackingField':8}
        fields=reader.fields(manager)
        if any(fields.get(key,(0,0))[1]!=kind for key,kind in expected.items()):raise ValueError('OD 字段类型不匹配')
        before=reader.prop(info,'isOverDriveTurn')
        points=reader.get(manager,'_currentPoint');level=reader.get(manager,'activatedLevel')
        consumed=reader.prop(manager,'consumedPoint')
        after=reader.prop(info,'isOverDriveTurn')
        if before is None or before!=after or not -30000<=points<=1000000 or not 0<=level<=3:
            raise ValueError('OD 正在切换或数值不可用')
        return dict(available=True,points=points,percent=points/100,active=bool(after),
                    level=level if after and level in (1,2,3) else None if after else 0,
                    last_activated_level=level,consumed_points=consumed)
    except (RuntimeError,ValueError,TypeError,KeyError):return dict(available=False)


def od_label(state):
    if not state or not state.get('available'):return 'OD · 暂不可读'
    mode=('发动中 Lv.'+str(state['level']) if state.get('level') else '发动中 · 等级待确认') if state['active'] else '未发动'
    return f"OD {state['percent']:.2f}% · {mode}"


def action_od_level(group):
    if not group or not group.get('od'):return None
    level=group.get('od_level',group.get('bonus_max'))
    return level if level in (1,2,3) else None


def action_background(group,default):
    from . import theme
    level=action_od_level(group)
    # User-requested colours, not extracted game assets. Theme blend keeps text legible.
    color={1:'#f09090',2:'#8fd6a0',3:'#efd06a'}.get(level)
    return theme.mix(default,color,.24) if color else default
