"""Centered, individually styled table cells backed by a scrollable Tk canvas."""
import tkinter as tk
from tkinter import font as tkfont
from . import theme
from .history import actor_title, skill_title, beneficiary, beneficiary_title
from .turns import context_label


class BattleTable(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=theme.CARD)
        self.header = tk.Canvas(self, height=38, bg=theme.CARD_HI, highlightthickness=0)
        self.header.pack(fill='x')
        self.canvas = tk.Canvas(self, bg=theme.CARD, highlightthickness=0, takefocus=True)
        self.canvas.pack(fill='both', expand=True)
        self.widths = [215, 240, 240, 240]
        self.rows = {}
        self.selected = ()
        self.bounds = {}
        from .portraits import Portraits
        self.portraits = Portraits(self)
        self.show_portraits = True
        self.actor_font = tkfont.Font(family='Microsoft YaHei UI', size=-12)
        self.skill_font = tkfont.Font(family='Microsoft YaHei UI', size=-16, weight='bold')
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
        current = self.canvas.find_withtag('current')
        if current and 'portrait_switch' in self.canvas.gettags(current[0]):
            self.toggle_portraits()
            return
        y = self.canvas.canvasy(event.y)
        for key, (top, bottom) in self.bounds.items():
            if top <= y < bottom:
                self.selection_set(key)
                self.canvas.focus_set()
                break

    def toggle_portraits(self):
        self.show_portraits = not self.show_portraits
        self.redraw()

    def draw_event(self, cx, y, width, event):
        photo = self.portraits.get(event.get('style_label')) if self.show_portraits else None
        target = beneficiary(event)
        ids = []
        if photo:
            skill_width = min(self.skill_font.measure(skill_title(event))+4, max(60, width-(154 if target else 84)))
            total_width = 44+14+skill_width+(78 if target else 0)
            left = cx-total_width/2
            ids.append(self.canvas.create_image(left+22, 0, image=photo, tags='portrait_switch'))
            ids.append(self.canvas.create_text(left+58+skill_width/2, 0, text=skill_title(event),
                width=skill_width, font=self.skill_font, fill=theme.GOLD, justify='center'))
            if target:
                right = left+total_width-22
                target_photo = self.portraits.get(target.get('style_label'))
                if target_photo:
                    ids.append(self.canvas.create_image(right, 0, image=target_photo, tags='portrait_switch'))
                else:
                    ids.append(self.canvas.create_text(right, 0, text=target.get('name') or '友方',
                        width=44, font=self.actor_font, fill=theme.CYAN, justify='center', tags='portrait_switch'))
                ids.append(self.canvas.create_text(right-38, 0, text='→', font=self.actor_font, fill=theme.CYAN))
            height = max(64, max(self.canvas.bbox(item)[3]-self.canvas.bbox(item)[1] for item in ids)+20)
            for item in ids:
                self.canvas.move(item, 0, y+height/2)
            return ids, height
        texts = [(self.fit_title(actor_title(event), width-28), self.actor_font, theme.DIM),
                 (skill_title(event), self.skill_font, theme.GOLD)]
        if target:
            texts.append(('→ '+beneficiary_title(event), self.actor_font, theme.CYAN))
        height = 0
        for index, (text, font, color) in enumerate(texts):
            item = self.canvas.create_text(cx, y+height, text=text, font=font, fill=color,
                width=width-28, justify='center', anchor='n', tags='portrait_switch' if index == 0 else ())
            height += self.canvas.bbox(item)[3]-self.canvas.bbox(item)[1]+6
            ids.append(item)
        return ids, height

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
                                    text=title, fill=theme.FG, font=self.skill_font)
        y = 0
        for number, (key, row) in enumerate(self.rows.items()):
            if (row['group'] or {}).get('kind') == 'instant':
                items, content_height = self.draw_event((edges[1]+available)/2, y+10,
                    available-edges[1], row['events'][0])
                height = max(84, content_height+20)
                rect = self.canvas.create_rectangle(0, y, available, y+height,
                    fill=theme.mix(theme.CARD, theme.PINK, .18) if key in self.selected else theme.mix(theme.CARD, theme.BG, .35), outline=theme.LINE)
                self.canvas.tag_lower(rect)
                self.canvas.create_text(edges[1]/2, y+height/2, text=context_label(row['group']),
                    width=edges[1]-20, font=self.badge_font, fill=theme.GOLD, justify='center')
                self.bounds[key] = (y, y+height)
                y += height
                continue
            blocks = []
            content_height = 0
            for index, slot in enumerate(row['slots'], 1):
                cx = (edges[index]+edges[index+1])/2
                ids, height = [], 0
                for event in slot:
                    items, block_height = self.draw_event(cx, y+height, widths[index], event)
                    ids.extend(items)
                    height += block_height
                if not slot:
                    ids.append(self.canvas.create_text(cx, y, text='/', font=self.actor_font, fill=theme.MUTED, anchor='n'))
                    height = 24
                blocks.append((ids, height))
                content_height = max(content_height, height)
            group = row['group'] or {}
            badges = [(f'Turn {group["turn"]}', theme.CYAN, theme.CYAN_DEEP)] if group.get('turn') else [('回合待确认', theme.LAVENDER, theme.LAVENDER_DEEP)]
            if group.get('od'):
                badges.append((f'Bonus {group["bonus"]}', theme.GOLD, theme.GOLD_DEEP))
            if group.get('additional') or group.get('extra'):
                badges.append(('Extra', theme.PINK, theme.PINK_DEEP))
            if group.get('kind') == 'instant':
                badges.append(('小按钮', theme.GOLD, theme.GOLD_DEEP))
            body_height = max(82, content_height+22)
            height = body_height + (24 if row['unplaced'] else 0)
            fill = theme.mix(theme.CARD, theme.PINK, .18) if key in self.selected else (theme.CARD if number % 2 == 0 else theme.mix(theme.CARD, theme.BG, .35))
            rect = self.canvas.create_rectangle(0, y, available, y+height, fill=fill, outline=theme.LINE)
            self.canvas.tag_lower(rect)
            for ids, block_height in blocks:
                for item in ids:
                    self.canvas.move(item, 0, (body_height-block_height)/2)
            segments = []
            for text, color, _ in badges:
                if segments:
                    segments.append((' / ', theme.DIM))
                segments.append((text, color))
            x = (edges[1] - sum(self.badge_font.measure(t) for t, _ in segments))/2
            for text, color in segments:
                self.canvas.create_text(x, y+body_height/2, text=text, fill=color,
                                        font=self.badge_font, anchor='w', tags=('context',))
                x += self.badge_font.measure(text)
            for edge in edges[1:-1]:
                self.canvas.create_line(edge, y+10, edge, y+body_height-10, fill=theme.LINE_SOFT)
            if row['unplaced']:
                self.canvas.create_text(available/2, y+body_height+10,
                    text=' / '.join(skill_title(e) for e in row['unplaced']) if group.get('kind') == 'instant' else f'{len(row["unplaced"])} 条行动位置未确认 · 展开详情查看', fill=theme.ROSE, font=self.skill_font)
            self.bounds[key] = (y, y+height)
            y += height
        self.canvas.configure(scrollregion=(0, 0, available, y))
        self.header.configure(scrollregion=(0, 0, available, 38))
        self.header.xview_moveto(self.canvas.xview()[0])
