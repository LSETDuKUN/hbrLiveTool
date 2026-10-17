# 装备攻击前增益

本轮只读定位了当前山胁的两条 DomainPassiveSkill 及其 MasterSkillPart，无需扫描安装目录或调用游戏方法。

- `Passive.Start_DarkEnhanceRing02`：Power≈0.06，VsDpRate=VsHpRate=1，资料为 Self / Dark / AttackUp；前排、玩家行动开始时触发。计入元素加攻 +6%，只用于暗属性技能。
- `Passive.Start_HPAttackUpRangeByHitEarring03`：SkillType=140（AttackUpRangeByHit），Power≈0.05，MaxPower≈0.15，Value1=10，Value2=1，VsDpRate=0、VsHpRate=1。运行时说明为“对 HP 技能攻击力最多 +15%，连击数越少效果越大”。本地物品名为攻击耳坠。
- 饰品并非固定 +6%。按参考网站 calcEquipmentBonus 的线性规则，在 1 Hit 为 15%、10 Hit 为 5%，9 Hit 约 6.111%；本实现根据本地端点插值，并在端点外保持其上/下限。主 Hit 数不含追加连击。超级大爆炸 10 个主 Hit 对应 +5%，而非硬编码用户估计的 6%。实际状态若读到 6%，则采用实际数值。未知主 Hit 数不猜测。

参考：[伤害网站的装备公式](https://github.com/RoyWu0922/hbr_calc_web/blob/local-db/src/engine/damage.ts)。本轮只读样本在忽略目录 `sessions/equipment-probe.json`，本地装备资料在 `sessions/equipment-catalog.json`。测试保留无进程地址的被动资料子集 `tests/fixtures/equipment_passives.json`。

## 原因与处理

这两条被动在本地数据库中嵌套于 accessories 记录的 effects / rng_eff 下，不是独立 records 行。新增精确标签递归查找与缓存，并要求匹配结果唯一。由运行时已拥有的标签确认具体装备档位，不按角色或物品名猜测。审查页也因此能够展示数值和对象。

预测只在已确认前排、预选攻击技能且属性匹配时补入。真实同源状态出现后优先读取最终 amountOnHpDamageInt，整条来源只计一份；实际效果的生效/过期/预添加/预移除标志仍筛选。戒指计元素加攻，饰品按用户既定规则与技能 HP 特攻相加，不把这两项送入普通主动加攻的两层竞争。

未找到通用“自动条件已满足”读取字段；此次使用已验证的 IsFront、技能元素和主 Hit 数，其他装备/复杂被动继续留待核对。没有修改游戏内存或触发游戏逻辑。

测试覆盖：6% 戒指、饰品各 Hit 边界、追击不影响主 Hit 数、HP 特攻加算、DP 情景不吃 HP 特攻、实际状态优先和去重、后排/普攻/错误元素排除、未装备/未知 Hit 不猜测、内嵌装备被动查找。
