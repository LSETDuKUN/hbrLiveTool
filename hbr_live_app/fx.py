"""Animated displays and a travelling border. Presentation only."""
import os
import tkinter as tk

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageTk

from . import theme

FONT_DIR = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')
FONT_FILES = {
    'bold': ('seguisbi.ttf', 'segoeuib.ttf', 'arialbi.ttf'),
    'normal': ('segoeuii.ttf', 'segoeui.ttf', 'ariali.ttf'),
}


def _font_path(weight='bold'):
    for name in FONT_FILES.get(weight, FONT_FILES['bold']):
        path = os.path.join(FONT_DIR, name)
        if os.path.exists(path):
            return path
    return None


def _load_font(size, weight='bold'):
    path = _font_path(weight)
    if path:
        try:
            return ImageFont.truetype(path, int(size))
        except OSError:
            pass
    return ImageFont.load_default()


def gradient_image(width, height, colors):
    """Horizontal multi-stop gradient, one pixel column at a time."""
    width = max(1, int(width))
    height = max(1, int(height))
    stops = [theme.hex_to_rgb(colour) for colour in colors]
    if len(stops) == 1:
        stops = stops * 2
    strip = Image.new('RGB', (width, 1))
    pixels = strip.load()
    span = width - 1 if width > 1 else 1
    for x in range(width):
        position = x / span * (len(stops) - 1)
        index = min(int(position), len(stops) - 2)
        blend = position - index
        a, b = stops[index], stops[index + 1]
        pixels[x, 0] = tuple(int(a[i] + (b[i] - a[i]) * blend) for i in range(3))
    return strip.resize((width, height))


class _Bitmap:
    """Shared glyph rendering for the two damage readouts."""

    weight = 'bold'
    shadow_blur = 2.4

    def _render(self, main, delta='', delta_scale=0.6):
        size = max(9, int(self._size * theme.SCALE))
        font = _load_font(size, self.weight)
        small = _load_font(max(8, int(size * delta_scale)), self.weight)
        ascent, descent = font.getmetrics()
        main_box = font.getbbox(main) if main else (0, 0, 0, 0)
        main_w = max(0, main_box[2] - main_box[0])
        gap = int(size * 0.22)
        delta_text = ('+ ' + delta) if delta else ''
        delta_box = small.getbbox(delta_text) if delta_text else (0, 0, 0, 0)
        delta_w = max(0, delta_box[2] - delta_box[0])
        pad = int(size * 0.16) + 6
        width = int(pad * 2 + main_w + (gap + delta_w if delta_text else 0))
        height = int((ascent + descent) * 1.18 + pad)
        mask = Image.new('L', (width, height), 0)
        delta_mask = Image.new('L', (width, height), 0)
        draw = ImageDraw.Draw(mask)
        base_y = pad / 2 + ascent
        draw.text((pad - main_box[0], base_y), main, font=font, fill=255, anchor='ls')
        if delta_text:
            draw = ImageDraw.Draw(delta_mask)
            draw.text((pad + main_w + gap - delta_box[0], base_y), delta_text,
                      font=small, fill=255, anchor='ls')
        canvas = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        shadow_mask = ImageChops.lighter(mask, delta_mask).filter(
            ImageFilter.GaussianBlur(self.shadow_blur))
        shadow = Image.new('RGBA', (width, height), self._shadow_rgb() + (150,))
        shadow.putalpha(shadow_mask.point(lambda value: int(value * 0.55)))
        canvas = Image.alpha_composite(canvas, shadow)
        fill = gradient_image(width, height, self._colors)
        fill.putalpha(mask)
        canvas = Image.alpha_composite(canvas, fill)
        if delta_text:
            flat = Image.new('RGBA', (width, height), self._delta_rgb() + (255,))
            flat.putalpha(delta_mask)
            canvas = Image.alpha_composite(canvas, flat)
        return canvas

    def _shadow_rgb(self):
        return theme.hex_to_rgb(theme.SHADOW)

    def _delta_rgb(self):
        return theme.hex_to_rgb(theme.mix(self.cget('bg'), self._colors[-1], .78))

    def _present(self, image):
        self._photo = ImageTk.PhotoImage(image, master=self)
        if self._image_item is None:
            self._image_item = self.create_image(2, 0, anchor='nw', image=self._photo)
        else:
            self.itemconfigure(self._image_item, image=self._photo)
            self.coords(self._image_item, 2, 0)


class NumberDisplay(_Bitmap, tk.Canvas):
    """Large damage number: italic face with a gradient fill."""

    def __init__(self, master, size=38, colors=None, height=None, **kwargs):
        self._text = '0'
        self._size = size
        self._colors = colors or (theme.CYAN, theme.LAVENDER, theme.PINK)
        self._photo = None
        self._image_item = None
        font = _load_font(int(size * theme.SCALE), self.weight)
        ascent, descent = font.getmetrics()
        super().__init__(master, bg=master.cget('bg'), highlightthickness=0, bd=0,
                         height=height or int((ascent + descent) * 1.3), **kwargs)
        self.bind('<Configure>', lambda e: self.refresh())

    def cget(self, key):
        if key == 'text':
            return self._text
        return tk.Canvas.cget(self, key)

    def configure(self, cnf=None, **kwargs):
        if 'text' in kwargs:
            self.set_text(kwargs.pop('text'))
        if 'font' in kwargs:
            self.set_font(kwargs.pop('font'))
        if 'colors' in kwargs:
            self._colors = kwargs.pop('colors')
            self.refresh()
        return super().configure(cnf, **kwargs)

    config = configure

    def set_font(self, font):
        size = abs(int(font[1])) if isinstance(font, (tuple, list)) and len(font) > 1 else None
        if size:
            self._size = size / theme.SCALE
        self.refresh()

    def set_text(self, text):
        self._text = str(text)
        self.refresh()

    def refresh(self):
        if not self.winfo_exists():
            return
        self._present(self._render(self._text))

    def tick(self):
        """Nothing moves on its own; the readout is a still gradient."""
        if self._image_item is None and self.winfo_exists():
            self.refresh()


