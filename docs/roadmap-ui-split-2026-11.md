# 下一阶段计划：前后端拆分与界面重构（2026-11）

状态：规划，未实施。基线分支 `optimize-review`（含离线试算、技能形态、共享敌方属性）。
目标：把"读取 / 计算"和"界面"拆开，使两部分可以由不同的人并行开发、单独测试；随后按方案 A 重构 Tk 界面，并保留将试算类窗口迁到网页（方案 C）的可能。

---

## 0. 现状与拆分原则

当前耦合点（交接时最需要知道的）：

| 位置 | 问题 |
| --- | --- |
| `damage_window.py`（~1000 行） | 同时负责布局、状态管理、调用 `autofill`、合并预添加效果、DP/HP 逐段、序列步骤；逻辑写在按钮回调里，无法脱离 Tk 测试 |
| `app.py` | 采样线程、模型更新、窗口生命周期、导出全部在一个类 |
| 快照 dict | 实际上已是前后端之间的数据契约（`players / enemies / field_state / od_state / turn_context`），但没有文档和版本号 |
| `effect_editor.py` / `team_window.py` | 界面直接拼装计算参数 |

原则：

1. **后端不 import tkinter**；前端不直接读内存、不直接写 SQLite、不自行拼计算参数。
2. 两边只通过一个 Python 服务层（`hbr_live_core`）交换**纯数据**（dict / dataclass，可 JSON 序列化）。
3. 先抽出契约和服务层并保持现有界面可用，再动界面。每一步都应能单独合并。

---

## 1. 后端（读取、计算、存储）

### B1. 定义数据契约（优先级最高，约 2–3 天）

- 新建 `hbr_live_core/schema.py`：用 `TypedDict` 或 dataclass 描述 `Snapshot`、`Player`、`Enemy`、`Status`、`SelectedSkill`、`TeamPayload`、`CalcRequest`、`CalcResult`，带 `schema_version`。
- 以现有字段为准（`combat_inputs.stats / selected_skill / passive_audit`、`enemy_progress`、`base_resistances` 等），**不改名**，只补文档；不确定字段标注"观测值，可能缺失"。
- 交付：schema 文件 + `docs/snapshot-contract.md` + 从 `tests/fixtures` 生成的示例 JSON。
- 验收：现有 fixtures 全部能通过 schema 校验（写一个 `tests/test_schema.py`）。

### B2. 抽出计算服务层（约 1–1.5 周）

把 `damage_window.py` 中非界面的流程移到 `hbr_live_core/damage_service.py`：

```
prepare(snapshot, actor_id, enemy_address, options) -> PreparedCalc
    # 现 fill()：形态解析、共享敌方属性、模式判断、autofill、预添加效果合并
apply_pending(prepared, action, payload) -> PreparedCalc     # 现 update_pending()
compute(prepared, overrides) -> CalcResult                   # 现 compute()：伤害、分布、逐段破坏率
sequence_add / sequence_undo / sequence_clear                 # 现 DamageSequence 包装
```

- `options` 包含：超越/高阶增幅模式、技能形态、敌方属性覆盖、目标判定（auto/dp/hp）、暴击开关等——即当前界面上的所有开关。
- `overrides` 为用户手改过的乘区与参数（字符串转数字、校验也在后端完成，返回字段级错误）。
- 界面层只保留"把控件值收集成 options/overrides → 调用 → 渲染结果"。
- 验收：
  - 新增不依赖 Tk 的测试，覆盖 `fill → 预添加 → compute` 全链路（可复用 `test_damage_*` 的 fixtures）；
  - 现有 331 项测试全部通过；同一输入下新旧路径结果逐字段一致（写一次性对比脚本）。

### B3. 离线试算服务（约 2–3 天）

- `offline_battle.py` 已是纯函数；补一个 `OfflineSession`（配队、技能选择、手动状态、敌人、场地/OD）→ `snapshot()`，并支持保存/读取为 JSON（"试算方案"，便于分享和回归）。
- 验收：保存 → 读取 → 计算结果一致。

### B4. 采样与模型解耦（约 1 周，可与 B2 并行）

- 把 `app.py` 中 `pump()` 的采样、模型更新、配队采样、自动保存移到 `hbr_live_core/live_session.py`，对外只暴露 `start / stop / pause / latest_snapshot() / events()`。
- 线程安全：快照以不可变副本交付（现在多处直接引用 `self.model.*`）。
- 验收：无界面运行（命令行）可连接游戏并输出快照 JSON。

### B5. 存储与数据（小项，随时可做）

- `TeamStore` 增加 schema 迁移（目前 `schema=1` 写入但从不检查）。
- 并发写下载缓存时 Windows `os.replace` 可能报 `PermissionError`（已知小概率问题），加一次重试。
- 场地加成 < 0 时 `calculate()` 拒绝负值——**需先由用户确认游戏中是否存在降低伤害的场地**，再决定是否放开。

### B6.（可选，为方案 C 做准备）本地 HTTP 接口

- 在服务层之上加一个很薄的本地服务（如 FastAPI，仅监听 127.0.0.1）：`GET /snapshot`、`POST /damage/prepare`、`POST /damage/compute`、`GET /teams` 等，直接映射 B2/B3 的函数。
- 只有决定走方案 C 时才做；B1–B4 完成后约 3–4 天。

