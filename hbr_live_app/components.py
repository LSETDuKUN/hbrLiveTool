"""Rounded shells, buttons and chips. Presentation only: no data access."""
import tkinter as tk
from tkinter import font as tkfont

from . import theme


def rounded(canvas, x1, y1, x2, y2, radius=16, **kwargs):
    r = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    return canvas.create_polygon(x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r,
        x1, y1 + r, x1, y1, smooth=True, splinesteps=24, **kwargs)


class RoundedCard(tk.Canvas):
    """Rounded shell whose inner frame keeps normal Tk geometry management."""
    def __init__(self, master, background=theme.CARD, outline=theme.LINE,
                 radius=theme.RADIUS, pad=(16, 14), accent=None, stretch=False,
                 clip=False, shadow=True, highlight=None, **kwargs):
        super().__init__(master, bg=master.cget('bg'), highlightthickness=0, bd=0, **kwargs)
        self.background = background
        self.outline = outline
        self.radius = radius
        self.pad = pad
        self.accent = accent
        self.stretch = stretch
        self.clip = clip
        self.shadow = shadow
        self.highlight = highlight
        self.fixed_height = kwargs.get('height')
        self.content = tk.Frame(self, bg=background)
        self.slot = self.create_window(pad[0], pad[1], anchor='nw', window=self.content)
        self.content.bind('<Configure>', self._layout)
        self.bind('<Configure>', self._layout)
        self.draw()

    def configure(self, cnf=None, **kwargs):
        for option, attr in (('background', 'background'), ('accent', 'accent'),
                             ('outline', 'outline')):
            if option in kwargs:
                setattr(self, attr, kwargs.pop(option))
                self.content.configure(bg=self.background)
        result = super().configure(cnf, **kwargs)
        self.draw()
        return result

    config = configure

    def _layout(self, event=None):
        self.draw()

    def draw(self):
        width = max(60, self.winfo_width())
        padx, pady = self.pad
        self.itemconfigure(self.slot, width=width - 2 * padx)
        natural = self.content.winfo_reqheight() + 2 * pady
        if self.clip and self.stretch:
            # Only viewport cards clip their body; inner cards must shrink and
            # grow with their content.
            self.itemconfigure(self.slot, width=width - 2 * padx,
                               height=max(1, self.winfo_height() - 2 * pady))
        if self.fixed_height is None and int(self.cget('height') or 0) != natural:
            self.configure(height=natural)
        actual = self.winfo_height()
        height = max(natural, actual) if self.stretch else natural
        self.delete('shell')
        if self.shadow:
            rounded(self, 3, 5, width - 1, height - 1, self.radius,
                    fill=theme.SHADOW, outline='', tags='shell')
        rounded(self, 1, 1, width - 2, height - 2, self.radius,
                fill=self.background, outline=self.outline or '', tags='shell')
        if self.outline:
            self.create_line(self.radius, 2, width - self.radius, 2,
                             fill=theme.mix(self.background, '#ffffff', .07), tags='shell')
        if self.accent:
            rounded(self, padx - 8, pady, padx - 5, pady + 17, 1.5,
                    fill=self.accent, outline='', tags='shell')
        if self.highlight:
            rounded(self, 3, 3, width - 3, height - 3, max(4, self.radius - 3),
                    fill='', outline=self.highlight, tags='shell')
        self.tag_lower('shell')


