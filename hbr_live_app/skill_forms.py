"""Switchable skills (SkillSwitch): one card, several concrete forms.

Karen Asakura's 红尖晶石 / 堇青石 or 血腥燃烧 / 芬布尔之舞 are stored as a wrapper
whose children carry the real parts and hits. Calculations must use one child;
the wrapper itself has no attack part, so it silently produced no damage.
"""
from .damage_autofill import catalog_skill


def forms(label, lookup=None):
    """[(child_label, child_name, part_labels)] for a switch skill, else []."""
    if not label:
        return []
    skill = (lookup or catalog_skill)(label) or {}
    for part in skill.get('parts', []):
        if part.get('skill_type') != 'SkillSwitch':
            continue
        result = []
        for child in part.get('strval') or []:
            if isinstance(child, dict) and child.get('label') and isinstance(child.get('parts'), list):
                labels = {p.get('label') for p in child['parts'] if p.get('label')}
                result.append((child['label'], child.get('name') or child['label'], labels))
        return result
    return []


def detect(selected, options):
    """Pick the form whose part labels the game reported, if exactly one fits."""
    live = {p.get('Label') for p in selected.get('parts', []) if p.get('Label')}
    if not live:
        return None
    matches = [i for i, (_, _, labels) in enumerate(options) if live & labels]
    return matches[0] if len(matches) == 1 else None


def with_form(player, choice=None, lookup=None):
    """Return (player, note). choice=None auto-detects from live parts."""
    inputs = player.get('combat_inputs', player.get('inputs', {}))
    selected = inputs.get('selected_skill') or {}
    options = forms(selected.get('label'), lookup)
    if not options:
        return player, None
    index = choice if isinstance(choice, int) and 0 <= choice < len(options) else detect(selected, options)
    title = selected.get('name') or selected.get('label')
    if index is None:
        names = ' / '.join(name for _, name, _ in options)
        return player, f'{title}：可切换形态（{names}），未能自动判断，请在“技能形态”中选择'
    label, name, labels = options[index]
    chosen = dict(selected, label=label, name=name, switch_parent=selected['label'], switch_index=index,
                  parts=[p for p in selected.get('parts', []) if p.get('Label') in labels])
    inputs = dict(inputs, selected_skill=chosen)
    how = '手动选择' if index == choice else '按游戏读取的技能部件自动判断'
    return dict(player, combat_inputs=inputs, inputs=inputs), f'{title}：使用形态 {index + 1}「{name}」（{how}）'