### 后端待办中仍需游戏实测的项（不要外包方自行"修正"）

- 士气同时作为加攻读取是否会重复计算（目前状态上通常无伤害数值，暂不改）。
- 实战中可切换技能的形态自动判断是否总能命中。
- 尚未审查的模块：`enemy_*`、`status_*`、`statuses.py`、`events.py`、`model.py`、`battle_table.py`、`player_transitions.py`、`planned_actions.py`、`formation.py`、`hbr_data` 其余文件。

---

## 2. 前端（界面，方案 A：保留 Tk）

依赖：F1 可立即开始；F2 起依赖 B2 的服务接口（可先对着接口桩开发）。

### F1. 设计系统（约 1 周，可立即开始）

- `theme.py` 整理为设计令牌：间距阶梯（4/8/12/16/24）、圆角（S/M/L）、字号阶梯、语义色（伤害=粉、增益=青、减益=玫红、破坏率=金、中性=灰），去掉各窗口内的硬编码数值。
- 组件库补全并统一：`Section`（带标题/说明/折叠）、`Field`（标签 + 输入 + 单位 + 错误提示）、`FormGrid`（按字段定义自动排版）、`Fold`（替换现有 `tk.Button` 折叠条）、`ResultStat`（大号数字 + 说明）。
- 性能：圆角控件只在尺寸/状态真正变化时重绘（现在每次 `<Configure>` 和悬停都全量重画）。
- 交付：组件 + 一个 `python -m hbr_live_app.gallery` 组件预览窗口（每个组件的各种状态），供验收和以后换皮。
- 验收：预览窗口在两套主题、100%/150% 缩放下截图无错位；现有窗口替换折叠条后外观一致。

### F2. 伤害试算窗口改为三栏（约 1.5–2 周）

```
┌──────────── 设置 ────────────┬──────── 乘区 ────────┬──── 结果（常驻）────┐
│ 实战：角色 / 敌人 / 形态      │ 连击、加攻、暴击、    │ 平均伤害（大字）     │
│ 离线：配队 / 技能 / 敌人参数  │ 减防、相性、破坏率…   │ 90% 区间、概率图      │
│ 敌方属性（全局）              │ 每组可折叠，改动高亮  │ 破坏率 起点 → 终点    │
│ Buff/Debuff（手动 + 预发动）  │                      │ 跨 DP/HP 逐段摘要     │
└──────────────────────────────┴─────────────────────┴─────────────────────┘
        次级页（抽屉或标签）：技能参数、饰品、内存原始参数、被动审查
```

- 实战与离线共用同一窗口，只是"设置"栏内容不同（替代现在的子类 + 额外标签页）。
- 用户手改过的字段显示"已手改"标记和一键恢复自动值。
- 结果栏在窗口宽度不足时折叠到下方（最小宽度约 980px）。
- 验收：常见操作（选角色 → 改一个乘区 → 看结果）不需要切换标签；所有现有功能可达。

### F3. 配队档案与离线试算整合（约 1 周）

- 档案页：左侧配队列表，右侧成员卡（头像、六维、技能含形态、饰品），"用此配队试算"直接带入 F2 的设置栏。
- 支持保存/读取"试算方案"（依赖 B3）。

### F4. 主界面（实时浮窗）轻量整理（约 1 周）

- 只做一致性：统一组件、间距、颜色语义；**不改信息结构**，因为战斗中需要小窗口快速扫读。
- 先确认用户实际使用的窗口尺寸与紧凑模式使用频率。

### F5.（可选）方案 C：试算/档案/资料库迁到网页

- 前提：B6 完成。技术建议：pywebview 承载，前端 Vue 或 Svelte + 现成图表库；实时浮窗仍用 Tk。
- 只迁移表单多、需要排版的窗口；实时浮窗继续留在 Tk。

---

## 3. 建议顺序与可并行性

```
第 1–2 周   B1 契约 ─────────┐            F1 设计系统（并行）
第 2–4 周   B2 计算服务 ──────┼─ B4 采样解耦（并行）
第 4–5 周   B3 离线会话       │            F2 三栏试算窗口（对接 B2）
第 5–6 周                     └──────────  F3 档案整合、F4 主界面整理
之后（可选） B6 HTTP 接口  →  F5 网页化
```

外包建议：

- 后端与前端分给不同的人；**B1 契约由维护者本人确认后再开工**，它是两边唯一的约定。
- 每个任务单独分支、单独 PR；合并条件：全部测试通过 + 新增测试 + 截图（前端）。
- 不允许外包方修改计算规则（`damage_math.py`、`damage_autofill.py` 的乘区/叠加逻辑）——规则变动必须有游戏实测依据，由维护者决定。
- 交接材料：本文件、`docs/snapshot-contract.md`（B1 产出）、`tests/fixtures`、一份已保存的配队档案（去除个人信息）。

## 4. 需要维护者先确认的问题

1. 选 A（Tk 重构）还是直接 C（试算类网页化）？本文默认 A，保留 C。
2. 实时浮窗在战斗中通常的窗口大小、是否常用紧凑模式。
3. 场地是否可能降低伤害（决定 B5 中负场地加成的处理）。
4. 是否需要"试算方案"文件可在玩家之间分享（影响 B3 的格式是否要稳定、是否去除个人数据）。
