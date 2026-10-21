"""Experimental, read-only battle source; never attaches using stale saved addresses."""
import json
import struct
import time
from pathlib import Path

from .events import ActionLedger
from .turns import TurnReader, CommandLedger
from .formation import FormationReader
from .enemy_reader import EnemyReader
from .overdrive import read_overdrive


def members(r, address):
    size = r.i(address + 24)
    if size is None or not 0 <= size <= 256:
        raise RuntimeError('列表布局不匹配或战斗对象已失效')
    array = r.q(address + 16)
    return [r.q(array + 32 + j * 8) for j in range(size)]


def locate(r):
    """Find class metadata then instances; reject ambiguous retained battles."""
    names, _ = r.scan(b'BattleModule\0')
    if not names:
        raise RuntimeError('未找到战斗运行时，请进入战斗后重试')
    refs, _ = r.scan(tuple(struct.pack('<Q', n) for n in names), seconds=60)
    classes = {ref - 16 for ref in refs if r.name(r.q(ref)) == 'BattleModule'
               and r.name(r.q(r.q(ref - 16 + 88) + 16))}
    if not classes:
        raise RuntimeError('未找到 BattleModule 类，游戏版本可能不兼容')
    refs, _ = r.scan(tuple(struct.pack('<Q', k) for k in classes), seconds=60)
    candidates = []
    for obj in refs:
        parent = r.q(obj + 16)
        manager = r.q(obj + 144)
        if r.cls(parent) != 'BattleState' or r.q(parent + 360) != obj:
            continue
        if r.cls(manager) != 'BattleCharacterDataManager':
            continue
        try:
            enemies = members(r, r.q(manager + 168))
            if enemies and all(r.cls(e) == 'BattleEnemyData' for e in enemies):
                if any(r.q(e + 72) > 0 for e in enemies):
                    candidates.append(obj)
        except RuntimeError:
            continue
    candidates = list(set(candidates))
    if len(candidates) != 1:
        raise RuntimeError(f'找到 {len(candidates)} 个可能的战斗对象，无法安全选择。请进入战斗后重试；若仍有多个，请重启游戏。')
    obj = candidates[0]
    required = {64: 'BattleInfoManager', 96: 'BattleActionEntryManager',
                144: 'BattleCharacterDataManager', 216: 'BattleTimelineManager'}
    if any(r.cls(r.q(obj + offset)) != name for offset, name in required.items()):
        raise RuntimeError('游戏内存布局不兼容，此版本暂不可读取')
    return obj


