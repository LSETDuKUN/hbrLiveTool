# 技能破坏倍率与逐段破坏率：调研记录

本轮仅更新公开技能资料、突出倍率显示；未接入逐段伤害递推。

## 数据核对

2026-10-18 重新下载 hbr.quest 的三个技能表：

- https://master.hbr.quest/v1/cn/skills.json ：655 条技能。
- https://master.hbr.quest/v1/en/skills.json ：613 条技能，与原本本地字节一致。
- https://master.hbr.quest/v1/skills.json ：728 条技能。

原库已经保存 `parts[].multipliers.dr`，对应 `skill_parts.destruction_multiplier`，无需迁移字段。此次仅刷新顶层 skills 表，其他资料保留各自抓取时间；current.json 的 partial_refresh 明确记录范围。原版本仍可恢复。原始下载及核对报告位于本地 sessions/destruction-source-check。

例：日服 BIYamawakiSkill55 的攻击效果 dr=4.5，STezukaSkill02 为 13.8。倍率属于效果，不应把多个效果无条件相加。界面现在在技能卡片折叠区域外展示该信息；零值和未提供分开处理。

## 参考模型（尚未进行游戏逐段验证）

来源：[计算器 calcBreakDetail 实现](https://github.com/RoyWu0922/hbr_calc_web/blob/local-db/src/engine/damage.ts)。

令 S 为技能破坏倍率，N 为本体段数，E 为敌人破坏系数（该实现输入 enemyDR/100），B 为生效的破坏率提升总量。破坏率 R 用倍率表示，1 对应 100%。

- 本体每段增量：ΔR = S/N × E × (1+B)。按段数均分，不按伤害权重分配。
- 连击每段增量：ΔR = S × 连击系数 × E × (1+B)。
- 本段伤害使用进入本段前的 R；下一段 R = min(上限, R+ΔR)。

该源码的表格注释与执行顺序存在歧义，上述顺序以实际代码为准，不能当作游戏时序已验证。参考实现将装备及其他增量相加，但各状态实际叠加规则还须沿用游戏有效状态筛选。

## 后续边界

需验证敌人字段单位、破盾那一段是否计入增长、连击实际顺序、取整时点、上限突破，以及多攻击效果的独立段数。不能把“破坏抗性”名称直接理解为 1-抗性。缺失伤害分配不能照搬参考实现的默认 0.05。此次不改变计算器结果，也不改变概率曲线。