class RoundedButton(tk.Canvas):
    def __init__(self, master, text='', command=None, bg=theme.PINK, fg='#2a2036',
                 font=None, height=44, radius=None, **kwargs):
        self._text, self._color, self._fg = text, bg, fg
        self._font = font or theme.ui(13, 'bold')
        self._command = command
        self._height = height
        self._radius = radius
        self._hover = False
        self._state = kwargs.pop('state', 'normal')
        self._explicit_width = 'width' in kwargs
        if not self._explicit_width:
            kwargs['width'] = tkfont.Font(font=self._font).measure(text or '确定') + 46
        super().__init__(master, height=height, bg=master.cget('bg'), highlightthickness=0,
                         takefocus=True, cursor='hand2', bd=0, **kwargs)
        self.bind('<Configure>', lambda e: self.draw())
        self.bind('<Button-1>', self._invoke)
        self.bind('<Return>', self._invoke)
        self.bind('<space>', self._invoke)
        self.bind('<Enter>', self._enter)
        self.bind('<Leave>', self._leave)
        self.bind('<FocusIn>', lambda e: self.draw())
        self.bind('<FocusOut>', lambda e: self.draw())

    def configure(self, cnf=None, **kwargs):
        relabel = None
        if 'state' in kwargs:
            self._state = kwargs.pop('state')
        for option, attr in (('text', '_text'), ('bg', '_color'), ('fg', '_fg')):
            if option in kwargs:
                setattr(self, attr, kwargs.pop(option))
                if option == 'text':
                    relabel = self._text
        if 'width' in kwargs:
            self._explicit_width = True
        if relabel is not None and not self._explicit_width:
            kwargs['width'] = tkfont.Font(font=self._font).measure(relabel or '确定') + 46
        result = super().configure(cnf, **kwargs)
        self.draw()
        return result

    config = configure

    def invoke(self):
        if self._command:
            self._command()

    def _invoke(self, event=None):
        if self._state == 'disabled':
            return
        self.invoke()

    def _enter(self, event=None):
        self._hover = True
        self.draw()

    def _leave(self, event=None):
        self._hover = False
        self.draw()

    def draw(self):
        self.delete('all')
        width = max(2, self.winfo_width())
        height = self._height
        color = theme.lift(self._color, .10) if self._hover else self._color
        label = self._fg
        if self._state == 'disabled':
            color = theme.mix(self._color, theme.BG, .55)
            label = theme.mix(self._fg, theme.BG, .45)
        radius = self._radius if self._radius is not None else height / 2
        if self.focus_get() is self:
            outline = theme.lift(color, .35)
        else:
            outline = theme.mix(color, theme.FG, .16)
        rounded(self, 2, 3, width - 1, height, radius, fill=theme.SHADOW, outline='')
        rounded(self, 1, 1, width - 1, height - 2, radius, fill=color, outline=outline)
        self.create_line(radius, 2.5, width - radius, 2.5,
                         fill=theme.mix(color, '#ffffff', .18))
        self.create_text(width / 2, height / 2, text=self._text, font=self._font, fill=label)


class Pill(tk.Canvas):
    """Small rounded label used for tags, status and counters."""
    def __init__(self, master, text='', fg=theme.PINK, bg=theme.PINK_DEEP, font=None,
                 height=24, padx=11, **kwargs):
        self._text, self._fg, self._bg = text, fg, bg
        self._font = font or theme.ui(11)
        self._height = height
        self._padx = padx
        super().__init__(master, height=height, bg=master.cget('bg'),
                         highlightthickness=0, bd=0, **kwargs)
        self.bind('<Configure>', lambda e: self.draw())

    def configure(self, cnf=None, **kwargs):
        for option, attr in (('text', '_text'), ('fg', '_fg'), ('bg', '_bg')):
            if option in kwargs:
                setattr(self, attr, kwargs.pop(option))
        result = super().configure(cnf, **kwargs)
        self.draw()
        return result

    config = configure

    def draw(self):
        self.delete('all')
        font = tkfont.Font(font=self._font)
        width = font.measure(self._text) + 2 * self._padx
        self.configure(width=width)
        height = self._height
        rounded(self, 1, 1, width - 1, height - 1, height / 2, fill=self._bg, outline='')
        self.create_text(width / 2, height / 2, text=self._text, font=self._font, fill=label)


