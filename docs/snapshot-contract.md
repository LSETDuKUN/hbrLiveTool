# 快照数据契约（Snapshot Contract）

`schema_version = 1` · 路线图 B1 产出 · 定义见 [`hbr_live_core/schema.py`](../hbr_live_core/schema.py)

快照是"读取 / 计算"与"界面"之间唯一的数据约定：计算窗口只调用 `snapshot() -> Snapshot`。实时快照由 `hbr_live_core.snapshot.live_snapshot(model, connected)` 生成，离线快照由 `hbr_live_app.offline_battle.snapshot(...)` 生成，二者结构相同。

## 规则

- **字段名沿用现状，不改名**；本文只补文档。`inputs` 是 `combat_inputs` 的旧别名，保留兼容。
- 标注"观测"的字段来自游戏内存：可能缺失或为 `null`（读取失败、游戏版本变化、离线方案中没有）。消费方必须容忍。
- 允许出现未列出的字段（诊断信息等）；消费方忽略不认识的字段。
- 数值：JSON 只有一种数字，`int` 可用于 `float` 位置；`bool` 不算数字。
- 地址类标识（`actor_id`、`address`）：实时为整数内存地址，离线为字符串（`offline-0`、`offline-enemy`）。
- 校验：`hbr_live_core.validate(data, kind)` 返回问题列表；`check()` 不符时抛 `SchemaError`。
- 示例：`tests/fixtures/contract/*.json`，由 `python -m hbr_live_core.examples [sessions/<run>.jsonl]` 生成。
- 已用 40 份本地实战记录（8000+ 个快照）回放校验；其中可能为 `null` 的观测字段已在类型中标注。

## Snapshot

| 字段 | 类型 | 必需 | 说明 |
| --- | --- | --- | --- |
| `schema_version` | int | | 契约版本（新增字段） |
| `connected` | bool | ✓ | 是否已连接战斗；离线恒为 true |
| `offline` | bool | | 离线试算快照 |
| `run_id` | str / null | ✓ | 本场标识；离线为 `offline:<配队>` |
| `execution_revision` | int | ✓ | 观察到新的已执行指令时递增；计算窗口据此清空预演 |
| `turn_context` | TurnContext / null | | 回合状态（观测） |
| `players` | list[Player] | ✓ | 我方六人 |
| `enemies` | list[Enemy] | ✓ | 仅当前在场敌人 |
| `field_state` | FieldState / null | | 场地 |
| `element_gauge` | ElementGauge / null | | 元素槽（观测） |
| `od_state` | OdState / null | | OD 状态（观测） |

## Player

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `actor_id` | int / str（必需） | 角色标识 |
| `actor_position` | int / null | 0–2 前排，3–5 后排 |
| `actor` / `name` | str / null | 角色名；`name` 为列表显示名 |
| `style_label` / `style_name` | str / null | 风格标识与名称 |
| `dp` / `hp` / `dp_max` / `hp_max` | 数值 / null | 观测 |
| `expected_dp` / `expected_hp` | 数值 / null | 观测，行动后预计值 |
| `mode_count` / `another_form` | int / bool | 强化使用次数、另一形态（观测） |
| `statuses` / `statuses_available` | list[Status] / bool | 状态读取失败时为 `[]` + false |
| `combat_inputs` / `inputs` | PlayerInputs | 计算输入 |

## PlayerInputs（全部为观测）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `unavailable` | bool | 整体读取失败 |
| `stats` | dict | `power / dexterity / toughness / spirit / wisdom / luck` |
| `token` | int | |
| `reinforced_mode_turn` | int / null | |
| `current_sp` / `expected_sp` / `sp_to_consume` | int / null | |
| `passive_labels` / `passive_audit` | list | 运行时持有的被动（PassiveAudit：`label`、`name`、`condition`、`timing`、`description`、`parts`、`catalog_found`、`classification`、`runtime`） |
| `equipped_skills` | list[SkillRef] | SkillRef：`label`、`base_label`、`name`、`level` |
| `selected_skill` | SelectedSkill | 当前选中技能，未选时为 `{}` |

## SelectedSkill

`label`、`base_label`、`name`（可为 null）、`name_source`、`level`、`base_sp_cost`（可为 null）、`hit_count`、`parts`（游戏原始键名：`Label`、`Power`、`MaxPower`……）。解析切换形态后追加 `switch_parent`、`switch_index`。

## Status

