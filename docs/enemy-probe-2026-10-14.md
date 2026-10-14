# Boss 名称与行动规则探查（2026-10-14）

## 实测

用户在异度监测之眼 Ω：等级 4（MasterEnemy ID 13402704、Label ExoWatcherDefault01_04）指令阶段配合，只读读取。groupLabel ExoWatcherDefault01 仅为底层分组名，不足以精确匹配关卡版本。

原始快照 sessions/enemy-probe-181643.json；两轮过程 sessions/enemy-probe-181805.jsonl，均不提交。筛选后的规则、观测顺序和字段布局保存在 tests/fixtures/enemy_rules.json、enemy_layout.json。

- Turn 1 指令阶段：派生类 mainCommandPatternOrder=0，_selectedCommands=null。
- 敌方行动判定：派生类进度变 1，选出 ExoWatcherD_AttackSingle01 和 ExoWatcherD_Charge，依次执行单体攻击、Power Pool。
- Turn 2 指令阶段：进度仍 1，_selectedCommands 仍保留上轮两技能；不能作为下一回合预告。
- 规则序号 2 为 IsEnemyCharge() 条件下的 Heavy Burst；事先向用户给出这一预期。
- 第二次敌方行动实际执行 ExoWatcherD_ChargeAttackAll01 / Heavy Burst，派生类进度变 2，之后进入 Turn 3。样本已足够验证前两步，停止探查，不再要求用户冒团灭风险。
- 基类 BattleCharacterData 同名进度字段始终 0。读取必须区分 declared class，不能仅按字段名选第一个。

## 本次布局证据

BattleEnemyData domainEnemy +480 → DomainEnemy master +16 → MasterEnemy：Id +16、Label +24、Name +32、MasterCommandPattern +80、BreakMasterCommandPattern +88。

BattleEnemyData：_selectedCommands +600、派生 main/breakCommandPatternOrder +608/+612、isEnemyCharge +592；基类 breakDownTurn +128。正式读取按元数据字段名、声明类、类型校验与定位，并独立降级，不使伤害采集中断。

当前 DP/HP 规则组分别 ExoWatcherDefaultHard / ExoWatcherDefaultHard_break。本地 cn enemy_details 与实际 MasterEnemy 精确匹配。此版本本地仅有 cn/jp，未提供英文名；其他精确匹配 en 的敌人可切换国际服名。

## 接入与边界

每敌人一张卡片；中文直接读游戏 Name，英文取相同 ID+Label 的资料，保留内部名称供点击切换。详情显示全部名称和完整规则。

预告来自当前阶段的 order+1 规则，标明“规则预告”，不宣称整条未来必然发生。可解析空条件和 IsEnemyCharge()；未知条件标记候选且不闪烁。随机分支展示为备选，权重在详情保留。未验证循环重置/跳过逻辑，因此末尾不自动回卷。倒地、特殊覆盖、多段血条或资料不匹配不预测。HP 阶段与其他 Boss 的实际进度语义仍需后续实测。

闪烁仅限正在采样、指令选择阶段的有效预告；暂停、停止、超过三秒无心跳、死亡/离场时停止。所有新增敌方数据保存在既有快照与导出结构，不混入角色伤害总计。

探查工具：python -B -m hbr_live_app.probe_enemies；--watch 最多十分钟，只写 sessions。sessions/enemy-probe-stop 是持久停止标记，下次观察前需确认上一轮已结束后手动移除，避免重复采集。游戏以管理员运行时同样需要通过系统授权启动探查。

此前通过实测的版本 6ea5891 已推送。此次 Boss 功能留在工作区，待用户验收后再提交。
