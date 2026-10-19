"""Shared source semantics for UI suppression and damage stacking."""
COUNTED_PASSIVES={'Passive.ConsumeSpAttackUp01','Passive.ConsumeSpAttackUp03'}


def active(status):
    remaining=status.get('remaining')
    return (status.get('effective') is not False and not status.get('pending_add')
            and not status.get('pending_remove') and not
            (status.get('duration_kind') in ('turn','count') and isinstance(remaining,(int,float)) and remaining<=0))


def independent(status):
    source=status.get('source') or ''
    if source in COUNTED_PASSIVES:return False
    limit=status.get('source_effect',{}).get('effect',{}).get('limitType')
    if limit in ('Default','Once','Only'):return False
    return source.startswith(('Passive.','Accessory'))
