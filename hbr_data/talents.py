"""Style-owned talents retain their explicit unlock tier and source path."""
def style_talents(style):
    rows=[]
    def add(value,group,tier,path):
        if not value:return
        if isinstance(value,str):value={'label':value}
        if not isinstance(value,dict):return
        rows.append(dict(group=group,tier=tier,path=path,data=value))
    add(style.get('roleabi'),'职业天赋',None,'/roleabi')
    for i,value in enumerate(style.get('passives') or []):add(value,'基础天赋',0,f'/passives/{i}')
    for i,level in enumerate((style.get('limit_break') or {}).get('bonus_per_level') or []):
        for j,value in enumerate(level.get('bonus') or []):
            add(value,'上限突破',level.get('step'),f'/limit_break/bonus_per_level/{i}/bonus/{j}')
    add(style.get('resonance'),'共鸣天赋',None,'/resonance')
    return rows


def expand_resonance(rows):
    result=[]
    for row in rows:
        levels=row['data'].get('list')
        if row['group']=='共鸣天赋' and isinstance(levels,list):
            for i,level in enumerate(levels):
                if isinstance(level.get('passive'),dict):
                    result.append(dict(row,tier=level.get('lb_lv'),data=level['passive'],
                                       path=row['path']+f'/list/{i}/passive'))
        else:result.append(row)
    return result
