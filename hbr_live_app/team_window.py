"""Review captured builds without interrupting the live battle."""
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from . import theme
from .components import RoundedButton
from .portraits import Portraits
from .damage_inputs import STATS


class TeamWindow(tk.Toplevel):
    def __init__(self, parent, store):
        super().__init__(parent)
        self.store = store
        self.title('配队档案 · 养成与配装')
        self.geometry('1180x760')
        self.minsize(1040, 620)
        self.configure(bg=theme.BG)
        self.portraits = Portraits(self, size=52)
        tk.Label(self, text='每场首次完整采样 → 待确认 → 另存配队或覆盖已有配队', bg=theme.BG,
                 fg=theme.FG, font=theme.ui(13)).pack(anchor='w', padx=18, pady=(14, 4))
        tk.Label(self, text='记录采样时的实测数值，可能含战斗修正；饰品暂保留可读取的效果，不代表完整装备清单。',
                 bg=theme.BG, fg=theme.DIM, font=theme.ui(10)).pack(anchor='w', padx=18)
        body = tk.PanedWindow(self, orient='horizontal', bg=theme.BG, sashwidth=8)
        body.pack(fill='both', expand=True, padx=18, pady=12)
        left = tk.Frame(body, bg=theme.CARD)
        right = tk.Frame(body, bg=theme.CARD)
        body.add(left, minsize=280, width=310); body.add(right, minsize=690)
        self.tree = ttk.Treeview(left, show='tree', selectmode='browse')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', self.show)
        self.search = tk.StringVar()
        self.scope = ttk.Combobox(left, state='readonly', values=['全部', '配队名', '角色 / 风格'], width=18)
        self.scope.current(0)
        self.scope.pack(before=self.tree, fill='x', padx=8, pady=(8, 4))
        query = ttk.Entry(left, textvariable=self.search)
        query.pack(before=self.tree, fill='x', padx=8, pady=(0, 8))
        self.search.trace_add('write', lambda *_: self.refresh())
        self.scope.bind('<<ComboboxSelected>>', lambda e: self.refresh())
        self.caption = tk.Label(right, bg=theme.CARD, fg=theme.PINK, font=theme.ui(14, 'bold'), anchor='w', justify='left')
        self.caption.pack(fill='x', padx=14, pady=(12, 6))
        self.note = tk.Label(right, bg=theme.CARD, fg=theme.DIM, font=theme.ui(10), anchor='w', justify='left')
        self.note.pack(fill='x', padx=14, pady=(0, 10))
        self.tabs = ttk.Notebook(right)
        self.tabs.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        self.pages = {}
        for title in ('六维与 DP / HP', '技能', '饰品效果', '天赋与其他被动', '共鸣被动'):
            outer = tk.Frame(self.tabs, bg=theme.CARD)
            self.tabs.add(outer, text=title)
            canvas = tk.Canvas(outer, bg=theme.CARD, highlightthickness=0)
            scroll = ttk.Scrollbar(outer, command=canvas.yview)
            scroll.pack(side='right', fill='y')
            canvas.configure(yscrollcommand=scroll.set)
            canvas.pack(fill='both', expand=True)
            inner = tk.Frame(canvas, bg=theme.CARD)
            item = canvas.create_window(0, 0, window=inner, anchor='nw')
            inner.bind('<Configure>', lambda e,c=canvas: c.configure(scrollregion=c.bbox('all')))
            canvas.bind('<Configure>', lambda e,c=canvas,i=item: c.itemconfigure(i,width=e.width))
            canvas.bind('<MouseWheel>', lambda e,c=canvas: c.yview_scroll(int(-e.delta/120), 'units'))
            self.pages[title] = inner
        bar = tk.Frame(self, bg=theme.BG)
        bar.pack(fill='x', padx=18, pady=(0, 14))
        tk.Label(bar, text='配队名', bg=theme.BG, fg=theme.FG).grid(row=0,column=0,padx=4)
        self.name = ttk.Entry(bar, width=24)
        self.name.grid(row=0,column=1,padx=4,sticky='ew')
        self.target = ttk.Combobox(bar, state='readonly', width=28)
        self.target.grid(row=0,column=2,padx=4,sticky='ew')
        self.save_button = RoundedButton(bar, '保存待确认记录', self.save, theme.PINK_FILL, theme.on_fill, theme.ui(11),height=32)
        self.save_button.grid(row=0,column=3,padx=4)
        RoundedButton(bar, '删除 / 不保存', self.remove, theme.CARD_HI, theme.FG, theme.ui(11),height=32).grid(row=1,column=3,pady=(8,0))
        tk.Label(bar,text='覆盖时请在右侧选择原配队；同成员也可另存不同配装。',bg=theme.BG,fg=theme.DIM).grid(row=1,column=0,columnspan=3,sticky='w',pady=(8,0))
        bar.columnconfigure(1, weight=1);bar.columnconfigure(2, weight=1)
        self.refresh()

    def refresh(self):
        from .team_views import member_matches
        previous = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        self.records = {}; self.member_records = {}
        saved = self.store.rows()
        self.targets = [None] + [key for key, _, _ in saved]
        self.target['values'] = ['另存为新配队'] + [f'{name} · #{key}' for key, name, _ in saved]
        self.target.current(0)
        query = self.search.get().strip().casefold()
        scope = self.scope.get()
        for draft, title in ((True,'待确认'),(False,'已保存')):
            root = 'drafts' if draft else 'saved'
            self.tree.insert('', 'end', iid=root, text=title, open=True)
            for key, name, payload in self.store.rows(draft):
                caption = payload['captured_at'].replace('T',' ') if draft else name
                team_match = scope != '角色 / 风格' and query in caption.casefold()
                matches = [i for i,p in enumerate(payload['members']) if scope != '配队名' and member_matches(p,query)]
                if query and not team_match and not matches: continue
                iid = f'{root}:{key}'
                self.tree.insert(root, 'end', iid=iid, text=caption, open=True)
                self.records[iid] = (draft, key, name, payload)
                for i,p in enumerate(payload['members']):
                    if query and not team_match and i not in matches: continue
                    child = f'{iid}/member/{i}'
                    self.tree.insert(iid,'end',iid=child,text=f"{p.get('actor') or '?'} · {p.get('style_name') or p['style_label']}")
                    self.member_records[child] = (iid, i)
        selected = previous[0] if previous and (previous[0] in self.records or previous[0] in self.member_records) else next(iter(self.member_records),None)
        if selected:
            self.tree.selection_set(selected);self.show()
        else:
            self.clear_pages()
            self.caption.configure(text='没有匹配的档案', image='')
            self.note.configure(text='可修改搜索条件，或连接战斗生成待确认记录。')

    def selected(self):
        values = self.tree.selection()
        if not values:return None
        iid = values[0]
        if iid in self.member_records: iid = self.member_records[iid][0]
        return self.records.get(iid)

    def clear_pages(self):
        for page in self.pages.values():
            for widget in page.winfo_children(): widget.destroy()

    def card(self, page, title, text, color=None):
        from .components import RoundedCard
        card = RoundedCard(page, background=theme.mix(theme.CARD, color or theme.CYAN, .06),
                           outline=theme.LINE, pad=(14, 10), radius=theme.RADIUS_SM)
        card.pack(fill='x', padx=8, pady=5)
        heading = tk.Label(card.content,text=title,bg=card.background,fg=color or theme.CYAN,
                 font=theme.ui(12,'bold'),anchor='w',justify='left',wraplength=580)
        heading.pack(fill='x')
        heading.bind('<Configure>',lambda e: heading.configure(wraplength=max(120,e.width-8)))
        label = tk.Label(card.content,text=text,bg=card.background,fg=theme.FG,
                        font=theme.ui(11),anchor='w',justify='left',wraplength=580)
        label.pack(fill='x',pady=(5,0))
        label.bind('<Configure>',lambda e: label.configure(wraplength=max(120,e.width-8)))
        return card.content

    def show(self, event=None):
        from .team_views import effect_group, equipment_slot
        row = self.selected()
        if not row:
            self.clear_pages();self.caption.configure(text='请选择配队或角色',image='');self.note.configure(text='');return
        draft, key, name, payload = row
        self.name.delete(0,'end')
        self.name.insert(0, ' / '.join(p.get('actor') or p['style_label'] for p in payload['members'][:3]) if draft else name)
        iid = self.tree.selection()[0]
        children = self.tree.get_children(iid)
        first = self.member_records.get(children[0], (None,0))[1] if children else 0
        index = self.member_records.get(iid, (None,first))[1]
        p = payload['members'][index]
        self.clear_pages()
        photo = self.portraits.get(p['style_label'])
        self.caption.configure(text=f"  {p.get('actor') or '?'} / {p.get('style_name') or p['style_label']}",image=photo or '',compound='left')
        self.note.configure(text=f"{('待确认配队' if draft else name)} · 采样 {payload['captured_at']} · Turn {payload.get('context',{}).get('turn','?')}\n左侧展开配队选择角色；搜索角色可查询其在不同队伍中的配装。")
        page = self.pages['六维与 DP / HP']
        self.card(page,'资源 · 当前 / 上限',f"DP   {p.get('dp','?')} / {p.get('dp_max','?')}         HP   {p.get('hp','?')} / {p.get('hp_max','?')}",theme.MINT)
        grid=tk.Frame(page,bg=theme.CARD);grid.pack(fill='x',padx=8,pady=8)
        for i,(k,title) in enumerate(STATS.items()):
            tile=tk.Frame(grid,bg=theme.CARD_HI,padx=12,pady=14)
            tile.grid(row=i//3,column=i%3,sticky='ew',padx=4,pady=4)
            grid.columnconfigure(i%3,weight=1)
            tk.Label(tile,text=title,bg=theme.CARD_HI,fg=theme.DIM,font=theme.ui(11)).pack()
            tk.Label(tile,text=str(p.get('stats',{}).get(k,'?')),bg=theme.CARD_HI,fg=theme.FG,font=theme.ui(20,'bold')).pack()
        self.card(page,'数值来源','首次完整战斗采样，可能含战斗修正，并非角色裸面板。',theme.GOLD)
        page=self.pages['技能']
        if not p.get('skills_complete'):self.card(page,'列表不完整','仅展示已读取的技能，不用资料库默认等级补齐。',theme.GOLD)
        for skill in p.get('skills',[]):
            area = self.card(page,skill.get('name') or skill.get('label') or '未知技能',f"等级  Lv.{skill.get('level') if skill.get('level') is not None else '?'}",theme.CYAN)
            RoundedButton(area, '查看技能详情 ›', lambda skill=skill: self.show_skill(skill),
                          theme.CARD_HI, theme.CYAN, theme.ui(11), height=30).pack(anchor='w',pady=(8,0))
        if not p.get('skills'):self.card(page,'暂无技能记录','尚未读取技能列表。')
        grouped={title:[] for title in ('饰品效果','天赋与其他被动','共鸣被动')}
        for effect in p.get('passives',[]):grouped[effect_group(effect)].append(effect)
        for title,items in grouped.items():
            page=self.pages[title]
            if title=='饰品效果':self.card(page,'已读取的饰品效果','按效果来源区分部位；未读取到完整饰品名称、强化等级或数量，不推断未装备。',theme.GOLD)
            if title=='天赋与其他被动':self.card(page,'来源说明','这里保留未归为饰品或共鸣的实际被动；未确认来源不视为已解锁风格天赋。',theme.DIM)
            if not items:self.card(page,'暂无可确认记录','本次快照未读取到此类效果。',theme.DIM)
            for effect in items:
                heading=effect.get('name') or effect.get('label','未知效果')
                if title=='饰品效果':heading=equipment_slot(effect)+' · '+heading
                text=effect.get('description') or '效果描述未读取'
                if effect.get('condition'):text+='\n条件  '+effect['condition']
                text+='\n来源  '+effect.get('label','未确认')
                self.card(page,heading,text,theme.LAVENDER if title=='共鸣被动' else theme.PINK)

    def show_skill(self, skill):
        from .team_skill_details import show_skill
        show_skill(self, skill)

    def save(self):
        row = self.selected()
        if not row or not row[0]:
            messagebox.showinfo('配队档案','请先选择一条待确认记录。', parent=self);return
        target = self.targets[self.target.current()]
        if target is not None and not messagebox.askyesno('覆盖配队','将用这次采样替换所选配队的全部成员与配装，继续吗？',parent=self):return
        try:self.store.save(row[1], self.name.get(), target)
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror('保存失败',str(exc),parent=self);return
        self.refresh()

    def remove(self):
        row = self.selected()
        if not row:return
        if not messagebox.askyesno('删除档案','删除这条配队档案？原有战斗诊断日志不受影响。',parent=self):return
        try:self.store.delete(row[1], draft=row[0])
        except sqlite3.Error as exc:
            messagebox.showerror('删除失败',str(exc),parent=self);return
        self.refresh()