def snapshot(r, module):
    manager = r.q(module + 144)
    enemies = members(r, r.q(manager + 168))
    states = []
    for enemy in enemies:
        if r.cls(enemy) != 'BattleEnemyData':
            raise RuntimeError('敌方对象失效，请重新连接')
        raw = r.read(enemy + 72, 16)
        if len(raw) != 16:
            raise RuntimeError('资源读取中断，已停止，保留最后有效值')
        hp, dp = struct.unpack('<qq', raw)
        if min(hp, dp) < 0 or max(hp, dp) > 10**12:
            raise RuntimeError('资源值越界，已停止读取')
        states.append(dict(address=enemy, hp=hp, dp=dp, name=r.string(r.q(enemy + 496)) or f'敌人 {len(states)+1}'))
    action_manager = r.q(module + 96)
    entries = members(r, r.q(action_manager + 16))
    preserved = r.q(action_manager + 40)
    if preserved and preserved not in entries:
        entries.append(preserved)
    actions = []
    for entry in entries:
        if r.cls(entry) != 'ActionEntry':
            raise RuntimeError('行动对象布局不匹配')
        actor = r.q(entry + 32)
        skill = r.q(entry + 24)
        master = r.q(r.q(skill + 16) + 16)
        card = r.q(r.q(actor + 488) + 16) if r.cls(actor) == 'BattlePlayerData' else 0
        hit_set = r.q(entry + 40)
        hits = []
        if hit_set:
            for hit in members(r, r.q(hit_set + 16)):
                if r.cls(hit) != 'HitInfo':
                    raise RuntimeError('命中对象布局不匹配')
                content = r.q(hit + 32)
                if r.cls(content) != 'HitContent':
                    raise RuntimeError('命中内容已失效')
                target = r.q(hit + 24)
                target_is_player = r.cls(target) == 'BattlePlayerData'
                target_style = r.string(r.q(r.q(r.q(target+488)+16)+24)) if target_is_player else ''
                target_name = target_style if target_is_player else r.string(r.q(target + 496)) if r.cls(target) == 'BattleEnemyData' else None
                hits.append(dict(address=hit, target=target, target_name=target_name,
                    target_is_player=target_is_player, target_style_label=target_style, type=r.i(hit + 16),
                    finished=r.read(hit + 41, 1) == b'\1', damage=r.i(content + 36) or 0,
                    raw_damage=r.i(content + 32), result_type=r.i(content + 28),
                    index=r.i(hit + 20), funnel=r.read(content + 174, 1) == b'\1',
                    critical=r.read(content + 171, 1) == b'\1'))
        style_label = r.string(r.q(card + 24)) if card else ''
        actor_class = r.cls(actor)
        instant = actor_class == 'BattleSpecialCommandCharacterData'
        actions.append(dict(instant=instant, style_label=style_label, address=entry, actor=actor, actor_position=None if instant else r.i(actor + 36), actor_is_player=actor_class in ('BattlePlayerData', 'BattleSpecialCommandCharacterData'), executing=entry == preserved, actor_name=style_label or ('小按钮' if instant else actor_class),
            skill=r.string(r.q(master + 24)), skill_name=r.string(r.q(master + 32)) or '未知技能',
            hit_set=hit_set, hits=hits))
    return states, actions