class ToggleChip(tk.Canvas):
    """Rounded on/off chip bound to a BooleanVar."""
    def __init__(self, master, text, variable, command=None, accent=theme.PINK,
                 height=32, **kwargs):
        self._text, self._var, self._command = text, variable, command
        self._accent = accent
        self._height = height
        self._hover = False
        super().__init__(master, height=height, bg=master.cget('bg'),
                         highlightthickness=0, bd=0, cursor='hand2', takefocus=True)
        self._trace = variable.trace_add('write', lambda *_: self.draw())
        self.bind('<Button-1>', self._toggle)
        self.bind('<Return>', self._toggle)
        self.bind('<space>', self._toggle)
        self.bind('<Enter>', lambda e: self._hovered(True))
        self.bind('<Leave>', lambda e: self._hovered(False))
        self.bind('<Configure>', lambda e: self.draw())

    def _hovered(self, value):
        self._hover = value
        self.draw()

    def _toggle(self, event=None):
        self._var.set(not self._var.get())
        if self._command:
            self._command()
        self.draw()

    def draw(self):
        self.delete('all')
        font = tkfont.Font(font=theme.ui(12))
        on = bool(self._var.get())
        width = font.measure(self._text) + 54
        self.configure(width=width)
        height = self._height
        fill = theme.mix(theme.CARD, self._accent, .26) if on else theme.CARD
        if self._hover:
            fill = theme.lift(fill, .06)
        rounded(self, 1, 1, width - 1, height - 1, height / 2, fill=fill,
                outline=theme.mix(self._accent, theme.CARD, .55) if on else theme.LINE)
        dot = self._accent if on else theme.MUTED
        self.create_oval(12, height / 2 - 4, 20, height / 2 + 4, fill=dot, outline='')
        self.create_text(28, height / 2, text=self._text, anchor='w',
                         font=theme.ui(12, 'bold' if on else 'normal'),
                         fill=theme.FG if on else theme.DIM)


class RoundedEntry(tk.Canvas):
    """Rounded field wrapping a borderless entry, so inputs match the cards."""

    def __init__(self, master, textvariable=None, width=130, height=None, justify='right',
                 font=None, radius=None, **kwargs):
        self._var = textvariable if textvariable is not None else tk.StringVar()
        self._justify = justify
        self._font = font or theme.ui(12)
        self._height = height or theme.px(34)
        self._radius = radius
        self._focused = False
        super().__init__(master, height=self._height, width=width, bg=master.cget('bg'),
                         highlightthickness=0, bd=0, **kwargs)
        self.entry = tk.Entry(self, textvariable=self._var, relief='flat', bd=0,
                              highlightthickness=0, bg=theme.field(), fg=theme.FG,
                              insertbackground=theme.FG, disabledbackground=theme.field(),
                              disabledforeground=theme.MUTED, justify=justify, font=self._font)
        self._slot = self.create_window(12, self._height / 2, anchor='w', window=self.entry)
        self.entry.bind('<FocusIn>', self._focus_in)
        self.entry.bind('<FocusOut>', self._focus_out)
        self.bind('<Configure>', lambda e: self.draw())
        self.entry.bind('<Configure>', lambda e: None)
        self.draw()

    def _focus_in(self, event=None):
        self._focused = True
        self.draw()

    def _focus_out(self, event=None):
        self._focused = False
        self.draw()

    def focus_set(self):
        self.entry.focus_set()

    def configure(self, cnf=None, **kwargs):
        if 'textvariable' in kwargs:
            self._var = kwargs.pop('textvariable')
            self.entry.configure(textvariable=self._var)
        if 'justify' in kwargs:
            self._justify = kwargs.pop('justify')
            self.entry.configure(justify=self._justify)
        if 'state' in kwargs:
            self.entry.configure(state=kwargs.pop('state'))
        result = super().configure(cnf, **kwargs)
        self.after_idle(self.draw)
        return result

    config = configure

    def get(self):
        return self._var.get()

    def set(self, value):
        self._var.set(value)

    def draw(self):
        self.delete('all')
        width = max(40, self.winfo_width())
        height = self._height
        radius = self._radius if self._radius is not None else min(height / 2, theme.RADIUS_SM)
        outline = theme.PINK if self._focused else theme.LINE
        rounded(self, 1, 1, width - 1, height - 1, radius, fill=theme.field(), outline=outline)
        if self._focused:
            rounded(self, 3, 3, width - 3, height - 3, max(3, radius - 2), fill='',
                    outline=theme.mix(theme.field(), theme.PINK, .45))
        self.itemconfigure(self._slot, width=max(20, width - 24))


