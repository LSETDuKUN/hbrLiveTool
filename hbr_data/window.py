"""Independent, non-blocking reference library for the capture widget."""
import json
import queue
import threading
from collections import Counter
import tkinter as tk
from tkinter import ttk

from hbr_live_app import theme
from hbr_live_app.components import RoundedButton, TabBar

from .store import Catalog
from .sync import sync
from .details import DetailService
from .cards import DetailCards
from .assets import sync_portraits

BG, CARD, SURFACE, FG, DIM, PINK = theme.BG, theme.CARD, theme.SURFACE, theme.FG, theme.DIM, theme.PINK
# Browse only the main categories; other synced tables remain available via SQL.
# Extend this mapping to expose another category in the browse menu later.
BROWSE_DATASETS = {"characters": "角色", "styles": "风格", "skills": "技能", "enemies": "敌人"}
LABELS = {"skills": "技能", "characters": "角色", "styles": "风格", "enemies": "敌人",
          "passives": "被动", "support_skills": "共鸣", "skill_types": "效果类型",
          "style_details": "风格详表", "enemy_details": "敌人详表", "master_skills": "大师技能",
          "rework_details": "调整历史", "localization": "本地化文本"}
EXAMPLE = """SELECT region, name, hit_count, part_index,
       power_min, power_max, diff_for_max,
       dp_multiplier, hp_multiplier, destruction_multiplier
FROM skill_damage
WHERE region = 'jp' AND power_max > 0
ORDER BY power_max DESC"""


