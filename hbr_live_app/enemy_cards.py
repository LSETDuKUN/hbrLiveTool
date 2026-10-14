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
        elif event.y >= 208 and self.show_details and self.state:
            self.show_details(self.number, self.state)

    def set_monitoring(self, enabled):
        if self.monitoring != enabled:
            self.monitoring = enabled
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

    def on_destroy(self, event):
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
        rounded(self, 1, 1, w-1, 231, 16, fill='#302b46', outline='#50415f')
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
        label, sep, skill = text.partition('：')
        caption = '行动预告' + (' · ' + label if sep else '')
        content = skill if sep else text
        flashing = self.timer is not None and self.monitoring
        background = '#655036' if flashing and self.flash else '#3e354e'
        rounded(self, 8, 119, w-8, 203, 10, fill=background, outline='')
        self.create_text(18, 133, text=caption, anchor='w', fill='#d8c8ad', font=self.font)
        item = self.create_text(18, 148, text=content, width=w-36, anchor='nw',
                               fill='#ffe4af', font=('Microsoft YaHei UI', -16, 'bold'), tags='forecast')
        # The skill stays bright while the background pulses; full text is in details.
        while self.bbox(item)[3] > 198 and len(content) > 6:
            content = content[:-2] + '…'
            self.itemconfigure(item, text=content)
        self.create_text(12, 219, text='名称、行动规则与技能效果 ›', anchor='w', fill='#83e5ed', font=self.font)
