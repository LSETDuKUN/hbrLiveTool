"""One command per table row, with front-line positions preserved."""
from collections import OrderedDict
from .turns import context_label

DISPLAY_POSITIONS = (1, 0, 2)
POSITION_NAMES = {1: '左', 0: '中', 2: '右'}


def actor_title(event):
    style = event.get('style_name') or event.get('style_label')
    return event['actor'] + (f' / {style}' if style else '')


def is_pursuit(event):
    return (event.get('skill_label') or '').startswith('Passive.Pursuit_')


def skill_title(event):
    return event['skill'] + (' · 追' if event.get('pursuit_count') else '')


def table_rows(events):
    rows = OrderedDict()
    for event in events:
        group = event.get('command')
        key = f'command:{group["id"]}' if group else f'unknown:{event["event_id"]}'
        row = rows.setdefault(key, dict(group=group, events=[]))
        row['events'].append(event)
    for row_key, row in list(rows.items()):
        slots = [[], [], []]
        unknown = []
        visible = []
        for event in row['events']:
            if is_pursuit(event):
                if visible:
                    visible[-1]['pursuit_count'] = visible[-1].get('pursuit_count', 0)+1
            else:
                visible.append(dict(event))
        row['pursuits'] = [e for e in row['events'] if is_pursuit(e)]
        if not visible:
            del rows[row_key]
            continue
        frontline = (row['group'] or {}).get('frontline')
        positions = {p['actor_id']: p['position'] for p in frontline} if frontline else None
        for event in visible:
            position = positions.get(event.get('actor_id')) if positions is not None else event.get('actor_position')
            if isinstance(position, int) and 0 <= position < 3:
                slots[position].append(event)
            else:
                unknown.append(event)
        # Game memory indexes the centre first; present screen left to right.
        slots = [slots[position] for position in DISPLAY_POSITIONS]
        cells = []
        for slot in slots:
            actors = OrderedDict()
            for event in slot:
                key = (event.get('actor_id', event['actor']), event.get('style_label'), event.get('style_name'))
                item = actors.setdefault(key, [actor_title(event), []])
                item[1].append(skill_title(event))
            cells.append('；'.join(name + '\n' + ' / '.join(skills) for name, skills in actors.values()) or '/')
        row['values'] = (context_label(row['group']), *cells)
        row['position_unknown'] = bool(unknown)
        row['unplaced'] = unknown
        row['slots'] = slots
    return rows
