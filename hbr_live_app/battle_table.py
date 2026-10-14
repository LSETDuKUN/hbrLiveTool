"""Centered, individually styled table cells backed by a scrollable Tk canvas."""
import tkinter as tk
from tkinter import font as tkfont
from .history import actor_title


class BattleTable(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg='#302b46')
        self.header = tk.Canvas(self, height=38, bg='#403650', highlightthickness=0)
        self.header.pack(fill='x')
        self.canvas = tk.Canvas(self, bg='#302b46', highlightthickness=0, takefocus=True)
        self.canvas.pack(fill='both', expand=True)
        self.widths = [215, 240, 240, 240]
        self.rows = {}
        self.selected = ()
        self.bounds = {}
        self.actor_font = tkfont.Font(family='Microsoft YaHei UI', size=-15, weight='bold')
        self.skill_font = tkfont.Font(family='Microsoft YaHei UI', size=-13)
        self.badge_font = tkfont.Font(family='Segoe UI', size=-13, weight='bold')
        self.canvas.bind('<Configure>', lambda e: self.redraw())
        self.canvas.bind('<Button-1>', self.click)
        self.canvas.bind('<Double-1>', lambda e: self.event_generate('<<RowDetails>>'))
        self.canvas.bind('<MouseWheel>', lambda e: self.canvas.yview_scroll(-int(e.delta / 120), 'units'))
        self.canvas.bind('<Up>', lambda e: self.step(-1))
        self.canvas.bind('<Down>', lambda e: self.step(1))

    def configure(self, cnf=None, **kwargs):
        for key in ('yscrollcommand', 'xscrollcommand'):
            if key in kwargs:
                self.canvas.configure(**{key: kwargs.pop(key)})
        if cnf or kwargs:
            super().configure(cnf, **kwargs)

    def xview(self, *args):
        result = self.canvas.xview(*args)
        self.header.xview_moveto(self.canvas.xview()[0])
        return result

    def yview(self, *args):
        return self.canvas.yview(*args)

    def get_children(self):
        return tuple(self.rows)

    def delete(self, *keys):
        for key in keys:
            self.rows.pop(key, None)
        self.selected = ()
        self.redraw()

    def item(self, key, option=None):
        data = {'values': self.rows[key]['values']}
        return data.get(option) if option else data

    def selection(self):
        return self.selected

    def selection_set(self, key):
        self.selected = (key,) if key in self.rows else ()
        self.redraw()
        self.event_generate('<<TreeviewSelect>>')

    def set_rows(self, rows):
        new = [key for key in rows if key not in self.rows]
        old_selected = self.rows.get(self.selected[0]) if self.selected else None
        self.rows = rows
        if self.selected and self.selected[0] not in rows:
            # A previously unknown event may have acquired its proper batch.
            ids = {e['event_id'] for e in old_selected['events']} if old_selected else set()
            match = next((key for key, row in rows.items() if any(e['event_id'] in ids for e in row['events'])), None)
            self.selected = (match,) if match else ()
        if not self.selected and rows:
            self.selected = (next(iter(rows)),)
        self.redraw()
        if new:
            self.canvas.yview_moveto(1)

    def click(self, event):
        y = self.canvas.canvasy(event.y)
        for key, (top, bottom) in self.bounds.items():
            if top <= y < bottom:
                self.selection_set(key)
                self.canvas.focus_set()
                break

    def step(self, direction):
        keys = list(self.rows)
        if not keys:
            return
        index = keys.index(self.selected[0]) if self.selected else 0
        key = keys[max(0, min(len(keys) - 1, index + direction))]
        self.selection_set(key)
        self.canvas.yview_moveto(self.bounds[key][0] / max(1, float(self.canvas.bbox('all')[3])))

    def fit_title(self, text, width):
        if self.actor_font.measure(text) <= width:
            return text
        while text and self.actor_font.measure(text + '…') > width:
            text = text[:-1]
        return text + '…'

    def redraw(self):
        self.canvas.delete('all')
        self.header.delete('all')
        self.bounds = {}
        available = max(sum(self.widths), self.canvas.winfo_width())
        widths = [self.widths[0]] + [(available-self.widths[0])/3]*3
        edges = [0]
        for w in widths:
            edges.append(edges[-1]+w)
        for index, title in enumerate(('回合', '前排 · 左', '前排 · 中', '前排 · 右')):
            self.header.create_text((edges[index]+edges[index+1])/2, 19,
                                    text=title, fill='#ded1ed', font=self.actor_font)
        y = 0
        for number, (key, row) in enumerate(self.rows.items()):
            blocks = []
            content_height = 0
            for index, slot in enumerate(row['slots'], 1):
                cx = (edges[index]+edges[index+1])/2
                texts = []
                for event in slot:
                    texts.extend(((self.fit_title(actor_title(event), widths[index]-28), self.actor_font, '#ffe4af'),
                                  (event['skill'], self.skill_font, '#c6bef4')))
                if not texts:
                    texts = [('/', self.actor_font, '#9388a8')]
                ids, height = [], 0
                for text, font, color in texts:
                    item = self.canvas.create_text(cx, y+height, text=text, font=font, fill=color,
                                width=widths[index]-28, justify='center', anchor='n')
                    box = self.canvas.bbox(item)
                    height += box[3]-box[1]+6
                    ids.append(item)
                blocks.append((ids, height))
                content_height = max(content_height, height)
            group = row['group'] or {}
            badges = [(f'Turn {group["turn"]}', '#8fe5ed', '#2d4b55')] if group else [('回合待确认', '#d7c8e8', '#4a3b57')]
            if group.get('od'):
                badges.append((f'Bonus {group["bonus"]}', '#ffdc9d', '#514432'))
            if group.get('additional') or group.get('extra'):
                badges.append(('Extra', '#ffb4d7', '#513449'))
            body_height = max(82, content_height+22)
            height = body_height + (24 if row['unplaced'] else 0)
            fill = '#514360' if key in self.selected else ('#302b46' if number % 2 == 0 else '#352e4b')
            rect = self.canvas.create_rectangle(0, y, available, y+height, fill=fill, outline='#51475f')
            self.canvas.tag_lower(rect)
            for ids, block_height in blocks:
                for item in ids:
                    self.canvas.move(item, 0, (body_height-block_height)/2)
            segments = []
            for text, color, _ in badges:
                if segments:
                    segments.append((' / ', '#bdb1d4'))
                segments.append((text, color))
            x = (edges[1] - sum(self.badge_font.measure(t) for t, _ in segments))/2
            for text, color in segments:
                self.canvas.create_text(x, y+body_height/2, text=text, fill=color,
                                        font=self.badge_font, anchor='w', tags=('context',))
                x += self.badge_font.measure(text)
            for edge in edges[1:-1]:
                self.canvas.create_line(edge, y+10, edge, y+body_height-10, fill='#554963')
            if row['unplaced']:
                self.canvas.create_text(available/2, y+body_height+10,
                    text=f'{len(row["unplaced"])} 条行动位置未确认 · 展开详情查看', fill='#e1bb94', font=self.skill_font)
            self.bounds[key] = (y, y+height)
            y += height
        self.canvas.configure(scrollregion=(0, 0, available, y))
        self.header.configure(scrollregion=(0, 0, available, 38))
        self.header.xview_moveto(self.canvas.xview()[0])
