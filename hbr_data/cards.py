"""Rounded, scrollable record and skill cards; no JSON syntax in normal details."""
import tkinter as tk
from tkinter import ttk
from hbr_live_app import theme
from hbr_live_app.components import RoundedCard

BG, CARD, FG, DIM, PINK = theme.BG, theme.CARD, theme.FG, theme.DIM, theme.PINK
WORDS = {"str":"力量","dex":"灵巧","wis":"智慧","spr":"精神","luk":"运气","con":"体力",
         "Attacker":"攻击手","Breaker":"破盾手","Blaster":"破坏手","Buffer":"增益手","Debuffer":"减益手","Healer":"治疗者","Defender":"守护者",
         "Slash":"斩","Stab":"突","Strike":"打","Fire":"火","Ice":"冰","Thunder":"雷","Light":"光","Dark":"暗",
         "AttackSkill":"攻击","DefenseDown":"防御降低","AttackUp":"攻击提升","Heal":"回复",
         "HealDp":"DP 回复","HealHp":"HP 回复","CriticalRateUp":"暴击率提升","CriticalDamageUp":"暴击伤害提升",
         "Single":"单体","All":"全体","Self":"自身","Main":"主伤害","Before":"命中前","After":"命中后"}


def number(value):
    if value is None:
        return "未提供"
    if isinstance(value,(int,float)):
        return f"{value:,.6f}".rstrip("0").rstrip(".")
    return str(value)


def ratios(hits):
    return " + ".join(number(hit.ratio) for hit in hits)


def friendly(value):
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, dict):
        return "；".join(f"{WORDS.get(k,k)}：{friendly(v)}" for k,v in value.items())
    if isinstance(value,(tuple,list)):
        return "、".join(friendly(v) for v in value) or "—"
    return WORDS.get(str(value),number(value))


# Explicit source types only: unfamiliar effects remain in "其他", never guessed.
DAMAGE_TYPES = {"AttackSkill", "PenetrationCriticalAttack", "DamageRateChangeAttackSkill",
                "TokenAttack", "AttackByOwnDpRate", "AttackBySp", "FixedHpDamageRate",
                "SelfDamage"}
BUFF_TYPES = {"AttackUp", "AttackUpIncludeNormal", "DefenseUp", "CriticalRateUp",
              "CriticalDamageUp", "MindEye", "BuffCharge", "Morale",
              "Funnel", "DamageRateUp", "ToughnessUpValue", "AllStatusUpValue",
              "GiveAttackBuffUp", "FightingSpirit", "OverDrivePointUp", "TokenSet"}
DEBUFF_TYPES = {"DefenseDown", "AttackDown", "Fragile", "ResistDown",
                "ResistDownOverwrite", "HealDown", "GiveDebuffUp",
                "OverDrivePointDown", "Provoke", "StunRandom",
                "ConfusionRandom", "ImprisonRandom", "Misfortune"}
EFFECT_GROUPS = (("伤害", DAMAGE_TYPES), ("增益", BUFF_TYPES), ("减益", DEBUFF_TYPES))


def effect_category(effect):
    return next((label for label, kinds in EFFECT_GROUPS if effect.kind in kinds), "其他")


def group_effects(effects):
    """Group for display only; retain each part's source index and payload."""
    return [(category, [effect for effect in effects if effect_category(effect) == category])
            for category in ("伤害", "增益", "减益", "其他")
            if any(effect_category(effect) == category for effect in effects)]


def destruction_summary(effects):
    """Keep separate attack parts separate; zero is known, None is unknown."""
    attacks = [effect for effect in effects if effect_category(effect) == "伤害"]
    values = ["未提供" if effect.destruction_multiplier is None else
              "×" + number(effect.destruction_multiplier) for effect in attacks]
    if len(values) == 1:
        return values[0]
    return "；".join(f"效果 {effect.index+1}：{value}"
                     for effect, value in zip(attacks, values))


