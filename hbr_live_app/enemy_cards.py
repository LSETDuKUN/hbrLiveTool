"""Separate compact gauges for every enemy, with stable session numbers."""
import tkinter as tk
import time
from .gauge_trail import GaugeTrail
from tkinter import font as tkfont
from .components import rounded


class EnemyCard(tk.Canvas):
    def __init__(self, parent, number, show_details=None):
        super().__init__(parent, height=232, bg='#201d32', highlightthickness=0)
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
        self.font = tkfont.Font(family='Microsoft YaHei UI', size=-12)
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

    def draw(self):
        self.delete('all')
        if not self.state:
            return
        s, w = self.state, max(100, self.winfo_width())
        preview = s.get('forecast', {})
        branches = preview.get('branches', [])
        visible = branches[:4]
        following = preview.get('future', [])[:2]
        effect_texts, branch_heights = [], []
        for branch in visible:
            effects = branch.get('effects', [])
            effect_text = '\n'.join((f'{i+1}. ' if len(effects)>1 else '')+value for i, value in enumerate(effects))
            effect_texts.append(effect_text)
            item = self.create_text(0, 0, text=effect_text, font=self.font, width=w-36, anchor='nw')
            box = self.bbox(item)
            branch_heights.append(58+(box[3]-box[1]+8 if effect_text and box else 0))
            self.delete(item)
        band_bottom = 169 + (sum(branch_heights) or 58)
        status_text = ''
        self.footer_y = band_bottom + 28*len(following) + (28 if preview.get('fallback') else 0) + 25
        if status_text:
            self.footer_y += 25
        height = self.footer_y+14
        if int(self.cget('height')) != height:
            self.configure(height=height)
        rounded(self, 1, 1, w-1, height-1, 16, fill='#302b46', outline='#50415f')
        departed = '（已离场）' if not s.get('active', True) else ''
        options = self.aliases()
        name = next((n for n in options if n['kind'] == self.name_kind), options[0])
        title = f'敌{self.number}{departed} · {name["name"]}'
        while self.font.measure(title) > w-24 and len(title) > 8:
            title = title[:-2] + '…'
        self.create_text(12, 16, text=title, anchor='w', fill='#f5aacb', font=self.font)
        kind = {'cn': '中文', 'en': '国际服', 'internal': '内部名称'}.get(name['kind'], name['kind'])
        self.create_text(12, 36, text=kind + (' · 点击名称切换' if len(options) > 1 else ''),
                         anchor='w', fill='#bdb1d4', font=self.font)
        for pool, y, color in [('dp', 57, '#83e5ed'), ('hp', 90, '#ffd398')]:
            change = s[pool+'_change']
            left = pool.upper() + (f'  {change:+,}' if change else '')
            self.create_text(12, y, text=left, anchor='w', fill=color, font=self.font)
            self.create_text(w-12, y, text=f'{s[pool]:,}', anchor='e', fill='#f7f0ff',
                             font=('Segoe UI', -14, 'bold italic'))
            rounded(self, 12, y+10, w-12, y+21, 5, fill='#201d32', outline='')
            fraction = min(1, s[pool]/max(1, s[pool+'_reference']))
            trail = self.trails[pool]
            delayed = min(1, trail.display(time.monotonic()) / max(1, s[pool+'_reference']))
            if delayed > fraction:
                rounded(self, 12, y+10, 12+(w-24)*delayed, y+21, 5, fill='#e8a5ae', outline='')
            if fraction:
                rounded(self, 12, y+10, 12+(w-24)*fraction, y+21, 5, fill=color, outline='')

        preview = s.get('forecast', {})
        text = preview.get('text', '行动预告未取得')
        if not s.get('active', True):
            text = '已离场'
        elif not self.monitoring and preview.get('blink'):
            text = '采样已暂停 · ' + text
        flashing = self.timer is not None and self.monitoring
        background = '#655036' if flashing and self.flash else '#3e354e'
        prior = f'{preview.get("phase", "").upper()} · 已推进至规则 {preview.get("progress_order", "—")}'
        if preview.get('previous'):
            prior = '刚执行 · ' + ' → '.join(preview['previous'])
        while self.font.measure(prior) > w-32 and len(prior)>8:
            prior = prior[:-2]+'…'
        self.create_text(16, 127, text=prior, anchor='w', fill='#a397b4', font=self.font)
        rounded(self, 8, 140, w-8, band_bottom, 10, fill=background, outline='#817051')
        caption = '恢复后候选' if preview.get('down', 0)>0 else '下一次行动'
        if not self.monitoring:
            caption += ' · 采样未更新'
        self.create_text(18, 153, text=caption, anchor='w', fill='#d8c8ad', font=self.font)
        shift = max(0, 1-(time.monotonic()-self.roll_started)/0.22)*10
        colors = ['#ffe4af', '#a9dbea', '#eab5d6', '#c5c1fa']
        if not visible:
            visible = [dict(skills=[text], status='unknown', share=None, weight=None)]
        top = 169
        for index, branch in enumerate(visible):
            row_height = branch_heights[index] if index < len(branch_heights) else 58
            titles = branch['skills']
            content = '  ·  '.join(f'{i+1} {title}' for i, title in enumerate(titles)) if len(titles)>1 else titles[0]
            item = self.create_text(18, top+shift, text=content, width=w-36, anchor='nw',
                fill=colors[index], font=('Microsoft YaHei UI', -15, 'bold'), tags='forecast')
            while self.bbox(item)[3] > top+36+shift and len(content)>6:
                content = content[:-2]+'…'
                self.itemconfigure(item, text=content)
            if index < len(effect_texts) and effect_texts[index]:
                self.create_text(18, top+40, text=effect_texts[index], width=w-36, anchor='nw',
                                 fill='#d0c5dd', font=self.font, tags='skill_effects')
            if branch.get('share') is not None and len(branches)>1:
                self.create_line(18, top+row_height-14, 18+(w-135)*branch['share'], top+row_height-14, fill=colors[index], width=4)
                self.create_text(w-18, top+row_height-14, text=f'{branch["share"]:.0%} 权重', anchor='e', fill=colors[index], font=self.font)
            elif branch.get('weight') is not None:
                label = ('观测推演' if branch.get('observed') else '条件已满足') if branch['status']=='matched' else '条件待确认'
                self.create_text(18, top+row_height-14, text=label + (f' · 权重 {branch["weight"]}' if len(branches)>1 else ''),
                                 anchor='w', fill='#c0b3ca', font=self.font)
            top += row_height
        below = band_bottom+15
        for row in following:
            title = ' / '.join(' → '.join(b['skills']) for b in row['branches'])
            text = f'↓ 推演 {row["order"]} · {title}'
            while self.font.measure(text)>w-32 and len(text)>8:
                text=text[:-2]+'…'
            self.create_text(16, below, text=text, anchor='w', fill='#a397b4', font=self.font)
            below += 28
        if preview.get('fallback'):
            self.create_text(16, below, text='↳ 条件不成立时有后续分支 · 见详情', anchor='w', fill='#c0b3ca', font=self.font)
        if status_text:
            while self.font.measure(status_text)>w-32 and len(status_text)>8:
                status_text=status_text[:-2]+'…'
            self.create_text(16, self.footer_y-25, text=status_text, anchor='w', fill='#eab5d6', font=self.font)
        footer = '名称、状态与技能效果 ›'
        if len(branches)>4:
            footer = f'另 {len(branches)-4} 个分支 · '+footer
        self.create_text(12, self.footer_y, text=footer, anchor='w', fill='#83e5ed', font=self.font)
