"""Six stable portrait slots; live position changes only update highlights."""
import tkinter as tk

from . import theme
from .components import RoundedCard, RoundedButton
from .portraits import Portraits
from .statuses import status_details
from .status_groups import StatusGroups




class PlayerPanel(tk.Frame):
    def __init__(self, parent, show_details):
        super().__init__(parent, bg=parent.cget('bg'))
        self.show_details = show_details
        self.portraits = Portraits(self, size=58)
        self.order = []
        self.tiles = {}
        self.players = {}
        self.selected = None
        self.previous_gauge = None
        self.configure(bg=parent.cget('bg'))
        self.gauge = tk.Label(self, bg=self.cget('bg'), fg=theme.GOLD, anchor='w',
                              font=theme.ui(11), wraplength=320)
        self.gauge.pack(fill='x', pady=(0, 6))
        self.strip = tk.Frame(self, bg=self.cget('bg'))
        self.strip.pack(fill='both', expand=True)
        for col in range(3):
            self.strip.columnconfigure(col, weight=1, uniform='portraits')
        for row in range(2):
            self.strip.rowconfigure(row, weight=1, uniform='portraits')
        self.hint = tk.Label(self, text='点击头像查看状态 · 亮框为前排', bg=self.cget('bg'), fg=theme.DIM,
                             anchor='w', font=theme.ui(10))
        self.hint.pack(fill='x', pady=(8, 4))
        self.detail = tk.Frame(self, bg=self.cget('bg'))
        self.detail_card = RoundedCard(self.detail, background=theme.CARD, outline=theme.LINE,
                                       pad=(14, 12), stretch=True)
        self.detail_card.pack(fill='both', expand=True)
        body = self.detail_card.content
        self.caption = tk.Label(body, bg=theme.CARD, fg=theme.FG, anchor='w', justify='left', font=theme.ui(12),
                                wraplength=260)
        self.caption.pack(fill='x')
        head = tk.Frame(body, bg=theme.CARD)
        head.pack(fill='x', pady=(6, 2))
        self.pools = tk.Label(head, bg=theme.CARD, fg=theme.CYAN, anchor='w', font=theme.ui(11))
        self.pools.pack(side='left')
        RoundedButton(head, '完整详情', self.details, theme.CARD_HI, theme.DIM, theme.ui(11),
                      height=28).pack(side='right')
        self.groups = StatusGroups(body, self.status_details)
        self.groups.pack(fill='x', pady=(4, 0))
        self.detail.bind('<Configure>', lambda e: self.caption.configure(wraplength=max(120, e.width - 24)))

    def reset(self):
        for tile in self.tiles.values():
            tile['frame'].destroy()
        self.tiles.clear();self.order=[];self.selected=None;self.players={}
        self.previous_gauge=None
        self.gauge.configure(text='')
        self.detail.pack_forget()

    def update_state(self, players, gauge):
        self.players = {p['actor_id']:p for p in players}
        # Freeze existing slots; a formation swap must never reorder portraits.
        initial_order = {pos:i for i,pos in enumerate((1,0,2,4,3,5))}
        for player in sorted(players,key=lambda p:initial_order.get(p.get('actor_position'),99)):
            key=player['actor_id']
            if key not in self.order:self.order.append(key)
        for key in self.order:
            p=self.players.get(key)
            if key not in self.tiles:
                frame=RoundedCard(self.strip, background=theme.CARD, outline=theme.LINE,
                                  radius=18, pad=(10, 10), stretch=True)
                index=self.order.index(key);frame.grid(row=index//3,column=index%3,sticky='nsew',padx=5,pady=5)
                holder=tk.Frame(frame.content,bg=theme.CARD)
                holder.pack(expand=True)
                portrait=tk.Label(holder,bg=theme.CARD,cursor='hand2')
                portrait.pack(pady=(0, 6))
                name=tk.Label(holder,bg=theme.CARD,fg=theme.FG,font=theme.ui(11,'bold'),
                              anchor='center',wraplength=120,justify='center')
                name.pack(fill='x')
                badge=tk.Label(holder,bg=theme.CARD,fg=theme.DIM,font=theme.ui(10))
                badge.pack(pady=(3, 0))
                for widget in (holder,frame,portrait,name,badge):
                    widget.configure(cursor='hand2')
                    widget.bind('<Button-1>',lambda e,k=key:self.select(k))
                self.tiles[key]=dict(frame=frame,portrait=portrait,name=name,badge=badge,signature=None)
            tile=self.tiles[key]
            signature=None if not p else (p.get('style_label'),p.get('actor'),p.get('actor_position'),key==self.selected)
            if tile['signature']==signature:continue
            tile['signature']=signature
            pos=p.get('actor_position') if p else None
            front=pos in (0,1,2)
            selected=key==self.selected
            tile['frame'].configure(outline=theme.PINK if selected else (theme.CYAN if front else theme.LINE))
            tile['frame'].draw()
            photo=self.portraits.get(p.get('style_label')) if p else None
            tile['portrait'].configure(image=photo or '',text='' if photo else (p.get('actor','未知角色') if p else '暂不可读'),
                                       fg=theme.MUTED,font=theme.ui(10))
            tile['name'].configure(text=p.get('actor','') if p else '',
                                   fg=theme.FG if p else theme.MUTED)
            tile['badge'].configure(text=('前排 · '+{1:'左',0:'中',2:'右'}[pos]) if front else '后排' if p else '暂不可读',
                                     fg=theme.CYAN if front else theme.MUTED)
        if gauge != self.previous_gauge:
            self.previous_gauge=gauge
            text='' if not gauge else f'{gauge["name"]}元素量表 {gauge["value"]/gauge["maximum"]:.0%}'
            self.gauge.configure(text=text)
        self.update_details()

    def select(self,key):
        self.selected=None if self.selected==key else key
        self.update_state(list(self.players.values()),self.previous_gauge)

    def update_details(self):
        p=self.players.get(self.selected)
        if not p:
            self.detail.pack_forget();return
        self.detail.pack(fill='x',pady=(8,0))
        pools=[]
        for pool in ('dp','hp'):
            value,maximum=p.get(pool),p.get(pool+'_max')
            pools.append(f'{pool.upper()} {value:,}'+(f' / {maximum:,}' if maximum else '') if value is not None else pool.upper()+' —')
        self.caption.configure(text=p['actor']+' / '+p.get('style_name',''))
        self.pools.configure(text='   '.join(pools))
        self.groups.update_state(p)

    def status_details(self,status):
        self.show_details(status['name'],status_details(dict(statuses_available=True,statuses=[status])))

    def details(self):
        player=self.players.get(self.selected)
        if not player:return
        text=player.get('style_name','')+'\n\n'+status_details(player)
        text+='\n\n内部预结算值（非下回合伤害预测）：'
        text+=f'\nexpected DP：{player.get("expected_dp", "未读取")}\nexpected HP：{player.get("expected_hp", "未读取")}'
        self.show_details(player['actor']+' · 当前状态',text)