class RoundedSelect(tk.Canvas):
    """Read-only select that keeps the combobox API but drops the native chrome."""

    def __init__(self, master, textvariable=None, values=(), width=190, height=None,
                 state='readonly', font=None, placeholder='请选择', **kwargs):
        self._var = textvariable if textvariable is not None else tk.StringVar()
        self._values = list(values)
        self._font = font or theme.ui(12)
        self._height = height or theme.px(34)
        self._state = state
        self._placeholder = placeholder
        self._callbacks = {}
        self._hover = False
        self._open = False
        super().__init__(master, height=self._height, width=width, bg=master.cget('bg'),
                         highlightthickness=0, bd=0, cursor='hand2', takefocus=True, **kwargs)
        self.bind('<Button-1>', self.popup)
        self.bind('<Return>', self.popup)
        self.bind('<space>', self.popup)
        self.bind('<Enter>', lambda e: self._set_hover(True))
        self.bind('<Leave>', lambda e: self._set_hover(False))
        self.bind('<Configure>', lambda e: self.draw())
        self._var.trace_add('write', lambda *_: self.draw())
        self.draw()

    def _set_hover(self, value):
        self._hover = value
        self.draw()

    def draw(self):
        self.delete('all')
        width = max(40, self.winfo_width())
        height = self._height
        radius = min(height / 2, theme.RADIUS_SM)
        fill = theme.lift(theme.field(), .05) if self._hover else theme.field()
        outline = theme.PINK if self._open else theme.LINE
        rounded(self, 1, 1, width - 1, height - 1, radius, fill=fill, outline=outline)
        text = self._var.get() or self._placeholder
        color = theme.FG if self._var.get() else theme.MUTED
        room = width - 34
        while room > 20:
            item = self.create_text(14, height / 2, text=text, anchor='w', font=self._font, fill=color)
            box = self.bbox(item)
            if box and box[2] <= width - 30:
                break
            self.delete(item)
            text = text[:-2] + '…'
            if len(text) <= 2:
                break
        self.create_text(width - 16, height / 2, text='▾', anchor='center',
                         font=self._font, fill=theme.MUTED)

    def popup(self, event=None):
        if self._state == 'disabled' or not self._values:
            return
        self._open = True
        self.draw()
        menu = tk.Menu(self, tearoff=False, bg=theme.CARD, fg=theme.FG, bd=0, relief='flat',
                       activebackground=theme.CARD_HI, activeforeground=theme.FG,
                       font=self._font, selectcolor=theme.PINK)
        for value in self._values:
            menu.add_command(label=value, command=lambda v=value: self._choose(v))
        try:
            menu.tk_popup(self.winfo_rootx(), self.winfo_rooty() + self.winfo_height())
        finally:
            menu.grab_release()
            self._open = False
            self.after_idle(self.draw)

    def _choose(self, value):
        self._var.set(value)
        self.draw()
        for callback in list(self._callbacks.get('<<ComboboxSelected>>', [])):
            callback(None)

    def bind(self, sequence=None, func=None, add=None):
        if sequence == '<<ComboboxSelected>>' and func is not None:
            self._callbacks.setdefault(sequence, []).append(func)
            return 'cb' + str(len(self._callbacks[sequence]))
        return super().bind(sequence, func, add)

    def get(self):
        return self._var.get()

    def set(self, value):
        self._var.set(value)

    def current(self, index=None):
        current = self._var.get()
        if index is None:
            try:
                return self._values.index(current)
            except ValueError:
                return -1
        if 0 <= index < len(self._values):
            self.set(self._values[index])
        return index

    def configure(self, cnf=None, **kwargs):
        if 'values' in kwargs:
            self._values = list(kwargs.pop('values'))
        if 'state' in kwargs:
            self._state = kwargs.pop('state')
        if 'textvariable' in kwargs:
            self._var = kwargs.pop('textvariable')
        result = super().configure(cnf, **kwargs)
        self.after_idle(self.draw)
        return result

    config = configure


