# HP 耳坠规则核对

参考源码：https://github.com/RoyWu0922/hbr_calc_web/blob/local-db/src/engine/damage.ts

2026-11-01 读取公开源码：calcEquipmentBonus 将 HP 耳坠按主 Hit 数折算；calculateAll 把装备值与主动、被动加攻相加。该函数没有逐段目标 DP/HP 判断，不能证明“HP 特攻技能即使打 DP 也能获得耳坠加成”。

本地运行时读到 AttackUpRangeByHit，VsDpRate=0、VsHpRate=1，以及 amountOnHpDamageInt=1500。当前按用户早期规则并入 HP 特攻，和参考网站存在乘区差异；此次用户允许不明确时暂缓，暂不改数值。自动填充备注已标注这一限制，后续需要同场景有／无耳坠逐段对照确认。

无耳坠对照的四段实际／预测为1.0676、0.9470、1.0304、1.0803，破坏率终值215.92%。这支持该场景的基础跨池路径，但不能确定耳坠乘区。
