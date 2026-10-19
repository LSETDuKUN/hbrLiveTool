"""Animated displays and a travelling border. Presentation only."""
import tkinter as tk
from tkinter import font as tkfont

from . import theme


def outline_points(x1, y1, x2, y2, radius):
    """Same silhouette as components.rounded(), as a closed point list."""
    r = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
            x1 + r, y1, x2 - r, y1]


class NumberDisplay(tk.Canvas):
    """Large number with a highlight that sweeps across the digits."""

    def __init__(self, master, size=46, color=None, height=None, **kwargs):
        self._text = '0'
        self._color = color or theme.PINK
        self._size = size
        self._font = tkfont.Font(font=theme.num(size))
        self._phase = 0.0
        self._items = []
        self._spacing = ()
        super().__init__(master, bg=master.cget('bg'), highlightthickness=0, bd=0,
                         height=height or int(size * theme.SCALE * 1.35), **kwargs)
        self.bind('<Configure>', lambda e: self.redraw())

    # -- compatibility with the label it replaces -------------------------
    def cget(self, key):
        if key == 'text':
            return self._text
        return tk.Canvas.cget(self, key)

    def configure(self, cnf=None, **kwargs):
        if 'text' in kwargs:
            self.set_text(kwargs.pop('text'))
        if 'font' in kwargs:
            self.set_font(kwargs.pop('font'))
        return super().configure(cnf, **kwargs)

    config = configure

    def set_font(self, font):
        self._font = tkfont.Font(font=font)
        self._size = abs(int(font[1])) if isinstance(font, tuple) and len(font) > 1 else self._size
        self.configure(height=int(self._font.metrics('linespace') * 1.25))
        self.redraw()

    def set_text(self, text):
        text = str(text)
        if text == self._text and self._items:
            return
        self._text = text
        self.redraw()

    # -- drawing -----------------------------------------------------------
    def _base_color(self):
        return self._color

    def redraw(self):
        self.delete('digits')
        self._items = []
        text = self._text
        if len(self._spacing) != len(text):
            self._spacing = tuple(self._font.measure(char) for char in text)
        total = sum(self._spacing)
        width = self.winfo_width()
        height = self.winfo_height() or self._font.metrics('linespace')
        x = 2
        for char, advance in zip(text, self._spacing):
            item = self.create_text(x, height / 2, text=char, anchor='w',
                                    font=self._font, fill=self._base_color(), tags='digits')
            self._items.append(item)
            x += advance
        self.paint()

    def paint(self):
        base = self._base_color()
        width = max(1, len(self._items))
        cycle = self._phase % 1.0
        for index, item in enumerate(self._items):
            frac = (index + 0.5) / width
            distance = abs(frac - cycle)
            distance = min(distance, 1 - distance)
            glow = max(0.0, 1 - distance / 0.28)
            fill = theme.mix(base, '#ffffff', .60 * glow) if glow > 0.01 else base
            self.itemconfigure(item, fill=fill)

    def tick(self):
        if not self._items:
            return
        self._phase += 0.0125
        self.paint()


