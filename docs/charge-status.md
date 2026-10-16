# 充能 / 蓄力状态

只读样本 sessions/status-display-193216.statuses.json 中发现手冢咲（ownerId 4001001）的 BuffChargeSpecialStatus，标签 SpecialStatus.BuffCharge，来源 AccessorySkillCharge01。回归样本保存于 tests/fixtures/charge_statuses.json。

- amountOnDpDamageInt、amountOnHpDamageInt 均为 3918，按伤害增益固定点字段显示技能伤害 +39.18%。
- CountExitCondition：totalCount=1、usedCount=0。
- rateValueInt=200000。未确认此类的暴击率定点尺度，不能照搬普通暴击状态的 /100；界面显示“暴击率提升（数值待核实）”，原始值保留在详情。

充能使用独立绿色乘区，不重复列入加攻或暴击区，不参与加攻覆盖推断。这里的玩家 BuffCharge 与敌人行动中的 Charge 蓄力不同，不混为同一状态。