class Segment(tk.Canvas):
    """Rounded segmented control bound to a StringVar."""
    def __init__(self, master, options, variable, command=None, accent=theme.PINK,
                 height=30, **kwargs):
        self.options = list(options)
        self._var, self._command, self._accent = variable, command, accent
        self._height = height
        self._hover = None
        super().__init__(master, height=height, bg=master.cget('bg'), highlightthickness=0,
                         bd=0, cursor='hand2', takefocus=True)
        self._trace = variable.trace_add('write', lambda *_: self.draw())
        self.bind('<Button-1>', self._click)
        self.bind('<Motion>', self._motion)
        self.bind('<Leave>', lambda e: self._set_hover(None))
        self.bind('<Configure>', lambda e: self.draw())

    def _segments(self):
        font = tkfont.Font(font=theme.ui(11))
        edges, x = [], 2
        for value, label in self.options:
            width = font.measure(label) + 30
            edges.append((value, label, x, x + width))
            x += width + 4
        return edges, x + 2

    def _hit(self, x):
        for value, label, left, right in self._segments()[0]:
            if left <= x <= right:
                return value
        return None

    def _click(self, event):
        value = self._hit(event.x)
        if value is not None and value != self._var.get():
            self._var.set(value)
            if self._command:
                self._command()
            self.draw()

    def _motion(self, event):
        self._set_hover(self._hit(event.x))

    def _set_hover(self, value):
        if value != self._hover:
            self._hover = value
            self.draw()

    def draw(self):
        self.delete('all')
        segments, total = self._segments()
        self.configure(width=total)
        height = self._height
        rounded(self, 1, 1, total - 1, height - 1, height / 2, fill=theme.CARD, outline=theme.LINE)
        for value, label, left, right in segments:
            active = value == self._var.get()
            if active:
                rounded(self, left, 3, right, height - 3, (height - 6) / 2,
                        fill=theme.mix(theme.CARD, self._accent, .3),
                        outline=theme.mix(self._accent, theme.CARD, .5))
            fill = self._accent if active else (theme.FG if value == self._hover else theme.DIM)
            self.create_text((left + right) / 2, height / 2, text=label,
                             font=theme.ui(11, 'bold' if active else 'normal'), fill=fill)


class TabBar(tk.Canvas):
    """Flat rounded tab strip; the owner swaps the visible page."""
    def __init__(self, master, names, command, bg=theme.BG, height=44, **kwargs):
        super().__init__(master, height=height, bg=bg, highlightthickness=0, bd=0, **kwargs)
        self.names = list(names)
        self.command = command
        self.current = self.names[0] if self.names else None
        self._hover = None
        self.font = theme.ui(12)
        self.bind('<Button-1>', self._click)
        self.bind('<Motion>', self._motion)
        self.bind('<Leave>', lambda e: self._set_hover(None))
        self.bind('<Configure>', lambda e: self.draw())

    def _segments(self):
        font = tkfont.Font(font=self.font)
        edges, x = [], 8
        for name in self.names:
            width = font.measure(name) + 40
            edges.append((name, x, x + width))
            x += width + 8
        return edges

    def _layout(self):
        limit=max(1,self.winfo_width()-8)
        x,y=8,0
        result=[]
        for name,left,right in self._segments():
            width=right-left
            if x>8 and x+width>limit:x,y=8,y+44
            result.append((name,x,x+width,y));x+=width+8
        return result

    def _hit(self, x, y):
        for name, left, right, top in self._layout():
            if left <= x <= right and top+4 <= y <= top+40:
                return name
        return None

    def _click(self, event):
        name = self._hit(event.x,event.y)
        if name and name != self.current:
            self.select(name)

    def _motion(self, event):
        self._set_hover(self._hit(event.x,event.y))

    def _set_hover(self, name):
        if name != self._hover:
            self._hover = name
            self.draw()

    def select(self, name):
        self.current = name
        self.draw()
        if self.command:
            self.command(name)

    def draw(self):
        self.delete('all')
        layout=self._layout()
        height=layout[-1][3]+44 if layout else 44
        if int(self.cget('height'))!=height:self.configure(height=height)
        for name, left, right, top in layout:
            active = name == self.current
            fill = theme.mix(theme.CARD, theme.PINK, .22) if active else theme.CARD
            if not active and name == self._hover:
                fill = theme.lift(theme.CARD, .06)
            rounded(self, left, top+4, right, top+40, 18, fill=fill,
                    outline=theme.mix(theme.PINK, theme.CARD, .7) if active else theme.LINE_SOFT)
            self.create_text((left + right) / 2, top+22, text=name, font=self.font,
                             fill=theme.PINK if active else theme.DIM)


