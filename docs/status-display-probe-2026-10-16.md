# Buff 褪色标识调研

用户提供截图：高值回合攻击力提升亮色、低值次数攻击力提升（加速）褪色，次数效果尚存、并未被消耗。用户保持该角色详情页打开后，只读采样确认显示层存在直接标记。

读取链：BattleModule.hudModule → battleMemberHudModule → uiBattleStatus → battleStatusContainer → dataList → Entity。

Entity 字段包括 statusLabel、statusComment、continuationCount 和 float alpha。当前页面对应角色为手冢咲。

- 雷属性攻击力提升，来源祈祷之花，托付于风，剩余 4 回合：alpha=1.0。
- 普通攻击力提升，同来源，剩余 4 回合：alpha=1.0。
- 普通攻击力提升，来源加速，剩余 1 次：alpha=0.5。
- 暴击伤害提升，来源加速，剩余 1 次：alpha=1.0。

注意不要读取错字段：低值攻击力提升行的 buffIcon.buffIconAlpha 仍为 1.0，变化的是外层行 Entity.alpha。XIUIBattleStatus 有 canvasGroup，行透明度控制整行显示。

样本保存于 tests/fixtures/status_display_rows.json；完整动态地址和采样对象保存在被 Git 忽略的 sessions/status-display-131059.json 及其 .statuses.json 中。地址不用于后续跨会话定位。

底层 SpecialStatus 中未发现对应的直接生效布尔字段。本次只确认当前已打开页面的显示结果，尚未确认关闭页面后的刷新、切换角色后的归属及同名同来源多实例匹配。**不要直接把该 UI 缓存当作全队实时 effective 状态。**原始 Buff 仍需完整保留，压制只影响当前是否贡献效果；不能按褪色删除或消费次数。

挂件中的 effective=False 目前仍是此前同值 Only 连击珠的规则筛选。本次没有把 UI alpha 接入生产筛选，以免把陈旧详情页数据应用到当前战斗。probe_status_display.py 仅用于只读调研。

## 未打开详情页的复核

用户明确表示本次没有打开详情页。只读样本为 sessions/status-display-185359.json 及其 .statuses.json：

- battleStatusContainer.dataList 的 _size=0、_version=1；_listItems 同样为空，没有可读取的行 alpha。
- UIBattleStatus3 的 isOutAnimationFinish=True、isInAnimationFinish=False；页面 Entity 没有 namelabel 文本，tabContainer=0、isPlayer=False。
- 底层 SpecialStatusManager 仍有 64 个状态对象，说明底层状态读取不依赖打开详情页。

本次确认“未打开详情页时，该显示列表可以为空”，所以不能依靠 UI alpha 进行后台全队实时生效筛选。它不能证明“曾经打开再关闭”时列表必然被清空，也不能证明关闭后的旧缓存会刷新。维持原始状态完整保存，不把缺失的 UI 行解释为 Buff 消失或不生效。

## 程序更新

增加独立于详情页的保守展示推断：相同加攻种类、相同已知属性、无额外目标条件时，如果有限期 Only=4 加攻在 DP 和 HP 两个数值上都严格大于另一有限期加攻，则将较弱者折叠并标注“暂被覆盖（规则推断）”。原始实例、数值和次数完整保留；每次状态采样重新计算，覆盖者结束后旧效果可重新显示。永久效果、属性未知、待增删、过期以及无法比较的效果不参与此规则。不把该结果称为直接读取到的游戏生效标记。

新增回归测试覆盖次数效果保留与恢复、永久效果独立、属性隔离、待增删、未知条件和 DP/HP 强弱交叉；全套 122 项测试通过。
