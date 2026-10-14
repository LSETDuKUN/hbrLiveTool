"""One command per table row, with front-line positions preserved."""
from collections import OrderedDict
from .turns import context_label


def table_rows(events):
    rows = OrderedDict()
    for event in events:
        group = event.get('command')
        key = f'command:{group["id"]}' if group else f'unknown:{event["event_id"]}'
        row = rows.setdefault(key, dict(group=group, events=[]))
        row['events'].append(event)
    for row in rows.values():
        slots = [[], [], []]
        unknown = []
        frontline = (row['group'] or {}).get('frontline')
        positions = {p['actor_id']: p['position'] for p in frontline} if frontline else None
        for event in row['events']:
            position = positions.get(event.get('actor_id')) if positions is not None else event.get('actor_position')
            if isinstance(position, int) and 0 <= position < 3:
                slots[position].append(event)
            else:
                unknown.append(event)
        cells = []
        for slot in slots:
            actors = OrderedDict()
            for event in slot:
                key = event.get('actor_id', event['actor'])
                item = actors.setdefault(key, [event['actor'], []])
                item[1].append(event['skill'])
            cells.append('；'.join(name + '\n' + ' / '.join(skills) for name, skills in actors.values()) or '/')
        row['values'] = (context_label(row['group']), *cells)
        row['position_unknown'] = bool(unknown)
        row['unplaced'] = unknown
        row['slots'] = slots
    return rows
