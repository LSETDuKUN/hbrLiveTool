# 仆人弱点条件、OD 精确量与获取量饰品

## BIYamawakiServant 修正

依据用户订正，该状态属于加攻乘区中的弱点限定增幅，可与普通心眼同时生效。新增单独可编辑的“仆人心眼”输入；仅在最终相性严格大于 1，或未被吸收的贯通暴击成立时加入。普通心眼和它相加，不参与彼此取最高。仍读取 rateValueInt / 100，当前资料为 40%；状态本身重复实例最多一份。

## OD 只读采样

生产读取 BattleModule.overDriveManager → BattleOverDriveManager，字段名及类型校验后读取 `_currentPoint`、`activatedLevel`、`consumedPoint`，并以 BattleInfoManager.isOverDriveTurn 判断当前是否处于 OD。不把缓存的 activatedLevel、剩余 Bonus 回合数或库存数当作当前发动状态/等级。

用户现场确认发动一级 OD 后，采样得到：isOverDriveTurn=true、activatedLevel=1、consumedPoint=10000、currentPoint=7000；因此显示剩余 70.00%，伤害自动填 ×1.1。历史一级样本 currentPoint=5774 对应 57.74%，initial 样本 13012 对应 130.12%。一个百分点对应 100 原始点，主界面保留两位小数。保留负点数，不提前截成 0；读取失败显示暂不可读，不伪造零值。

`_currentStockCount` 为另一个字段，不加到当前量表。本轮不假定其完整语义。

OD 数据随常规战斗包更新，并进入保存摘要和试算快照。当前 OD 等级 1/2/3 对应 ×1.1/1.2/1.3；结束后自动填充恢复 ×1，等级未确认时暂用 ×1 并提示。自动填充仅在用户点击或首次打开试算时覆盖表单，后台采样仍不覆盖用户手工修改。

现场资料 `sessions/od-before.json`、`sessions/od-probe.json` 留在忽略目录。测试 fixture 使用只读采样的 OD/回合对象及合成模块根连接。

## OD 饰品

匹配已拥有的 `Passive.Start_OverDrivePointUpByHitEarring01/02/03`，读取本地装备内嵌的 OverDrivePointUpByHit part。当前最高档 power=[0.05,0.15]，value=[1,10]，Self、IsFront、OnPlayerTurnStart。

按主 Hit 数线性插值，1 Hit +5%、10 Hit 及以上 +15%，不按追加连击提高装备档位；其他档位读取自身资料端点。不把最高 15% 硬套到所有技能。技能主 Hit 未确认则标记待核对。

试算的属性页显示“OD 饰品获取量增幅”，结果区单独显示获取倍率与例子：20% × 1.15 = 23%。它不乘当前已有的 OD 条，也不乘伤害。未预测技能最终会获得多少 OD（目标数、相性、命中与固定 OD 等仍需另外处理）。这部分已对资料和公式做回归，本轮没有实测逐 Hit 的 OD 增量。

回归包括弱点边界、仆人与心眼相加、吸收优先、OD 小数精度、等级 1/2/3、结束后缓存等级不生效、读取失败、OD 饰品插值与不影响伤害，以及主界面到试算的 OD 数据连通。