def run(stop, paused, emit, outdir):
    from . import runtime as r
    from .windows import game_pid
    from .names import Names
    import uuid
    r.STOP = stop
    run_id = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    ledger = ActionLedger()
    commands = CommandLedger()
    from .planned_actions import PlannedActions
    planned = PlannedActions()
    names = Names()
    enemy_reader = EnemyReader(r)
    from .player_transitions import PlayerTransitions
    player_transitions = PlayerTransitions()
    from .statuses import StatusReader
    status_reader = StatusReader(r)
    previous_players = None
    previous_gauge = None
    previous_fields = None
    try:
        r.open_process(game_pid())
        emit(('status', '正在定位战斗，请暂不行动…'))
        module = locate(r)
        states, actions = snapshot(r, module)
        if actions:
            raise RuntimeError('正在行动中，请等指令选择阶段再连接。')
        turn_reader = None
        formation_reader = FormationReader(r, module)
        last_formation = None
        formation_visit = None
        turn_warning = None
        try:
            turn_reader = TurnReader(r, module)
        except (RuntimeError, ValueError) as exc:
            turn_warning = f'回合分组不可用，继续记录角色行动：{exc}'
        path = Path(outdir) / (run_id + '.jsonl')
        path.parent.mkdir(parents=True, exist_ok=True)
        previous = None
        known_enemies = {s['address'] for s in states}
        heartbeat = 0.0
        with path.open('x', encoding='utf-8') as log:
            log.write(json.dumps({'schema': 2, 'run_id': run_id, 'kind': 'start', 'time': time.time()})+'\n')
            log.flush()
            emit(('connected', {'run_id': run_id, 'path': str(path)}))
            if turn_warning:
                emit(('status', turn_warning))
            previous_context = None
            previous_od = None
            while not stop.is_set():
                if paused.is_set():
                    planned.pending=None
                    enemy_reader.observations.invalidate()
                    player_transitions.invalidate()
                    stop.wait(0.1)
                    continue
                context = None
                if turn_reader:
                    try:
                        context = turn_reader.sample()
                    except (RuntimeError, ValueError) as exc:
                        turn_reader = None
                        emit(('status', f'回合分组已停止，继续记录角色行动：{exc}'))
                states, actions = snapshot(r, module)
                if context:
                    visit = context.get('command_visit')
                    if context['selecting'] or context.get('phase') == '味方ターン開始' or visit != formation_visit:
                        try:
                            last_formation = formation_reader.sample()
                            for player in last_formation:
                                player['actor'] = names.actor(player['actor'])
                        except RuntimeError:
                            last_formation = None
                        formation_visit = visit
                    context['frontline'] = last_formation
                if not states:
                    break
                enemy_reader.observations.update(states, actions)
                for state in states:
                    try:
                        state.update(enemy_reader.sample(state, context))
                    except (RuntimeError, ValueError, TypeError, KeyError):
                        state['forecast'] = dict(text='敌方行动信息暂不可读', blink=False)
                known_enemies.update(s['address'] for s in states)
                for action in actions:
                    action['style_name'] = names.style(action['style_label']) if action.get('style_label') else ''
                    action['actor_name'] = names.actor(action['actor_name'])
                    for hit in action['hits']:
                        hit['target_style_name'] = names.style(hit['target_style_label']) if hit.get('target_style_label') else ''
                        if hit.get('target_name'):
                            hit['target_name'] = names.actor(hit['target_name'])
                player_states = []
                transitions = []
                try:
                    player_states = player_transitions.sample(r, formation_reader, names)
                    transitions = player_transitions.update(player_states)
                except (RuntimeError, ValueError, TypeError, KeyError):
                    player_transitions.invalidate()
                events = commands.update(transitions + ledger.update(actions, known_enemies), context)
                for player in player_states:
                    try:
                        player.update(status_reader.sample(player['actor_id'], resources=True))
                        if context and context.get('selecting'):
                            from .damage_inputs import read_selection
                            inputs=dict(player.get('combat_inputs',{}))
                            inputs.pop('selected_skill',None)
                            inputs.update(read_selection(status_reader,player['actor_id']))
                            player['combat_inputs']=inputs
                    except (RuntimeError, ValueError, TypeError, KeyError):
                        player.update(statuses=[], statuses_available=False)
                for state in states:
                    state.update(status_reader.sample(state['address']))
                planned_events=planned.update(context,player_states)
                gauge = status_reader.element_gauge(module)
                fields = status_reader.sample_fields(module)
                od_state=read_overdrive(status_reader,module)
                if states != previous or events or planned_events or context != previous_context or player_states != previous_players or gauge != previous_gauge or fields != previous_fields or od_state != previous_od:
                    packet = dict(time=time.time(), enemies=states, events=events, turn_context=context,
                                  player_states=player_states, planned_events=planned_events, element_gauge=gauge, field_state=fields,od_state=od_state)
                    emit(('snapshot', packet))
                    log.write(json.dumps(packet, ensure_ascii=False)+'\n')
                    log.flush()
                    previous = states
                    previous_context = context
                    previous_players = player_states
                    previous_gauge = gauge
                    previous_fields = fields
                    previous_od = od_state
                if time.monotonic() - heartbeat >= 1:
                    emit(('heartbeat', time.time()))
                    heartbeat = time.monotonic()
                if all(s['hp'] == 0 for s in states) and not actions:
                    break
                stop.wait(0.02)
            log.write(json.dumps({'kind': 'end', 'time': time.time(), 'reason': 'stopped' if stop.is_set() else 'battle_end'})+'\n')
        emit(('status', '已停止 · 记录已保存' if stop.is_set() else '战斗结束 · 记录已保存'))
        if not stop.is_set():
            emit(('battle_end', {'run_id': run_id}))
    except InterruptedError:
        emit(('status', '已取消连接'))
    except Exception as exc:
        emit(('error', str(exc)))
    finally:
        if r.h:
            r.close(r.h)
            r.h = None
        emit(('stopped', None))