| 字段 | 说明 |
| --- | --- |
| `label`（必需） | 如 `SpecialStatus.AttackUp` |
| `name` / `value` / `duration` | 显示文本 |
| `values` | 数值：`rateValueInt`、`amountOnDpDamageInt`、`amountOnHpDamageInt`、`numValue`… |
| `source` / `source_name` / `source_effect` | 来源技能或被动；`source_effect` 可为 `{}` |
| `element_type` / `element_key` / `element_name` | 属性，可为 null |
| `buff_limit_type` | 叠加类型，可为 null |
| `remaining` / `duration_kind` | 剩余数；`turn`、`count`、`permanent`… |
| `hidden` / `pending_add` / `pending_remove` | 观测标记 |
| `effective` / `effective_basis` / `effective_reason` | 规则推断（非游戏标记） |
| `manual` | 离线手动添加 |

## Enemy

| 字段 | 说明 |
| --- | --- |
| `address` / `name` / `dp` / `hp`（必需） | 标识、名称、当前值 |
| `active` | 是否在场 |
| `dp_max` / `hp_max` | 可为 null |
| `enemy_id` / `enemy_label` / `names` | 资料匹配；EnemyName：`kind`（cn/en/internal）、`name` |
| `action_rules` / `forecast` | 行动预告，仅供显示，不是计算输入 |
| `base_resistances` | 属性/武器 → 数值，另含 `absorb_element_list`、`ignore_penetration`；可为 null |
| `enemy_progress` | EnemyProgress |
| `statuses` / `statuses_available` | 同 Player |
| `combat_inputs` / `inputs` | EnemyInputs：`stats`、`token`、`_defenseRefParam`（敌方属性，伤害差与减益共用）、`_borderRefParam` |
| `dp_reference` / `hp_reference` / `dp_change` / `hp_change` / `dp_rises` / `hp_rises` | 实时模型追加的观测统计 |

### EnemyProgress（观测）

`damage_rate`（破坏率 %，≥100）、`down`、`destruction_coefficient`、`destruction_max`、`dp`、`dp_max`、`hp_max`、`dp_rate`、`hp_rate`、`dp_index`、`dp_order`、`hp_order`、`dp_pattern`、`hp_pattern`、`dp_active_pattern`、`dp_extra`、`hp_extra`、`charged`、`charge_step`、`enemy_count`、`enemy_executing`、`enemy_pending`、`recent_break`、`overridden`、`last_actions`、`played_counts`、`observed_played_counts`、`played_complete`、`played_source`、`shield`。

`shield`（ShieldState，可为 null；子字段多数可为 null）：`index`、`total`、`remaining`、`broken`、`breaks_this_turn`、`limit_per_turn`、`locked`、`complete`、`next_dp`、`turn`、`source`、`capacity_source`。

## 战斗全局

- **TurnContext**：`selecting`（指令选择中）、`turn`、`phase`、`phase_count`、`command_count`、`command_visit`、`additional`、`extra`、`extra_turn`、`extra_actor_ids`、`od`、`od_level`、`od_activation`、`od_before_enemy`、`bonus`、`bonus_max`、`frontline`（FrontlineSlot：`actor_id`、`actor`、`position`）、`fsm_address`、`state_address`。
- **FieldState**：`available`、`statuses`（必需）。
- **ElementGauge**：`value`、`maximum`、`element`、`name`、`full`（必需）。
- **OdState**：`available`、`active`、`level`、`points`、`percent`、`consumed_points`、`last_activated_level`。

## TeamPayload（配队档案，`teams.payload`）

`schema`（必需，当前 1）、`captured_at`、`context`、`members`（必需）。TeamMember：`style_label`、`stats`（必需）、`actor`、`style_name`、`position`、`dp`、`hp`、`dp_max`、`hp_max`、`skills`、`skills_complete`、`passives`。

## 计算服务（草案，B2 定稿）

- **CalcOptions**：`transcend` / `high_boost`（`auto`/`on`/`off`）、`transcend_element`、`form_index`、`enemy_stat`、`target_pool`（`auto`/`dp`/`hp`）、`critical`、`penetration_critical`、`absorbed`、`damage_metric`（`raw`/`applied`）。
- **CalcRequest**：`actor_id`、`enemy_address`（必需）、`options`、`overrides`（用户手改值，后端校验）。
- **CalcResult**：`ok`（必需）、`errors`（字段 → 消息）、`damage`、`mean`、`low`、`high`、`destruction_start`、`destruction_end`、`notes`。

## 版本规则

新增可选字段不升版本；删除、改名或改变类型时 `SCHEMA_VERSION` +1，并在本文记录迁移说明。