class DeltaDisplay(NumberDisplay):
    """Current-command damage: gradient total with a softer delta beside it."""

    def __init__(self, master, size=25, colors=None, **kwargs):
        self._main = '0'
        self._delta = ''
        super().__init__(master, size=size, colors=colors, **kwargs)

    def cget(self, key):
        if key == 'text':
            return f'{self._main} + {self._delta}' if self._delta else self._main
        return tk.Canvas.cget(self, key)

    def set_text(self, text):
        text = str(text)
        if ' + ' in text:
            self._main, self._delta = text.split(' + ', 1)
        else:
            self._main, self._delta = text, ''
        self.refresh()

    def refresh(self):
        if not self.winfo_exists():
            return
        self._present(self._render(self._main, self._delta))


def shaped_points(x1, y1, x2, y2, radius):
    """The exact control points components.rounded() hands to the canvas."""
    r = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    return [(x1 + r, y1), (x2 - r, y1), (x2, y1), (x2, y1 + r),
            (x2, y2 - r), (x2, y2), (x2 - r, y2), (x1 + r, y2),
            (x1, y2), (x1, y2 - r), (x1, y1 + r), (x1, y1)]


def smoothed_path(points, steps=24):
    """Sample the same quadratic B-spline Tk draws for a smooth polygon."""
    count = len(points)
    path = []
    for index in range(count):
        previous = points[index - 1]
        corner = points[index]
        following = points[(index + 1) % count]
        start = ((previous[0] + corner[0]) / 2, (previous[1] + corner[1]) / 2)
        stop = ((corner[0] + following[0]) / 2, (corner[1] + following[1]) / 2)
        for step in range(steps):
            t = step / steps
            inverse = 1 - t
            path.append((inverse * inverse * start[0] + 2 * inverse * t * corner[0] + t * t * stop[0],
                         inverse * inverse * start[1] + 2 * inverse * t * corner[1] + t * t * stop[1]))
    return path


class BorderLight:
    """The outline itself, lit: a soft bright arc laps the full border."""

    SEGMENTS = 64
    SPREAD = 0.22
    SPEED = 2.6

    def __init__(self, card, accent=None, base=None, width=1.8):
        self.card = card
        self.accent = accent or theme.PINK
        self.base = base or theme.LINE
        self.width = width
        self.phase = 0.0
        self.items = []
        self.applied = []
        self.active = False
        self._size = (0, 0)

    def show(self, active):
        self.active = active
        if not active:
            self._clear()
        elif not self.items:
            self._build()

    def _clear(self):
        for item in self.items:
            try:
                self.card.delete(item)
            except tk.TclError:
                pass
        self.items = []
        self.applied = []

    def _build(self):
        card = self.card
        try:
            width = max(40, card.winfo_width())
            height = max(20, card.winfo_height())
        except tk.TclError:
            return
        self._clear()
        control = shaped_points(1, 1, width - 2, height - 2, card.radius)
        path = smoothed_path(control, steps=24)
        total = len(path)
        self._size = (width, height)
        base_rgb = theme.hex_to_rgb(self.base)
        for index in range(self.SEGMENTS):
            start = int(index * total / self.SEGMENTS) % total
            stop = int((index + 1) * total / self.SEGMENTS) % total
            span = (stop - start) % total or 1
            coords = []
            for offset in range(span + 1):
                x, y = path[(start + offset) % total]
                coords.extend((x, y))
            item = card.create_line(coords, width=self.width, capstyle='round',
                                    fill=self.base)
            self.items.append(item)
            self.applied.append(-1.0)

    def update(self):
        if not self.active:
            return
        card = self.card
        try:
            width = max(40, card.winfo_width())
            height = max(20, card.winfo_height())
        except tk.TclError:
            return
        if not self.items or (width, height) != self._size:
            self._build()
            if not self.items:
                return
        head = self.phase % 1.0
        for index, item in enumerate(self.items):
            centre = (index + 0.5) / self.SEGMENTS
            distance = abs(centre - head)
            distance = min(distance, 1 - distance)
            glow = 0.0
            if distance < self.SPREAD:
                glow = 1.0 - distance / self.SPREAD
                glow = glow * glow
            if abs(glow - self.applied[index]) < 0.02:
                continue
            self.applied[index] = glow
            card.itemconfigure(item, fill=theme.mix(self.base, self.accent, glow),
                               width=self.width + 1.8 * glow)
        self.phase = (self.phase + self.SPEED / 100.0) % 1.0