class DetailCards(tk.Frame):
    def __init__(self,parent):
        super().__init__(parent,bg=BG)
        self.canvas = tk.Canvas(self,bg=BG,highlightthickness=0)
        scroll = ttk.Scrollbar(self,command=self.canvas.yview)
        scroll.pack(side="right",fill="y")
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.pack(fill="both",expand=True)
        self.body = tk.Frame(self.canvas,bg=BG)
        self.slot = self.canvas.create_window(0,0,window=self.body,anchor="nw")
        self.canvas.bind("<Configure>",lambda e:self.canvas.itemconfigure(self.slot,width=e.width))
        self.body.bind("<Configure>",lambda e:self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.photos = []
        self.card_count = 0

    def label(self,parent,text,size=10,color=FG,bold=False):
        label = tk.Label(parent,text=text,bg=parent.cget("bg"),fg=color,justify="left",anchor="w",
                         font=theme.ui(round(size*1.5),"bold" if bold else "normal"))
        label.pack(fill="x",pady=3)
        label.bind("<Configure>",lambda e:label.configure(wraplength=max(100,e.width-8)) if str(label.cget("wraplength")) != str(max(100,e.width-8)) else None)
        return label

    def card(self,title):
        shell = RoundedCard(self.body,background=CARD)
        shell.pack(fill="x",padx=10,pady=7)
        self.label(shell.content,title,13,PINK,True)
        return shell.content

    def row(self,parent,title,value):
        line = tk.Frame(parent,bg=parent.cget("bg"))
        line.pack(fill="x",pady=2)
        tk.Label(line,text=title,bg=line.cget("bg"),fg=DIM,anchor="nw",width=12,
                 font=theme.ui(13)).pack(side="left",anchor="n")
        self.label(line,value,10,FG,True)

    def fold(self,parent,title,fill):
        panel = tk.Frame(parent,bg=parent.cget("bg"))
        panel.pack(fill="x",pady=3)
        content = tk.Frame(panel,bg=parent.cget("bg"))
        opened = False
        built = False
        def toggle():
            nonlocal opened,built
            opened = not opened
            button.configure(text=("▾  " if opened else "▸  ")+title)
            if opened:
                if not built:
                    fill(content);built=True;self.bind_wheel(content)
                content.pack(fill="x",padx=7,pady=4)
            else:
                content.pack_forget()
        button = tk.Button(panel,text="▸  "+title,command=toggle,bg=parent.cget("bg"),fg=PINK,
                           relief="flat",anchor="w",font=theme.ui(13,"bold"),cursor="hand2",
                           activebackground=parent.cget("bg"),activeforeground=theme.FG,borderwidth=0,
                           highlightthickness=0)
        button.pack(fill="x")

    def hit_rows(self,parent,hits,title="逐 Hit 倍率"):
        if not hits:
            self.row(parent,title,"暂缺 · 保留空白，后续可录入")
            return
        text = ratios(hits)
        def fill(frame):
            self.label(frame,text,10,"#9ee4ef",True)
            for hit in hits:
                self.row(frame,f"第 {hit.index} Hit",f"×{number(hit.ratio)} · {WORDS.get(hit.kind,hit.kind) or '未标类型'}")
        if len(hits)>6:
            self.fold(parent,f"{title} · {len(hits)} 段 · {text}",fill)
        else:
            self.row(parent,title,text)
            if any(hit.kind != "Main" for hit in hits):
                self.fold(parent,"命中类型与顺序",fill)

    def render_skill(self,skill,index):
        self.card_count += 1
        frame = self.card(f"✦  {index}  {skill.name}")
        if skill.description:
            self.label(frame,skill.description,10)
        if any(effect_category(effect) == "伤害" for effect in skill.effects):
            self.row(frame,"技能 Hit 数",number(skill.hit_count) if skill.hit_count is not None and skill.hit_count>=0 else "来源未定义")
        self.row(frame,"SP 消耗",number(skill.sp_cost))
        destruction = destruction_summary(skill.effects)
        if destruction:
            self.row(frame,"技能破坏倍率",destruction)
            self.label(frame,"技能来源系数；实际破坏率增量还需结合敌人系数、增益与命中段数。",9,DIM)
        if skill.hits and any(effect_category(effect) == "伤害" for effect in skill.effects):
            self.hit_rows(frame,skill.hits,"技能伤害逐 Hit")
        elif any(effect_category(effect) == "伤害" for effect in skill.effects) and (skill.hit_count or 0) > 0:
            self.row(frame,"技能伤害逐 Hit","来源未提供分配，不能按 Hit 数推算")
        elif skill.hits:
            self.row(frame,"来源命中标记","、".join(f"{hit.index}: {WORDS.get(hit.kind,hit.kind) or '未标类型'}" for hit in skill.hits))
        for category, effects in group_effects(skill.effects):
            def fill(group, effects=effects, category=category):
                for effect in effects:
                    self.render_effect(group,effect,category)
            if len(skill.effects) == 1:
                self.label(frame,category,10,PINK,True)
                fill(frame)
            else:
                self.fold(frame,f"{category} · {len(effects)} 项",fill)
        def meta(panel):
            for key,label in (("id","技能 ID"),("label","来源标签"),("max_level","等级上限"),("use_count","使用次数"),("cond","技能条件"),("overwrite_cond","替换条件")):
                self.row(panel,label,friendly(skill.raw.get(key)))
        self.fold(frame,"技能补充信息",meta)

    def render_effect(self, parent, effect, category):
        area = tk.Frame(parent,bg=theme.SURFACE,padx=10,pady=8)
        area.pack(fill="x",pady=5)
        self.label(area,f"来源效果 {effect.index+1} · {WORDS.get(effect.kind,effect.kind) or '未标类型'}",10,"#9ee4ef",True)
        if category == "伤害":
            self.row(area,"基础威力"," ～ ".join(number(v) for v in effect.power) or "未提供")
            self.row(area,"上限属性差",number(effect.stat_difference))
            weights = " + ".join(f"{WORDS.get(k,k)} × {number(v)}" for k,v in effect.weights if v)
            self.row(area,"属性权重",weights or "无属性权重")
            self.row(area,"攻击属性"," · ".join(WORDS.get(v,v) for v in (effect.physical_type,*effect.elements) if v) or "无")
            self.row(area,"DP 倍率","×"+number(effect.dp_multiplier))
            self.row(area,"HP 倍率","×"+number(effect.hp_multiplier))
            self.row(area,"破坏倍率","×"+number(effect.destruction_multiplier))
            if effect.hits:
                self.hit_rows(area,effect.hits,"该效果命中信息")
        elif category in {"增益", "减益"}:
            self.row(area,"效果数值"," ～ ".join(number(v) for v in effect.power) or "未提供")
            if effect.hits:
                self.row(area,"施加时机","、".join(f"{WORDS.get(hit.kind,hit.kind) or '未标类型'}（标记 {hit.index}）" for hit in effect.hits))
        else:
            self.row(area,"来源数值"," ～ ".join(number(v) for v in effect.power) or "未提供")
            if effect.hits:
                self.row(area,"触发时机","、".join(f"{WORDS.get(hit.kind,hit.kind) or '未标类型'}（标记 {hit.index}）" for hit in effect.hits))
        if effect.condition:
            self.row(area,"生效条件",effect.condition)
        def extra(panel):
            self.row(panel,"等级成长",friendly(effect.growth))
            for key in ("target_type","value","hit_condition","target_condition","effect"):
                if effect.raw.get(key):
                    self.row(panel,{"target_type":"作用对象","value":"附加数值","effect":"特殊效果","hit_condition":"命中条件","target_condition":"目标条件"}[key],friendly(effect.raw[key]))
            if category != "伤害" and effect.hits:
                self.row(panel,"来源命中标记","、".join(f"{hit.index}: {number(hit.ratio)}" for hit in effect.hits))
        self.fold(area,"原始参数与条件",extra)

    def render(self,record):
        for child in self.body.winfo_children():
            child.destroy()
        self.photos.clear();self.card_count=0
        data = record["raw"]
        frame = self.card(record.get("name") or "资料")
        header = tk.Frame(frame,bg=CARD)
        header.pack(fill="x")
        portrait = record.get("portrait") or {}
        if portrait.get("local_path"):
            try:
                from PIL import Image,ImageTk
                with Image.open(portrait["local_path"]) as source:
                    picture = source.convert("RGBA");picture.thumbnail((100,100),Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(picture,master=self)
                self.photos.append(photo)
                tk.Label(header,image=photo,bg=CARD).pack(side="left",anchor="n",padx=(0,12),pady=5)
            except (OSError,ValueError):
                self.label(frame,"头像暂不可用",9,DIM)
        elif record["dataset"] in {"styles","characters","enemies"}:
            self.label(frame,"图标未公开或尚未缓存",9,DIM)
        if isinstance(data,dict):
            info = tk.Frame(header,bg=CARD)
            info.pack(side="left",fill="x",expand=True)
            def identity(panel):
                for key,label in (("chara","角色"),("tier","稀有度"),("role","定位"),("team","部队")):
                    if data.get(key):self.label(panel,f"{label}  {friendly(data[key])}",9,DIM)
            if record["dataset"] == "skills":
                owners = record.get("owners", [])
                if owners:
                    self.label(info, "所属角色：" + "、".join(dict.fromkeys(owner[1] for owner in owners)), 9, DIM)
                    self.label(info, "关联风格：" + "、".join(dict.fromkeys(owner[3] for owner in owners)), 9, DIM)
                else:
                    self.label(info, "未找到明确的角色—风格关联；不根据技能名称猜测。", 9, DIM)
                self.fold(info,"来源标注",identity)
            else:
                identity(info)
            if record["dataset"] == "enemies":
                self.row(frame,"敌人类型","Boss" if (data.get("flags") or {}).get("is_boss") else "普通敌人")
                for key,label in (("dp","初始 DP"),("hp","初始 HP")):
                    self.row(frame,label,number((data.get("base_param") or {}).get(key)))
            if not record["skills"] and data.get("desc"):
                self.label(frame,data["desc"])
        for index,skill in enumerate(record["skills"],1):
            self.render_skill(skill,index)
        extras = self.card("资料备注")
        self.label(extras,"威力范围尚未代入等级、增益和敌人参数；逐 Hit 倍率只显示来源提供的 hits.power_ratio，空值不推算。",9,DIM)
        def more(panel):
            self.row(panel,"来源",record["source"])
            self.row(panel,"服务器",record["region"])
            if isinstance(data,dict):
                for key,value in data.items():
                    if key not in {"skills","parts","hits"}:
                        self.row(panel,key,friendly(value))
        self.fold(extras,"来源与其他资料",more)
        self.canvas.yview_moveto(0)
        self.bind_wheel(self.body)

    def bind_wheel(self,widget):
        widget.bind("<MouseWheel>",lambda event:self.canvas.yview_scroll(-int(event.delta/120),"units"))
        for child in widget.winfo_children():
            self.bind_wheel(child)