class LibraryWindow:
    def __init__(self, master):
        self.catalog = Catalog()
        self.details = DetailService(self.catalog)
        self.asset_busy = False
        self.queue = queue.Queue()
        self.busy = False
        self.generation = 0
        self.selection_generation = 0
        self.offset = 0
        self.character_filter = None  # (region, label, display name) for the current style list
        self.window = w = tk.Toplevel(master)
        w.title("星屑资料室 · HBR QUEST")
        w.configure(bg=BG)
        w.geometry(f"{min(1160,w.winfo_screenwidth()-100)}x{min(860,w.winfo_screenheight()-120)}")
        w.minsize(820, 580)
        w.protocol("WM_DELETE_WINDOW", w.withdraw)
        theme.install(w)
        style = ttk.Style(w)
        self.apply_style(style)
        self.build_head()
        self.build_tabs()
        w.after(100, self.pump)

    def apply_style(self, style):
        style.configure("Quest.Treeview", background=CARD, fieldbackground=CARD, foreground=FG,
                        rowheight=30, borderwidth=0, font=theme.ui(12))
        style.configure("Quest.Treeview.Heading", background=theme.CARD_HI, foreground=PINK,
                        font=theme.ui(11, 'bold'), relief='flat', borderwidth=0)
        style.map("Quest.Treeview", background=[("selected", theme.CARD_HI)],
                  foreground=[("selected", FG)])
        style.configure("Quest.Browse.Treeview", background=CARD, fieldbackground=CARD, foreground=FG,
                        rowheight=56, borderwidth=0, font=theme.ui(12))
        style.configure("Quest.Browse.Treeview.Heading", background=theme.CARD_HI, foreground=PINK,
                        font=theme.ui(11, 'bold'), relief='flat', borderwidth=0)
        style.map("Quest.Browse.Treeview", background=[("selected", theme.CARD_HI)],
                  foreground=[("selected", FG)])
        style.configure("TCombobox", fieldbackground=theme.mix(SURFACE, '#000000', .35),
                        background=CARD, foreground=FG, arrowcolor=DIM, bordercolor=theme.LINE,
                        lightcolor=theme.LINE, darkcolor=theme.LINE, padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", theme.mix(SURFACE, '#000000', .35))],
                  foreground=[("readonly", FG)])
        style.configure("TScrollbar", background=theme.CARD_HI, troughcolor=SURFACE,
                        bordercolor=SURFACE, arrowcolor=DIM, relief='flat', gripcount=0)

    # ---- chrome ------------------------------------------------------------
    def build_head(self):
        w = self.window
        head = tk.Frame(w, bg=BG)
        head.pack(fill='x', padx=24, pady=(18, 10))
        tk.Label(head, text='✦', bg=BG, fg=PINK, font=theme.ui(19)).pack(side='left')
        tk.Label(head, text='星屑资料室', bg=BG, fg=FG,
                 font=theme.ui(19, 'bold')).pack(side='left', padx=(9, 0))
        tk.Label(head, text='HBR QUEST', bg=BG, fg=theme.MUTED,
                 font=theme.num(11)).pack(side='left', padx=(12, 0), pady=(4, 0))
        self.update_button = RoundedButton(head, '同步网站资料', self.update, PINK, '#2a2036',
                                           theme.ui(12, 'bold'), height=34)
        self.update_button.pack(side='right')
        self.asset_button = RoundedButton(head, '同步头像', self.update_assets, theme.CARD_HI, FG,
                                          theme.ui(12), height=34)
        self.asset_button.pack(side='right', padx=8)
        bar = tk.Frame(w, bg=BG)
        bar.pack(fill='x', padx=24, pady=(0, 10))
        self.status = tk.StringVar(value="本地资料 · 查询无需联网")
        dot = tk.Canvas(bar, width=10, height=10, bg=BG, highlightthickness=0, bd=0)
        dot.pack(side='left', padx=(0, 8))
        dot.create_oval(1, 1, 9, 9, fill=theme.MINT, outline='')
        tk.Label(bar, textvariable=self.status, bg=BG, fg=DIM, anchor='w',
                 font=theme.ui(11)).pack(side='left', fill='x', expand=True)

    def build_tabs(self):
        w = self.window
        self.tab_names = ['  查资料  ', ' SQL 查询 ', ' 来源与覆盖 ']
        self.tabs = TabBar(w, self.tab_names, self.show_tab, bg=BG)
        self.tabs.pack(fill='x', padx=20, pady=(0, 8))
        self.pages = tk.Frame(w, bg=BG)
        self.pages.pack(fill='both', expand=True, padx=20, pady=(0, 18))
        browse = tk.Frame(self.pages, bg=BG)
        advanced = tk.Frame(self.pages, bg=BG)
        coverage = tk.Frame(self.pages, bg=BG)
        self.page_frames = dict(zip(self.tab_names, (browse, advanced, coverage)))
        self.build_browse(browse)
        self.build_sql(advanced)
        self.coverage = self.make_text(coverage)
        self.coverage.master.pack(fill="both", expand=True)
        self.show_tab(self.tab_names[0])
        self.refresh()

    def show_tab(self, name):
        for page, frame in self.page_frames.items():
            if page == name:
                frame.pack(fill='both', expand=True)
            else:
                frame.pack_forget()
        self.tabs.current = name
        self.tabs.draw()

    def build_browse(self, browse):
        bar = tk.Frame(browse, bg=SURFACE, padx=14, pady=10)
        bar.pack(fill='x', pady=(0, 8))
        self.region = tk.StringVar(value="jp · 日服")
        ttk.Combobox(bar, textvariable=self.region, values=["jp · 日服", "cn · 国服", "en · 国际服"],
                     state="readonly", width=12).pack(side="left", padx=(0, 8))
        self.dataset = tk.StringVar(value="characters · 角色")
        self.dataset_box = ttk.Combobox(bar, textvariable=self.dataset, state="readonly", width=22)
        self.dataset_box.pack(side="left", padx=(0, 8))
        self.dataset_box.bind("<<ComboboxSelected>>", self.change_dataset)
        self.region.trace_add("write", self.change_region)
        self.character_path = tk.StringVar(value="风格：全部角色")
        self.back_button = RoundedButton(bar, '← 角色', self.back_to_characters, theme.CARD_HI, PINK,
                                         theme.ui(11), height=30)
        self.keyword = tk.StringVar()
        entry = ttk.Entry(bar, textvariable=self.keyword)
        self.keyword_entry = entry
        entry.pack(side="left", fill="x", expand=True, ipady=3, padx=8)
        entry.bind("<Return>", lambda e: self.search())
        RoundedButton(bar, '搜索', self.search, PINK, '#2a2036', theme.ui(11, 'bold'),
                      height=30).pack(side="left")
        hints = tk.Frame(browse, bg=BG)
        hints.pack(fill='x', padx=4, pady=(0, 6))
        tk.Label(hints, text="按名称、ID、角色名或原文内容搜索；不同服务器独立保存。选择角色后可查看其风格。",
                 bg=BG, fg=theme.MUTED, anchor="w", font=theme.ui(10),
                 justify='left').pack(fill='x')
        tk.Label(hints, textvariable=self.character_path, bg=BG, fg=PINK, anchor="w",
                 font=theme.ui(10, 'bold')).pack(fill='x', pady=(2, 0))
        panes = tk.PanedWindow(browse, orient="horizontal", bg=BG, sashwidth=6,
                               sashrelief='flat', borderwidth=0, showhandle=False)
        panes.pack(fill="both", expand=True)
        left = tk.Frame(panes, bg=CARD)
        right = tk.Frame(panes, bg=BG)
        panes.add(left, minsize=240, width=360)
        panes.add(right, minsize=360)
        self.tree = self.make_tree(left, ("id", "name"))
        self.tree.configure(show="tree headings", style="Quest.Browse.Treeview")
        self.tree.heading("#0", text="头像")
        self.tree.column("#0", width=76, minwidth=76, stretch=False)
        self.tree.heading("id", text="ID")
        self.tree.column("id", width=92, minwidth=70, stretch=False)
        self.tree.heading("name", text="名称")
        self.tree_photos = []
        self.tree.bind("<<TreeviewSelect>>", self.select)
        self.tree.bind("<Double-1>", self.open_character_styles)
        lower = tk.Frame(left, bg=CARD)
        lower.pack(fill="x")
        self.styles_button = RoundedButton(lower, '查看该角色的风格 →', self.open_character_styles,
                                           theme.CARD_HI, PINK, theme.ui(11), height=30)
        self.styles_button.pack(fill="x", pady=4, padx=6)
        paging = tk.Frame(lower, bg=CARD)
        paging.pack(fill="x", pady=(0, 6), padx=6)
        RoundedButton(paging, '上一页', lambda: self.page(-1), theme.CARD_HI, DIM, theme.ui(10),
                      height=26).pack(side="left")
        RoundedButton(paging, '下一页', lambda: self.page(1), theme.CARD_HI, DIM, theme.ui(10),
                      height=26).pack(side="right")
        self.page_label = tk.Label(paging, bg=CARD, fg=theme.MUTED, font=theme.ui(10))
        self.page_label.pack()
        self.right_tab_names = ['  技能与数值  ', '  原始数据（高级）  ']
        self.right_tabs = TabBar(right, self.right_tab_names, self.show_right, bg=BG)
        self.right_tabs.pack(fill='x', pady=(0, 6))
        self.right_pages = tk.Frame(right, bg=BG)
        self.right_pages.pack(fill='both', expand=True)
        self.summary = DetailCards(self.right_pages)
        tk.Label(self.summary.body, text='← 在左侧选择一个条目\n查看技能、数值与来源', bg=CARD,
                 fg=theme.MUTED, font=theme.ui(12), justify='left', anchor='w').pack(
            anchor='w', padx=16, pady=(30, 0))
        self.raw = self.make_text(self.right_pages)
        self.right_frames = {self.right_tab_names[0]: self.summary,
                             self.right_tab_names[1]: self.raw.master}
        self.show_right(self.right_tab_names[0])

    def show_right(self, name):
        for key, frame in self.right_frames.items():
            if key == name:
                frame.pack(fill='both', expand=True)
            else:
                frame.pack_forget()
        self.right_tabs.current = name
        self.right_tabs.draw()

    def build_sql(self, advanced):
        tk.Label(advanced, text="只读 SQLite · 单次最多 500 行 / 3 秒；支持 JOIN、聚合、JSON 查询。所有原始字段位于 raw_json。",
                 bg=BG, fg=theme.MUTED, font=theme.ui(11), anchor='w').pack(fill='x', padx=4, pady=(0, 8))
        box = tk.Frame(advanced, bg=CARD, padx=2, pady=2)
        box.pack(fill="x", padx=4)
        self.sql = tk.Text(box, height=8, bg=theme.mix(CARD, '#000000', .25), fg=FG,
                           insertbackground=FG, font=theme.mono(12), relief='flat',
                           borderwidth=0, padx=12, pady=10, highlightthickness=0)
        self.sql.pack(fill="x")
        self.sql.insert("1.0", EXAMPLE)
        row = tk.Frame(advanced, bg=BG)
        row.pack(fill='x', padx=4, pady=8)
        RoundedButton(row, "运行查询", self.run_sql, PINK, '#2a2036', theme.ui(11, 'bold'),
                      height=30).pack(side='right')
        self.sql_tree = self.make_tree(advanced, ("结果",))

    def make_text(self, parent):
        frame = tk.Frame(parent, bg=CARD)
        text = tk.Text(frame, wrap="word", bg=CARD, fg=FG, insertbackground=FG, relief="flat",
                       borderwidth=0, padx=16, pady=14, font=theme.ui(12),
                       selectbackground=theme.mix(CARD, PINK, .3), highlightthickness=0)
        scroll = ttk.Scrollbar(frame, command=text.yview)
        scroll.pack(side="right", fill="y")
        text.configure(yscrollcommand=scroll.set)
        text.pack(fill="both", expand=True)
        text.tag_configure("title", foreground=PINK, font=theme.ui(15, "bold"))
        text.tag_configure("head", foreground=theme.CYAN, font=theme.ui(12, "bold"))
        return text

    def make_tree(self, parent, columns):
        frame = tk.Frame(parent, bg=CARD)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=columns, show="headings", style="Quest.Treeview")
        vertical = ttk.Scrollbar(frame, command=tree.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        vertical.pack(side="right", fill="y")
        horizontal.pack(side="bottom", fill="x")
        tree.pack(fill="both", expand=True)
        for column in columns:
            tree.heading(column, text=column)
            tree.column(column, width=180, minwidth=80)
        return tree

    def set_text(self, widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.tag_add("title", "1.0", "1.end")
        widget.configure(state="disabled")

    def task(self, fn, done):
        def work():
            try:
                self.queue.put((done, fn(), None))
            except Exception as exc:
                self.queue.put((done, None, str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def pump(self):
        try:
            while True:
                callback, value, error = self.queue.get_nowait()
                if error:
                    self.status.set("未完成：" + error)
                callback(value, error)
        except queue.Empty:
            pass
        if self.window.winfo_exists():
            self.window.after(100, self.pump)

    def refresh(self):
        try:
            manifest = self.catalog.manifest()
        except FileNotFoundError:
            self.status.set("尚无本地资料，请点击「同步网站资料」")
            return
        available = {s["table"] for s in manifest["sources"].values()}
        datasets = [name for name in BROWSE_DATASETS if name in available]
        self.dataset_box.configure(values=[f"{name} · {BROWSE_DATASETS[name]}" for name in datasets])
        if datasets and self.dataset.get().split(" · ")[0] not in datasets:
            self.dataset.set(f"{datasets[0]} · {BROWSE_DATASETS[datasets[0]]}")
            self.character_filter = None
            self.back_button.pack_forget()
            self.character_path.set("选择角色，查看其风格" if datasets[0] == "characters" else "风格：全部角色" if datasets[0] == "styles" else "")
            self.styles_button.configure(state="normal" if datasets[0] == "characters" else "disabled")
        unavailable = len(manifest["errors"])
        self.status.set(f"本地资料快照 {manifest['created'][:10]} · 查询无需联网" +
                        (f" · {unavailable} 个来源缺失（详见「来源与覆盖」）" if unavailable else ""))
        counts = {}
        for source in manifest["sources"].values():
            key = source["region"] + "/" + source["table"]
            counts[key] = counts.get(key, 0) + 1
        report = ("来源与覆盖报告\n\nhttps://hbr.quest/\nhttps://master.hbr.quest/v1/\n\n"
                  + f"快照 {manifest['created']} · {len(manifest['sources'])} 个已获取来源 · {unavailable} 个未获取来源")
        if unavailable and all("HTTP Error 404:" in error for error in manifest["errors"].values()):
            report += "\n未获取来源均返回 404，表示对应路径未提供数据；不代表本地资料查询失败。"
        report += "\n\n范围：站点公开模块引用的 JSON 表及表中列出的详细资料。头像与敌人图标可通过「同步头像」独立缓存；不下载立绘、音视频。无法发现的服务器文件不声称已覆盖。\n原始 JSON、页面脚本、SHA256、下载时间与历史版本均保存在 data/quest。\n\n"
        report += "\n".join(f"{key}: {count} 文件" for key,count in sorted(counts.items()))
        report += "\n\n不可用来源（不隐瞒缺项）：\n" + "\n".join(f"{url}\n  {error}" for url,error in manifest["errors"].items())
        report += "\n\nSQL 表：sources, records, translations, skills, skill_parts, skill_hits, skill_elements\n视图：characters, styles, enemies, style_skills, skill_catalog, skill_damage\n关联：skills.skill_key = skill_parts.skill_key；source_url → sources.url。\n同一技能可能出现在多个来源；skill_catalog / skill_damage 限定技能主表，仍保留表内条件变体；全部来源用 skills。"
        portraits = self.details.assets.index()
        counts = Counter((key.split('/')[1],value['status']) for key,value in portraits['records'].items())
        report += "\n\n头像覆盖（关联记录数，多条记录可共用同一图片）：\n"
        report += "\n".join(f"{LABELS.get(category,category)} · {status}: {count}" for (category,status),count in sorted(counts.items()))
        report += "\n详细图像 URL、失败原因和本地路径见 data/quest/portraits.json。"
        self.set_text(self.coverage, report)
        self.search()

    def update(self):
        if self.busy:
            return
        self.busy = True
        self.update_button.configure(text='同步中…')
        def progress(text):
            self.queue.put((lambda value, error: self.status.set(value), text, None))
        def done(value, error):
            self.busy = False
            self.update_button.configure(text='同步网站资料')
            if not error:
                self.refresh()
        def download():
            stage = self.catalog.root / "staging.json"
            resume = False
            if stage.exists():
                pending = json.loads(stage.read_bytes())
                try:
                    current = self.catalog.manifest()
                except FileNotFoundError:
                    current = {}
                resume = (pending.get("created") != current.get("created") or
                          pending.get("database") != current.get("database") or
                          any("HTTP Error 404:" not in e for e in pending.get("errors", {}).values()))
            return sync(self.catalog.root, progress=progress, resume=resume)
        self.task(download, done)

    def change_dataset(self, event=None):
        self.character_filter = None
        self.back_button.pack_forget()
        self.character_path.set("风格：全部角色" if self.dataset.get().startswith("styles ·") else "选择角色，查看其风格" if self.dataset.get().startswith("characters ·") else "")
        self.styles_button.configure(state="normal" if self.dataset.get().startswith("characters ·") else "disabled")
        self.search()

    def change_region(self, *args):
        if self.character_filter:
            self.character_filter = None
            self.back_button.pack_forget()
        if hasattr(self, "character_path"):
            self.character_path.set("风格：全部角色" if self.dataset.get().startswith("styles ·") else "选择角色，查看其风格" if self.dataset.get().startswith("characters ·") else "")
        if hasattr(self, "tree"):
            self.search()

    def back_to_characters(self):
        self.character_filter = None
        self.dataset.set("characters · 角色")
        self.back_button.pack_forget()
        self.character_path.set("选择角色，查看其风格")
        self.styles_button.configure(state="normal")
        self.keyword.set("")
        self.search()

    def page(self, direction):
        self.offset = max(0, self.offset + direction * 250)
        self.search(reset=False)

    def search(self, reset=True):
        if reset:
            self.offset = 0
        self.generation += 1
        self.selection_generation += 1
        generation = self.generation
        region, dataset = self.region.get().split(" · ")[0], self.dataset.get().split(" · ")[0]
        keyword = self.keyword.get()
        pattern = "%" + keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        offset = self.offset
        character_filter = self.character_filter if dataset == "styles" and self.character_filter and self.character_filter[0] == region else None
        def done(result, error):
            if error or generation != self.generation:
                return
            from PIL import ImageTk
            rows, pictures = result
            self.tree.delete(*self.tree.get_children())
            self.tree_photos.clear()
            self.keys = {}
            for index, row in enumerate(rows):
                self.keys[str(index)] = row[0]
                photo = ImageTk.PhotoImage(pictures[row[1]],master=self.tree) if row[1] in pictures else None
                if photo:self.tree_photos.append(photo)
                self.tree.insert("", "end", iid=str(index), image=photo or "",values=(row[1], row[2] or row[3]))
            self.page_label.configure(text=f"第 {offset//250+1} 页 · {len(rows)} 条")
        def find():
            from PIL import Image
            if character_filter:
                _, rows, _ = self.catalog.character_styles(region, character_filter[1], keyword, limit=250, offset=offset)
            else:
                _, rows, _ = self.catalog.query("SELECT record_key,id,COALESCE(NULLIF(name_zh,''),name),label FROM records WHERE region=? AND dataset=? AND (raw_json LIKE ? ESCAPE '\\' OR name_zh LIKE ? ESCAPE '\\') ORDER BY ordinal LIMIT 250 OFFSET ?", (region,dataset,pattern,pattern,offset))
            paths = self.details.assets.paths(region,dataset,[row[1] for row in rows])
            pictures = {}
            for entity_id,path in paths.items():
                try:
                    with Image.open(path) as source:
                        picture = source.convert("RGBA")
                        picture.thumbnail((48,48),Image.Resampling.LANCZOS)
                        pictures[entity_id] = picture
                except OSError:
                    pass
            return rows,pictures
        self.task(find, done)

    def select(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return
        key = self.keys[selected[0]]
        self.selection_generation += 1
        generation = self.selection_generation
        def done(record, error):
            if error or generation != self.selection_generation:
                return
            self.summary.render(record)
            self.set_text(self.raw, json.dumps(record["raw"], ensure_ascii=False, indent=2))
            self.show_right(self.right_tab_names[0])
        self.task(lambda: self.details.record(key), done)

    def open_character_styles(self, event=None):
        if self.dataset.get().split(" · ")[0] != "characters":
            return
        selected = self.tree.selection()
        if not selected:
            return
        key = self.keys.get(selected[0])
        if not key:
            return
        region = self.region.get().split(" · ")[0]
        self.selection_generation += 1
        generation = self.selection_generation
        def done(result, error):
            if (error or generation != self.selection_generation or not result
                    or self.dataset.get().split(" · ")[0] != "characters"
                    or self.region.get().split(" · ")[0] != region):
                return
            label, name = result
            self.character_filter = (region, label, name)
            self.dataset.set("styles · 风格")
            self.styles_button.configure(state="disabled")
            self.keyword.set("")
            self.character_path.set(f"角色：{name}  →  风格")
            self.back_button.pack(side="left", padx=(0, 8), before=self.keyword_entry)
            self.search()
        def find_character():
            _, rows, _ = self.catalog.query("SELECT label,COALESCE(NULLIF(name_zh,''),NULLIF(name,''),label) FROM records WHERE record_key=?", (key,))
            return rows[0] if rows else None
        self.task(find_character, done)

    def update_assets(self):
        if self.asset_busy:
            return
        self.asset_busy = True
        self.asset_button.configure(text='同步中…')
        def progress(text):
            self.queue.put((lambda value, error:self.status.set(value), text, None))
        def done(result, error):
            self.asset_busy = False
            self.asset_button.configure(text='同步头像')
            if not error:
                self.refresh()
                self.status.set("头像同步完成；缺失资源已记录，可离线使用已缓存头像")
        self.task(lambda: sync_portraits(self.catalog.root, progress=progress),done)

    def run_sql(self):
        sql = self.sql.get("1.0", "end").strip()
        def done(result, error):
            if error:
                return
            columns, rows, truncated = result
            tree = self.sql_tree
            tree.delete(*tree.get_children())
            keys = [str(i) for i in range(len(columns))]
            tree.configure(columns=keys)
            for key, title in zip(keys, columns):
                tree.heading(key, text=title)
                tree.column(key, width=160, minwidth=70)
            for row in rows:
                tree.insert("", "end", values=["NULL" if v is None else v for v in row])
            self.status.set(f"查询成功 · {len(rows)} 行" + ("（仅显示前 500 行，请缩小条件）" if truncated else ""))
        self.task(lambda: self.catalog.query(sql), done)


if __name__ == "__main__":
    from hbr_live_app.windows import set_dpi_aware
    set_dpi_aware()
    root = tk.Tk()
    root.withdraw()
    window = LibraryWindow(root)
    window.window.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
