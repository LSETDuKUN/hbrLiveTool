# 前排状态与元素量表

本轮只读实测：Turn 1 指令选择阶段，前排中位由 FMikoto04 换为 MAikawa09，位置、角色身份均更新。显示顺序继续使用内部位置 1、0、2，对应画面左、中、右。

SpecialStatusManager 是全场共享对象，specialStatusList 包含双方状态。必须将状态 owner 与角色 instanceId 对应，不能把整个列表挂在每个角色身上。ownerId 是状态所属角色，不当作技能施加者。

实际样本：
- Carol：SpecialStatus.MindEye，来源 CReaperSkill06，rateValueInt=15095，显示 150.95%。
- Boss：SpecialStatus.Fragile，来源 MAikawaSkill08，rateValueInt=3300，显示 33%。
- Boss：SpecialStatus.DefenseDown，来源 STezukaSkill02，DP/HP 参数均为 2155，显示 21.55%。

这些是本次生效值，不是资料库区间，不保证同一技能每次施加都相同。状态标签从 DomainSpecialStatus.master.Label 获取；不要使用本地数据库枚举序号对应运行时枚举。未核实的数字保留在详情原始参数中；不直接累加多个状态当作最终伤害倍率。预添加、预移除另行标识。

资源读取 hpInternal/dpInternal，最大值取 defaultMaxHp/defaultMaxDp。expectedHp/expectedDp 仅放详情，明确不是下一回合伤害预测。

BattleElementGaugeManager 独立管理元素量表，实测雷属性 enum=3，_currentPoint=maxPoint=10000。满量表时普通状态列表未出现与用户描述一致的整套爆发 Buff，因此只显示量表和“爆发增益待核实”，不臆造加攻、暴击率、暴伤或 Buff 强化倍率。其他元素枚举尚未逐一核实，暂显示通用“元素”。实际场地、爆发增益适用角色及公式仍需后续核对。

前排卡片显示头像、当前 DP/HP 和状态摘要，详情提供来源技能、状态计数与原始参数。Boss 卡片新增状态摘要与详情。状态共享列表约 0.4 秒刷新一次，玩家状态变化独立触发快照，不依赖敌方 HP 或行动事件变化。

## 分组展示调整

- 主窗口左侧前排、右侧 Boss，各自滚动；伤害卡片并排，留出战场区域。行动轴改为独立窗口，关闭仅隐藏，持续记录和导出方式不变。
- 已确认状态按加攻/心眼/场地、连击珠、暴击/暴伤、减防/脆弱、抗性/弱点分组，其他已识别减益另列。只分组，不直接计算乘区总倍率。
- 每个状态单列，保留元素、永久/剩余计数，点击可查来源。运行时元素枚举当前确认 0 普通、3 雷；其他枚举保留属性编号，避免擅自对应。
- 不确定、隐藏和预添加/预移除效果默认折叠；更新 HP 时保留折叠选择。采用固定多行与鼠标滚动，未使用自动轮播。
- 基础抗性/弱点尚未读取，不将空列表解释为无抗性。实际场地与爆发倍率仍属于上述未完成的调研项。

## 场地与生效筛选后续

稻场样本确认：全场共享 SpecialStatusManager.specialStatusList 中存在 RiceFieldZoneSpecialStatus；owner 指针为空、ownerId=0。此前读取器跳过无 owner 状态造成遗漏。FieldStateModule.fieldData 指向 BattleFieldModel，内容是战斗场景资料，不是该场地 Buff。

稻场来源 SKuraMasterlyPassiveSkill01，EternalExitCondition；rateValueInt=15500、numValue=313，与资料 power=1.55、value=313 一致。尚不解释特殊参数的最终伤害公式。现在独立读取无 owner 的 Zone/RiceFieldZone/SandStormZone，放在双方卡片上方；其余无 owner 状态不擅自归类为场地。场地变化独立触发快照。

乘区使用各自背景色。永久、回合、计数状态继续分列，明确为未生效的状态可以折叠。但生产读取器尚未确认游戏 UI 变灰的实际生效判断字段；当前不根据同名或大小盲目删除状态。用户补充的单独发动、最多两层及永久叠加规则已纳入后续验证要求，等待同类状态变灰样本核对后再接入实际筛选。

后续实测两份 RKayamoriSkill09b 连击珠：同 owner、numValue=5、rateValueInt=1200、buffLimitType=4，TurnEndExitCondition 分别剩余 1/2 回合。资料该技能 effect.limitType=Only，与用户确认的单独发动一致。未发现直接的 active/inactive 字段，因此采用保守的规则筛选：相同类型、元素、持续类别、Hit 数与倍率的 Only 连击珠只展示剩余时间较长的一份；另一份保留到折叠详情并明确筛选依据。不得将该结果描述为读到了游戏内部生效标记。

永久、回合、计数类别彼此不混合去重；其他倍率组合、普通次数层数上限以及其他类型的单独发动仍保留，不泛化未经验证的筛选逻辑。完整实例始终进入日志。`only_funnels.json` 和 `rice_field.json` 是本次实测结构回归样本。

## 元素场地、弱点与六人头像

新样本 MAikawaSkill56b：ZoneSpecialStatus.rateValueInt=19500、elementType=3、EternalExitCondition；原始场地系数 1.95，展示雷属性场地 +95%、永久。资料该技能的 Zone 部分 power=1.8、8 回合，但当前运行时已经是永久，实际面板必须优先当前状态，不能用技能描述覆盖。火/冰/雷/光/暗名称从精确来源技能中唯一匹配的同类型 parts.elements 解析，不再仅展示内部属性编号。存在多个不同候选时不猜测。

同源 ResistSpecialStatus.rateValueInt=-5940，显示弱点加深 59.4%。Boss 精确资料 ExoWatcherDefault01_04 的雷抗性记录 -300；用户确认游戏基础弱点显示为 300%。现在展示基础弱点加成（资料）300% + 加深 59.4% → 359.4%（加成推算）。该数值不是直接读取的最终伤害乘数，也不等同于破坏率。多项抗性变化、覆盖效果或状态不可读时不合算；基础资料可能与特殊机制下的实时抗性不同，保留“资料/推算”标识。

角色区改为全部六人固定头像槽，默认折叠 Buff；点击头像查看该角色 DP/HP、分组状态和详情。换位只更新前排边框及位置标记，复用头像控件，不移动头像、不反复重建全部角色卡片。紧凑模式默认隐藏角色区，可以手动勾选“角色状态”显示，采样和记录不受隐藏影响。