class Divider(tk.Frame):
    def __init__(self, master, color=None, **kwargs):
        super().__init__(master, height=1, bg=color or theme.LINE_SOFT, **kwargs)


def blend(first, second, ratio):
    return theme.mix(first, second, ratio)


class ResourceMeter(tk.Canvas):
    def __init__(self, master, name, subtitle, colors, **kwargs):
        super().__init__(master, height=106, bg=master.cget('bg'), highlightthickness=0, **kwargs)
        self.name, self.subtitle, self.colors = name, subtitle, colors
        self.current = self.maximum = self.loss = 0
        self.number_font = tkfont.Font(family=theme.num_family(), size=-18, weight='bold')
        self.loss_font = tkfont.Font(family=theme.num_family(), size=-14, weight='bold')
        self.caption_font = tkfont.Font(family=theme.UI_FAMILY, size=-12)
        self.title_font = tkfont.Font(family=theme.UI_FAMILY, size=-13, weight='bold')
        self.bind('<Configure>', lambda event: self.draw())

    def set_values(self, current, maximum, loss):
        self.current, self.maximum, self.loss = current, maximum, loss
        self.draw()

    def draw(self):
        self.delete('all')
        width = max(1, self.winfo_width())
        if width < 40:
            return
        pad, right = 12, width - 12
        fraction = max(0, min(1, self.current / self.maximum if self.maximum else 0))
        rounded(self, 1, 1, width - 1, 105, theme.RADIUS, fill=theme.CARD, outline=theme.LINE)
        self.create_text(pad, 16, text=f'{self.name}  {self.subtitle}', anchor='w',
                         fill=self.colors[1], font=self.title_font)
        self.create_text(right, 16, text=f'{fraction:.0%}', anchor='e',
                         fill=theme.MUTED, font=self.caption_font)
        self.create_text(pad, 44, text=f"{'−' if self.loss >= 0 else '+'}{abs(self.loss):,}",
                         anchor='w', fill=theme.GOLD if self.loss else theme.MUTED,
                         font=self.loss_font)
        self.create_text(right, 44, text=f'{self.current:,}', anchor='e',
                         fill=theme.FG, font=self.number_font)
        rounded(self, pad, 62, right, 80, 9, fill=theme.BG, outline=theme.LINE_SOFT)
        filled = int((right - pad - 2) * fraction)
        for x in range(filled):
            self.create_line(pad + 1 + x, 64, pad + 1 + x, 78,
                             fill=theme.mix(self.colors[0], self.colors[1], x / max(1, right - pad - 2)))
        self.create_text(pad, 94, text='最近变化', anchor='w', fill=theme.MUTED, font=self.caption_font)
        self.create_text(right, 94, text=f'参考 {self.maximum:,}', anchor='e',
                         fill=theme.MUTED, font=self.caption_font)
