"""Separate compact gauges for every enemy, with stable session numbers."""
import tkinter as tk
from tkinter import font as tkfont
from .components import rounded


class EnemyCard(tk.Canvas):
    def __init__(self, parent, number, show_details=None):
        super().__init__(parent, height=190, bg='#201d32', highlightthickness=0)
        self.number = number
        self.state = None
        self.show_details = show_details
        self.name_kind = 'cn'
        self.monitoring = False
        self.flash = True
        self.timer = None
        self.bind('<Button-1>', self.click)
        self.bind('<Destroy>', self.on_destroy)
        self.font = tkfont.Font(family='Microsoft YaHei UI', size=-12)
        self.bind('<Configure>', lambda _: self.draw())

    def update_state(self, state):
        self.state = dict(state)
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
        elif event.y >= 164 and self.show_details and self.state:
            self.show_details(self.number, self.state)

    def set_monitoring(self, enabled):
        if self.monitoring != enabled:
            self.monitoring = enabled
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
        self.draw()
        self.sync_flash()

    def on_destroy(self, event):
        if event.widget is self and self.timer is not None:
            self.after_cancel(self.timer)
            self.timer = None

    def draw(self):
        self.delete('all')
        if not self.state:
            return
        s, w = self.state, max(100, self.winfo_width())
        rounded(self, 1, 1, w-1, 189, 16, fill='#302b46', outline='#50415f')
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
            if fraction:
                rounded(self, 12, y+10, 12+(w-24)*fraction, y+21, 5, fill=color, outline='')

        preview = s.get('forecast', {})
        text = preview.get('text', '行动预告未取得')
        if not s.get('active', True):
            text = '已离场'
        elif not self.monitoring and preview.get('blink'):
            text = '采样已暂停 · ' + text
        color = '#ffd398' if self.flash else '#bdb1d4'
        item = self.create_text(12, 123, text=text, width=w-24, anchor='nw',
                               fill=color, font=self.font, tags='forecast')
        # Full preview and all rules remain available in the detail window.
        while self.bbox(item)[3] > 163 and len(text) > 6:
            text = text[:-2] + '…'
            self.itemconfigure(item, text=text)
        self.create_text(12, 177, text='名称与行动规则 ›', anchor='w', fill='#83e5ed', font=self.font)