class DeltaDisplay(NumberDisplay):
    """Current-command damage: running total plus a smaller, fainter delta."""

    def __init__(self, master, size=30, color=None, **kwargs):
        self._main = '0'
        self._delta = ''
        self._delta_alpha = 0.0
        self._flash = 0.0
        self._delta_items = []
        super().__init__(master, size=size, color=color, **kwargs)

    def cget(self, key):
        if key == 'text':
            return f'{self._main} + {self._delta}' if self._delta else self._main
        return tk.Canvas.cget(self, key)

    def set_text(self, text):
        text = str(text)
        if ' + ' in text:
            main, delta = text.split(' + ', 1)
            if delta != self._delta:
                self._delta_alpha = 0.0
                self._flash = 1.0
            self._main, self._delta = main, delta
        else:
            if self._delta:
                self._flash = 0.9
            self._main, self._delta = text, ''
            self._delta_alpha = 0.0
        self.redraw()

    def redraw(self):
        self.delete('digits')
        self._items = []
        self._delta_items = []
        main_font = self._font
        small_size = max(9, int(self._size * 0.6 * theme.SCALE))
        small = tkfont.Font(family=main_font.actual('family'), size=-small_size)
        main_space = tuple(main_font.measure(char) for char in self._main)
        delta_text = ('+ ' + self._delta) if self._delta else ''
        gap = small_size * 0.45
        delta_space = tuple(small.measure(char) for char in delta_text)
        total = sum(main_space) + ((gap + sum(delta_space)) if delta_text else 0)
        width = self.winfo_width()
        height = self.winfo_height() or int(self._size * theme.SCALE * 1.3)
        x = 2
        for char, advance in zip(self._main, main_space):
            self._items.append(self.create_text(x, height / 2, text=char, anchor='w',
                                                font=main_font, fill=self._base_color(),
                                                tags='digits'))
            x += advance
        if delta_text:
            self._delta_items = []
            x += gap
            for char, advance in zip(delta_text, delta_space):
                self._delta_items.append(self.create_text(x, height / 2 + 1, text=char,
                                                          anchor='w', font=small,
                                                          fill=self._base_color(), tags='digits'))
                x += advance
        self.paint()

    def paint(self):
        super().paint()
        if self._flash > 0 and self._items:
            for item in self._items:
                current = self.itemcget(item, 'fill')
                self.itemconfigure(item, fill=theme.mix(current, '#ffffff', .45 * self._flash))
        if not self._delta_items:
            return
        alpha = max(0.0, min(1.0, self._delta_alpha))
        soft = theme.mix(theme.mix(theme.BG, self._color, .25), self._color, alpha)
        for item in self._delta_items:
            self.itemconfigure(item, fill=soft)

    def tick(self):
        dirty = False
        if self._delta and self._delta_alpha < 1.0:
            self._delta_alpha = min(1.0, self._delta_alpha + 0.16)
            dirty = True
        elif not self._delta and self._delta_alpha > 0.0:
            self._delta_alpha = max(0.0, self._delta_alpha - 0.16)
            dirty = True
        if self._flash > 0:
            self._flash = max(0.0, self._flash - 0.09)
            dirty = True
        if dirty:
            self.paint()
            return
        super().tick()


def rounded_path(x1, y1, x2, y2, radius, step=3):
    """Dense point list around a rounded rectangle, for a travelling light."""
    import math
    r = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    points = []

    def arc(cx, cy, start_angle):
        span = 90
        count = max(2, int((math.pi * r / 2) / max(1, step)))
        for index in range(count + 1):
            angle = math.radians(start_angle + span * index / count)
            points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

    def line(ax, ay, bx, by):
        count = max(1, int(math.hypot(bx - ax, by - ay) / max(1, step)))
        for index in range(count + 1):
            points.append((ax + (bx - ax) * index / count, ay + (by - ay) * index / count))

    arc(x1 + r, y1 + r, 180)
    line(x1 + r, y1, x2 - r, y1)
    arc(x2 - r, y1 + r, 270)
    line(x2, y1 + r, x2, y2 - r)
    arc(x2 - r, y2 - r, 0)
    line(x2 - r, y2, x1 + r, y2)
    arc(x1 + r, y2 - r, 90)
    line(x1, y2 - r, x1, y1 + r)
    return points


class GlowBorder:
    """A short bright segment that travels around a RoundedCard outline."""

    def __init__(self, card, color=None, width=3, span=64):
        self.card = card
        self.color = color or theme.PINK
        self.width = width
        self.span = span
        self.phase = 0
        self.item = None
        self.path = []
        self.active = False
        self._size = (0, 0)

    def show(self, active):
        self.active = active
        if not active and self.item is not None:
            try:
                self.card.delete(self.item)
            except tk.TclError:
                pass
            self.item = None
        if active:
            self.update()

    def _rebuild(self, width, height):
        self.path = rounded_path(2, 2, width - 2, height - 2, self.card.radius, step=7)
        self._size = (width, height)
        self.count = max(2, len(self.path) // max(1, self.span // 3))

    def update(self):
        if not self.active:
            return
        card = self.card
        try:
            width = max(40, card.winfo_width())
            height = max(20, card.winfo_height())
        except tk.TclError:
            return
        if not self.path or (width, height) != self._size:
            self._rebuild(width, height)
        total = len(self.path)
        keep = max(2, self.count)
        start = self.phase % total
        coords = []
        for offset in range(keep):
            x, y = self.path[int(start + offset) % total]
            coords.extend((x, y))
        if self.item is None:
            self.item = card.create_line(coords, width=self.width, fill=self.color,
                                         capstyle='round', joinstyle='round')
        else:
            card.coords(self.item, *coords)
            card.itemconfigure(self.item, fill=self.color)
        card.tag_raise(self.item)
        self.phase = (self.phase + 3) % total
