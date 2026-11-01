"""Navigation order only; never executes or implicitly commits a skill."""
from .damage_autofill import catalog_skill
from hbr_data.skill_tree import effects
ATTACKS={'AttackSkill','AttackNormal','TokenAttack','PenetrationCriticalAttack','AttackByOwnDpRate','AttackBySp','DamageRateChangeAttackSkill'}

def ordered_frontline(players,lookup=None):
    lookup=lookup or catalog_skill
    rows=[]
    for index,player in enumerate(players):
        position=player.get('actor_position')
        if position not in (0,1,2):continue
        selected=player.get('combat_inputs',player.get('inputs',{})).get('selected_skill',{})
        if not selected.get('label'):continue
        parts=list(effects(lookup(selected['label']) or {}))
        damage=any(p.get('skill_type') in ATTACKS for p in parts)
        if not parts:damage=any(p.get('skill_type_raw')==10 for p in selected.get('parts',[]))
        rows.append((damage,{1:0,0:1,2:2}[position],index))
    return [r[2] for r in sorted(rows)]
