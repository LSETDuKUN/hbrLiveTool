"""Separate compact gauges for every enemy, with stable session numbers."""
import tkinter as tk
import time
from tkinter import font as tkfont

from . import theme
from .components import rounded
from .gauge_trail import GaugeTrail


class EnemyCard(tk.Canvas):
    def __init__(self, parent, number, show_details=None):
        super().__init__(parent, height=232, bg=parent.cget('bg'), highlightthickness=0, bd=0)
        self.number = number
        self.state = None
        self.show_details = show_details
        self.name_kind = 'cn'
        self.monitoring = False
        self.flash = True
        self.timer = None
        self.trail_timer = None
        self.wheel_timer = None
        self.wheel_identity = None
        self.roll_started = 0
        self.footer_y = 219
        self.trails = {p: GaugeTrail() for p in ('dp', 'hp')}
        self.bind('<Button-1>', self.click)
        self.bind('<Destroy>', self.on_destroy)
        self.font = tkfont.Font(family=theme.UI_FAMILY, size=-12)
        self.small = tkfont.Font(family=theme.UI_FAMILY, size=-11)
        self.name_font = tkfont.Font(family=theme.UI_FAMILY, size=-14, weight='bold')
        self.number_font = tkfont.Font(family=theme.num_family(), size=-15, weight='bold', slant='italic')
        self.branch_font = tkfont.Font(family=theme.UI_FAMILY, size=-14, weight='bold')
        self.bind('<Configure>', lambda _: self.draw())

    def update_state(self, state):
        now = time.monotonic()
        for pool, trail in self.trails.items():
            if self.monitoring and state.get('active', True):
                trail.update(state[pool], state[pool+'_reference'], now)
            else:
                trail.reset(state[pool], state[pool+'_reference'], now)
        preview = state.get('forecast', {})
        if preview.get('branches'):
            identity = (preview.get('phase'), preview.get('progress_order'), preview.get('order'),
                        preview.get('pattern'), preview.get('gauge_index'))
            if self.wheel_identity is not None and identity != self.wheel_identity and self.monitoring:
                self.roll_started = now
                if self.wheel_timer is None:
                    self.wheel_timer = self.after(20, self.rotate)
            self.wheel_identity = identity
        self.state = dict(state)
        self.sync_trail()
        self.sync_flash()
        self.draw()

    def aliases(self):
        return (self.state or {}).get('names') or [dict(kind='internal', name=(self.state or {}).get('name', '未命名敌人'))]

    def click(self, event):
        if event.y <= 46:
            options = self.aliases()
            index = next((i for i, n in enumerate(options) if n['kind'] == self.name_kind), -1)
            self.name_kind = options[(index+1) % len(options)]['kind']
            self.draw()
        elif event.y >= self.footer_y-12 and self.show_details and self.state:
            self.show_details(self.number, self.state)

    def set_monitoring(self, enabled):
        if self.monitoring != enabled:
            self.monitoring = enabled
            if not enabled and self.wheel_timer is not None:
                self.after_cancel(self.wheel_timer)
                self.wheel_timer = None
                self.roll_started = 0
            if not enabled and self.state:
                for pool, trail in self.trails.items():
                    trail.reset(self.state[pool], self.state[pool+'_reference'], time.monotonic())
            self.sync_trail()
            self.sync_flash()
            self.draw()

    def sync_flash(self):
        state = self.state or {}
        enabled = self.monitoring and state.get('active', True) and state.get('hp', 0) > 0 and state.get('forecast', {}).get('blink')
        if enabled and self.timer is None:
            self.timer = self.after(750, self.tick)
        elif not enabled and self.timer is not None:
            self.after_cancel(self.timer)
            self.timer = None
            self.flash = True

    def tick(self):
        self.timer = None
        self.flash = not self.flash
        self.sync_flash()
        self.draw()

    def sync_trail(self):
        active = self.monitoring and any(t.active(time.monotonic()) for t in self.trails.values())
        if active and self.trail_timer is None:
            self.trail_timer = self.after(33, self.animate_trail)
        elif not active and self.trail_timer is not None:
            self.after_cancel(self.trail_timer)
            self.trail_timer = None

    def animate_trail(self):
        self.trail_timer = None
        self.draw()
        self.sync_trail()

    def rotate(self):
        self.wheel_timer = None
        self.draw()
        if self.monitoring and time.monotonic()-self.roll_started < 0.22:
            self.wheel_timer = self.after(20, self.rotate)

    def on_destroy(self, event):
        if event.widget is self and self.wheel_timer is not None:
            self.after_cancel(self.wheel_timer)
            self.wheel_timer = None
        if event.widget is self and self.trail_timer is not None:
            self.after_cancel(self.trail_timer)
            self.trail_timer = None
        if event.widget is self and self.timer is not None:
            self.after_cancel(self.timer)
            self.timer = None

    # ---- drawing -----------------------------------------------------------
    def bar(self, x1, y1, x2, y2, fraction, delayed, color):
        rounded(self, x1, y1, x2, y2, (y2-y1)/2, fill=theme.BG, outline='')
        if delayed > fraction:
            rounded(self, x1, y1, x1+(x2-x1)*delayed, y2, (y2-y1)/2, fill=theme.mix(color, theme.ROSE, .55), outline='')
        if fraction:
            rounded(self, x1, y1, x1+(x2-x1)*fraction, y2, (y2-y1)/2, fill=color, outline='')

    def draw(self):
        self.delete('all')
        if not self.state:
            return
        s, w = self.state, max(120, self.winfo_width())
        preview = s.get('forecast', {})
        branches = preview.get('branches', [])
        visible = branches[:4]
        following = preview.get('future', [])[:2]
        inner = w - 56

        # Pass 1: measure the wrapped effect text so the band can size itself.
        effect_texts, effect_heights = [], []
        for branch in visible:
            effects = branch.get('effects', [])
            effect_text = '\n'.join((f'{i+1}. ' if len(effects) > 1 else '') + value
                                     for i, value in enumerate(effects))
            effect_texts.append(effect_text)
            item = self.create_text(0, 0, text=effect_text, font=self.small, width=inner, anchor='nw')
            box = self.bbox(item)
            effect_heights.append((box[3] - box[1]) if effect_text and box else 0)
            self.delete(item)
        row_heights = [40 + height + (16 if height else 0) for height in effect_heights]

        band_top = 158
        band_bottom = band_top + 34 + sum(row_heights or [46]) + 6
        following_tops = [band_bottom + 18 + 26 * index for index in range(len(following))]
        fallback_top = band_bottom + 18 + 26 * len(following)
        self.footer_y = band_bottom + 26 * len(following) + (26 if preview.get('fallback') else 0) + 26
        height = self.footer_y + 12
        if int(self.cget('height')) != height:
            self.configure(height=height)

        rounded(self, 1, 1, w - 1, height - 1, 20, fill=theme.CARD, outline=theme.LINE, tags='shell')
        departed = not s.get('active', True)
        options = self.aliases()
        name = next((n for n in options if n['kind'] == self.name_kind), options[0])
        rounded(self, 14, 12, 52, 40, 12, fill=theme.PINK_DEEP, outline='')
        self.create_text(33, 26, text=str(self.number), font=theme.num(15), fill=theme.PINK)
        title = name['name'] + (' · 已离场' if departed else '')
        while self.name_font.measure(title) > w - 92 and len(title) > 4:
            title = title[:-2] + '…'
        self.create_text(62, 19, text=title, anchor='w', fill=theme.FG, font=self.name_font)
        kind = {'cn': '中文', 'en': '国际服', 'internal': '内部名称'}.get(name['kind'], name['kind'])
        self.create_text(62, 35, text=kind + (' · 点击名称切换' if len(options) > 1 else ''),
                         anchor='w', fill=theme.MUTED, font=self.small)

        for pool, y, color in (('dp', 60, theme.CYAN), ('hp', 104, theme.GOLD)):
            change = s[pool+'_change']
            self.create_text(16, y, text=pool.upper(), anchor='w', fill=color, font=theme.ui(11, 'bold'))
            if change:
                self.create_text(48, y, text=f'{change:+,}', anchor='w',
                                 fill=theme.ROSE if change < 0 else theme.MINT, font=self.small)
            self.create_text(w - 18, y, text=f'{s[pool]:,}', anchor='e', fill=theme.FG,
                             font=self.number_font)
            fraction = min(1, s[pool]/max(1, s[pool+'_reference']))
            delayed = min(1, self.trails[pool].display(time.monotonic()) / max(1, s[pool+'_reference']))
            self.bar(16, y+13, w-18, y+24, fraction, delayed, theme.bar_tint(color))

        text = preview.get('text', '行动预告未取得')
        if departed:
            text = '已离场'
        elif not self.monitoring and preview.get('blink'):
            text = '采样已暂停 · ' + text
        flashing = self.timer is not None and self.monitoring and self.flash
        prior = f'{preview.get("phase", "").upper()} · 已推进至规则 {preview.get("progress_order", "—")}'
        if preview.get('previous'):
            prior = '刚执行 · ' + ' → '.join(preview['previous'])
        from .shield_layers import shield_text
        shield=shield_text(s.get('enemy_progress',{}).get('shield'))
        if shield:prior=shield
        while self.font.measure(prior) > w - 36 and len(prior) > 5:
            prior = prior[:-2]+'…'
        self.create_text(16, 140, text=prior, anchor='w', fill=theme.MUTED, font=self.small)

        band_fill = theme.GOLD_DEEP if flashing else theme.SURFACE
        band_line = theme.mix(theme.GOLD_DEEP, theme.GOLD, .35) if flashing else theme.LINE
        band = rounded(self, 10, band_top, w-10, band_bottom, 16, fill=band_fill, outline=band_line)
        self.tag_raise(band, 'shell')
        caption = '恢复后候选' if preview.get('down', 0) > 0 else '下一次行动'
        if not self.monitoring:
            caption += ' · 采样未更新'
        self.create_text(22, band_top+13, text=caption, anchor='w',
                         fill=theme.mix(theme.GOLD, theme.FG, .2), font=self.small)

        shift = max(0, 1-(time.monotonic()-self.roll_started)/0.22)*10
        colors = [theme.GOLD, theme.CYAN, theme.PINK, theme.LAVENDER]
        if not visible:
            visible = [dict(skills=[text], status='unknown', share=None, weight=None)]
        top = band_top + 34
        for index, branch in enumerate(visible):
            row_height = row_heights[index] if index < len(row_heights) else 46
            titles = branch['skills']
            content = '  ·  '.join(f'{i+1} {title}' for i, title in enumerate(titles)) if len(titles)>1 else titles[0]
            item = self.create_text(22, top+shift, text=content, width=inner, anchor='nw',
                fill=colors[index], font=self.branch_font, tags='forecast')
            while self.bbox(item)[3] > top+26+shift and len(content) > 6:
                content = content[:-2]+'…'
                self.itemconfigure(item, text=content)
            if index < len(effect_texts) and effect_texts[index]:
                self.create_text(22, top+24+shift, text=effect_texts[index], width=inner, anchor='nw',
                                 fill=theme.mix(theme.DIM, theme.FG, .25), font=self.small, tags='skill_effects')
            if branch.get('share') is not None and len(branches)>1:
                y = top+row_height-12+shift
                self.create_line(22, y, 22+(w-160)*branch['share'], y, fill=colors[index],
                                 width=3, capstyle='round')
                self.create_text(w-22, y, text=f'{branch["share"]:.0%} 权重', anchor='e',
                                 fill=colors[index], font=self.small)
            elif branch.get('weight') is not None:
                label = ('观测推演' if branch.get('observed') else '条件已满足') if branch['status']=='matched' else '条件待确认'
                self.create_text(22, top+row_height-12+shift,
                                 text=label + (f' · 权重 {branch["weight"]}' if len(branches)>1 else ''),
                                 anchor='w', fill=theme.MUTED, font=self.small)
            top += row_height

        for row, y in zip(following, following_tops):
            line = '↓ 推演 ' + str(row['order']) + ' · ' + ' / '.join(' → '.join(b['skills']) for b in row['branches'])
            while self.font.measure(line) > w - 36 and len(line) > 5:
                line = line[:-2]+'…'
            self.create_text(16, y, text=line, anchor='w', fill=theme.MUTED, font=self.small)
        if preview.get('fallback'):
            self.create_text(16, fallback_top, text='↳ 条件不成立时有后续分支 · 见详情', anchor='w',
                             fill=theme.mix(theme.DIM, theme.FG, .2), font=self.small)
        footer = '名称、状态与技能效果 ›'
        if len(branches) > 4:
            footer = f'另 {len(branches)-4} 个分支 · ' + footer
        self.create_text(16, self.footer_y, text=footer, anchor='w', fill=theme.CYAN, font=self.small)
