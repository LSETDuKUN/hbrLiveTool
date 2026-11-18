"""Design system component gallery (Roadmap F1).

Run from the terminal to preview every shared component across palettes and
display scales::

    python -B -m hbr_live_app.gallery
"""
import argparse
import tkinter as tk

from . import theme
from .components import (
    Field,
    Fold,
    FormGrid,
    Pill,
    ResultStat,
    RoundedButton,
    RoundedCard,
    RoundedEntry,
    RoundedSelect,
    Segment,
    Section,
    TabBar,
    ToggleChip,
)


class GalleryWindow:
    def __init__(self, root=None, palette=None, scale=None):
        self.root = root or tk.Tk()
        if palette:
            theme.use(palette)
        theme.install(self.root)
        if scale is not None:
            theme.SCALE = float(scale)
        self.root.title('HBR Live · 组件设计系统预览 (F1 Gallery)')
        self.root.geometry('1020x820')
        self.root.configure(bg=theme.BG)
        self.palette_var = tk.StringVar(self.root, value=theme.NAME)
        self.scale_var = tk.StringVar(self.root, value=f'{int(round(theme.SCALE * 100))}%')
        self.build()

    def build(self):
        for child in list(self.root.winfo_children()):
            child.destroy()
        self.root.configure(bg=theme.BG)

        head = tk.Frame(self.root, bg=theme.BG)
        head.pack(fill='x', padx=theme.SPACE_XL, pady=theme.SPACE_LG)
        tk.Label(
            head, text='✦ 设计系统组件预览 · Gallery',
            bg=theme.BG, fg=theme.SEMANTIC_DAMAGE,
            font=theme.ui(theme.FONT_XL, 'bold'),
        ).pack(side='left')

        controls = tk.Frame(head, bg=theme.BG)
        controls.pack(side='right')
        Segment(
            controls,
            [(k, theme.TITLES.get(k, k)) for k in theme.options()],
            self.palette_var,
            command=self._switch_palette,
            accent=theme.SEMANTIC_BUFF,
        ).pack(side='left', padx=theme.SPACE_SM)
        Segment(
            controls,
            [('100%', '100% 缩放'), ('150%', '150% 缩放')],
            self.scale_var,
            command=self._switch_scale,
            accent=theme.SEMANTIC_DESTRUCTION,
        ).pack(side='left')

        # Semantic tokens strip
        tokens = Section(
            self.root,
            '语义色彩与胶囊标签 (Pill / Buttons / Chips)',
            hint='伤害=粉 · 增益=青 · 减益=玫红 · 破坏率=金 · 中性=灰',
            accent=theme.SEMANTIC_BUFF,
        )
        tokens.pack(fill='x', padx=theme.SPACE_XL, pady=theme.SPACE_SM)
        row = tk.Frame(tokens.body, bg=theme.CARD)
        row.pack(fill='x', pady=theme.SPACE_XS)
        for label, color, deep in (
            ('伤害 Damage', theme.SEMANTIC_DAMAGE, theme.PINK_DEEP),
            ('增益 Buff', theme.SEMANTIC_BUFF, theme.CYAN_DEEP),
            ('减益 Debuff', theme.SEMANTIC_DEBUFF, theme.ROSE_DEEP),
            ('破坏率 Destruction', theme.SEMANTIC_DESTRUCTION, theme.GOLD_DEEP),
            ('中性 Neutral', theme.SEMANTIC_NEUTRAL, theme.NEUTRAL_DEEP),
        ):
            Pill(row, label, fg=color, bg=deep).pack(side='left', padx=theme.SPACE_XS)
        RoundedButton(
            row, '主操作按钮', bg=theme.PINK_FILL, fg=theme.on_fill,
            font=theme.ui(theme.FONT_SM, 'bold'), height=32,
        ).pack(side='left', padx=theme.SPACE_SM)
        RoundedButton(
            row, '禁用状态', state='disabled', bg=theme.CARD_HI, fg=theme.DIM,
            font=theme.ui(theme.FONT_SM), height=32,
        ).pack(side='left', padx=theme.SPACE_XS)
        self.chip_var = tk.BooleanVar(self.root, value=True)
        ToggleChip(row, '暴击开关', self.chip_var, accent=theme.SEMANTIC_DESTRUCTION).pack(
            side='left', padx=theme.SPACE_SM
        )

        # ResultStat hero numbers
        stats_row = tk.Frame(self.root, bg=theme.BG)
        stats_row.pack(fill='x', padx=theme.SPACE_XL, pady=theme.SPACE_SM)
        stats_row.columnconfigure(0, weight=1)
        stats_row.columnconfigure(1, weight=1)
        self.stat_damage = ResultStat(
            stats_row,
            '平均打出伤害 (ResultStat)',
            value='1,284,560.00',
            caption='中央 90% 浮动区间：1,168,200 – 1,401,900',
            accent=theme.SEMANTIC_DAMAGE,
        )
        self.stat_damage.grid(row=0, column=0, sticky='nsew', padx=(0, theme.SPACE_SM))
        self.stat_dr = ResultStat(
            stats_row,
            '破坏率递推终值 (ResultStat)',
            value='150% → 286.4%',
            caption='跨 DP/HP 逐段计算 · 模型内击杀概率 94.2%',
            accent=theme.SEMANTIC_DESTRUCTION,
        )
        self.stat_dr.grid(row=0, column=1, sticky='nsew', padx=(theme.SPACE_SM, 0))

        # Section + FormGrid + Field + Fold
        form_section = Section(
            self.root,
            '自动排版表单与字段校验 (Section / FormGrid / Field / Fold)',
            hint='支持单位标注与字段级错误提示',
            accent=theme.SEMANTIC_DAMAGE,
            collapsible=True,
            opened=True,
        )
        form_section.pack(fill='x', padx=theme.SPACE_XL, pady=theme.SPACE_SM)
        self.form_grid = FormGrid(
            form_section.body,
            [
                ('attack', '普通加攻', '%'),
                ('element_attack', '元素加攻', '%'),
                ('defense_down', '普通减防', '%'),
                ('fragile', '脆弱', '%'),
            ],
            columns=2,
            bg=theme.CARD,
        )
        self.form_grid.pack(fill='x')
        self.form_grid.fields['attack'].set('165')
        self.form_grid.fields['defense_down'].set('invalid')
        self.form_grid.set_errors({'defense_down': '请输入有效的减防百分比数字'})

        self.fold = Fold(self.root, '可折叠次级详情区 (Fold)', prominent=True, opened=True)
        self.fold.pack(fill='x', padx=theme.SPACE_XL, pady=theme.SPACE_SM)
        tk.Label(
            self.fold.body,
            text='折叠区内容：用于收纳逐 Hit 明细、计算假设备注与调试数据。',
            bg=theme.BG, fg=theme.DIM, font=theme.ui(theme.FONT_SM), anchor='w',
        ).pack(fill='x', pady=theme.SPACE_SM)

    def _switch_palette(self):
        theme.use(self.palette_var.get())
        theme.install(self.root)
        self.build()

    def _switch_scale(self):
        theme.SCALE = 1.5 if self.scale_var.get() == '150%' else 1.0
        self.build()


def main(argv=None):
    parser = argparse.ArgumentParser(description='HBR Live Design System Gallery (F1).')
    parser.add_argument('--palette', choices=theme.options(), default='midnight')
    parser.add_argument('--scale', type=float, default=None)
    parser.add_argument('--check', action='store_true', help='Render all palettes/scales and exit (for CI).')
    args = parser.parse_args(argv)

    root = tk.Tk()
    if args.check:
        root.withdraw()
        gallery = GalleryWindow(root, palette=args.palette, scale=args.scale)
        for pal in theme.options():
            for sc in (1.0, 1.5):
                gallery.palette_var.set(pal)
                gallery.scale_var.set('150%' if sc == 1.5 else '100%')
                gallery._switch_palette()
                gallery._switch_scale()
                root.update_idletasks()
        root.destroy()
        return 0
    GalleryWindow(root, palette=args.palette, scale=args.scale)
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
