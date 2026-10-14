# 回合与整段行动的运行时探查（2026-10-13）

本记录来自用户配合的一场国服实际战斗，只读访问游戏内存。诊断入口为
`python -B -m hbr_live_app.probe_turns`，原始数据位于不提交 Git 的
`sessions/turn_probe/`。尚未接入正式采集或 UI。

## 定位链与字段

仍使用 source.locate 动态查找并校验 BattleModule，不复用上次进程地址。
以下偏移为本次观测值，后续需按类名、字段名与类型校验。

- BattleModule + 64 → BattleInfoManager
  - +16 int squadTurn：本次与界面 Turn 1、Turn 2 对应。
  - +20 int prevSquadTurn：进入 Turn 2 后仍为 0，不能直接当上一回合。
  - +24/+28 int maxExtraTurn/extraTurn，+32 bool isExtraTurn：本场始终 0/false，语义未验证。
  - +36/+40 int maxOverDriveTurn/overDriveTurn：本次对应 Bonus 总数/当前序号。
  - +44 bool isOverDriveTurn。
  - +45 bool isOverDriveBeforeEnemyTurn：本次后置 OD 为 true。
  - +48 int overDriveCount：本次发动后为 1。
  - +56 List<BattlePlayerData> additionalTurnCharacters。
  - +64 bool isAdditionalTurn。
- BattleModule +80 → BattleOverDriveManager
  - +72 int activatedTurn，+80 int activatedLevel：本次均为 1。
- BattleModule +16 → BattleState；+168 → SubStateModule；+48 → ArborFSM。
  - ArborFSM +224 → 当前 State。
  - State +80 → 名称字符串，+88 → uint transitionCount，+24 → NodeID。
  - 指令选择状态名 `コマンド選択`。

## 已观测流程

1. 初始指令选择：Turn 1，无追加/OD。
2. 第一段行动后：Turn 1，isAdditionalTurn=true（用户确认单人追加）。
3. 同一角色再次行动后仍追加：Turn 和标记不变，但状态机经历我方开始、执行、追加判定、指令选择；指令选择 transitionCount 从 2 增为 3。
4. 用户普攻接一级后置 OD：Turn 1，Bonus 1/1，isOverDriveTurn=true，isOverDriveBeforeEnemyTurn=true，isAdditionalTurn=false；指令选择计数为 4。
5. OD 行动后再次追加：Turn 1、Bonus 1/1 均保持，isAdditionalTurn=true；OD 与追加标记同时为真。额外只读快照确认列表有 3 个 BattlePlayerData，position 分别为 0、1、2，与用户前排三人反馈对应；指令选择计数为 5。
6. 三人追加结束：OD 当前/总回合归零，OD、后置 OD 和追加标记均 false；随后经过敌方开始、执行、结束状态，Preturn 阶段 squadTurn 由 1 增至 2，返回指令选择计数为 6。
   - 用户观察 Boss 倒地，downturn 1→0，实际未出手。诊断未采集敌方倒地计数，不能把此数值变化写成内存验证结果。
7. Turn 2 斩杀：我方开始节点计数增至 6，经过行动预计算、执行、我方结束，然后进入 PreResult → BattleClear → Result；squadTurn 保持 2，没有再次进入指令选择。最后一段行动应在战斗结束时封口，无需等待下一次开始行动。

## 实现注意

- 用户定义的整段行动，是每次按开始行动到下一次按开始行动；不同于 ActionEntry 的单角色技能。
- 整段编号应依据实际我方执行边界，独立于主 Turn；OD 和追加须保存为可同时存在的属性。
- 进入指令选择次数不能直接当点击次数；发动 OD 等流程也可能重新进入选择阶段。
- 本次 State 计数有先读到旧值、下一采样才递增的情况；字段读取不是原子快照。不能把瞬态不一致当作两次行动。
- 可以进一步研究固定“我方回合开始”节点的 transitionCount，避免只靠当前状态轮询漏掉短阶段。本次尚未持续监控所有固定节点，不能宣称已验证其完整性。
- 100ms 诊断采样不保证捕获每个短暂状态；正式实现需去重、校验和录制回放测试。
- 本场共 6 次开始行动：Turn 1 普通、单人追加、再次单人追加并接后置 OD、OD Bonus 1/1、OD 内三人追加，以及 Turn 2 斩杀。第一段开始时未采状态机，其起始来自用户操作反馈及已有行动对象采样，其余开始阶段均有状态机记录。
- 原 source.run 已有全体敌人 HP 为 0 且无行动时退出的判断；上述结算状态用于补充边界探查，尚未改变原结束逻辑。
- 尚待验证：前置 OD、多级 OD、ExtraTurn 语义及其他特殊流程。


## 首次实现的实测修正

20261013-195622-e70409 与 20261013-195844-fdb899 的会话表明：连接时缓存的指令节点计数分别停在 1、2，selecting 离开后始终 false，但 additional 与 squadTurn 正常变化。旧实现将后续角色事件全部归到首组，并保留了首组的普通回合标签。日志不足以进一步确定是哪个缓存对象失效。

改为每次沿 BattleModule → BattleState → SubStateModule.instance → 当前 State 读取，按当前节点名称判断指令选择，记录当前状态计数和对象地址用于诊断。每次重新进入选择（或选择节点/计数发生变化）分配本地 command_visit，角色事件据此分组，组内后续结算仍保持原归属。旧 command_count 作为游戏读数保留，不再单独充当新会话的分组主键。

新增旧指针计数冻结、当前节点及 FSM 替换、同 Turn 同标记重复追加的模拟回归，以及从调研记录精简出的 43 帧真实状态变化回放。45 项测试通过，修复后的游戏现场实测仍待用户确认。


## 自动战斗与表格呈现

20261013-200756-2b6777 的自动战斗记录显示，自动使用 `オート` 准备节点，手动的 `コマンド選択` 只在连接时出现一次。该记录覆盖 Turn 1 普通与两次连续追加、Turn 2 普通、Turn 3 普通与追加，共六批。现在将自动准备节点纳入相同的批次逻辑；真实事件回放验证六批分别建立，角色事件数量及伤害总额保持不变。

界面改成每批一行：Turn/Bonus/Extra 标签加三格前排角色与技能，详情默认收起。BattlePlayerData +36 的 position 保存到事件 actor_position（本次探查中确认前排为 0、1、2），按位置放入表格，未观测到行动的格显示 /。同一位置多次技能不会覆盖原内容。批次内部的事件顺序仍保留在详情和导出中。
