"""Six stable portrait slots; live position changes only update highlights."""
import tkinter as tk
from .portraits import Portraits
from .statuses import status_details
from .status_groups import StatusGroups

BG, CARD, FG, DIM = '#201d32', '#302b46', '#f7f0ff', '#bdb1d4'


class PlayerPanel(tk.Frame):
    def __init__(self, parent, show_details):
        super().__init__(parent, bg=BG)
        self.show_details = show_details
        self.portraits = Portraits(self)
        self.order = []
        self.tiles = {}
        self.players = {}
        self.selected = None
        self.previous_gauge = None
        self.gauge = tk.Label(self, bg=BG, fg='#ffd398', anchor='w',wraplength=280)
        self.gauge.pack(fill='x',pady=4)
        self.strip = tk.Frame(self,bg=BG)
        self.strip.pack(fill='x',pady=8)
        for col in range(3):self.strip.columnconfigure(col,weight=1,uniform='portraits')
        self.hint = tk.Label(self,text='点击头像查看状态 · 亮框为前排',bg=BG,fg=DIM,anchor='w')
        self.hint.pack(fill='x',pady=(0,8))
        self.detail = tk.Frame(self,bg=CARD,padx=10,pady=8)
        self.caption = tk.Label(self.detail,bg=CARD,fg=FG,anchor='w',justify='left',wraplength=260)
        self.caption.pack(fill='x')
        tk.Button(self.detail,text='完整详情',bg=CARD,fg=DIM,relief='flat',command=self.details).pack(anchor='e')
        self.groups = StatusGroups(self.detail,self.status_details)
        self.groups.pack(fill='x')
        self.detail.bind('<Configure>',lambda e:self.caption.configure(wraplength=max(120,e.width-24)))

    def reset(self):
        for tile in self.tiles.values():tile['frame'].destroy()
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
                frame=tk.Frame(self.strip,bg=CARD,highlightthickness=2,highlightbackground='#50415f',padx=8,pady=6)
                index=self.order.index(key);frame.grid(row=index//3,column=index%3,sticky='nsew',padx=4,pady=4)
                portrait=tk.Label(frame,bg=CARD,cursor='hand2')
                portrait.pack()
                badge=tk.Label(frame,bg=CARD,fg=DIM,font=('Microsoft YaHei UI',-11))
                badge.pack()
                for widget in (frame,portrait,badge):widget.bind('<Button-1>',lambda e,k=key:self.select(k))
                self.tiles[key]=dict(frame=frame,portrait=portrait,badge=badge,signature=None)
            tile=self.tiles[key]
            signature=None if not p else (p.get('style_label'),p.get('actor'),p.get('actor_position'),key==self.selected)
            if tile['signature']==signature:continue
            tile['signature']=signature
            pos=p.get('actor_position') if p else None
            front=pos in (0,1,2)
            tile['frame'].configure(highlightbackground='#83e5ed' if front else '#50415f',
                                    bg='#394758' if key==self.selected else CARD)
            photo=self.portraits.get(p.get('style_label')) if p else None
            tile['portrait'].configure(image=photo or '',text='' if photo else (p.get('actor','未知角色') if p else '暂不可读'))
            tile['badge'].configure(text=('前排 · '+{1:'左',0:'中',2:'右'}[pos]) if front else '后排' if p else '暂不可读',
                                     fg='#83e5ed' if front else DIM)
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
        self.detail.pack(fill='x',pady=6)
        pools=[]
        for pool in ('dp','hp'):
            value,maximum=p.get(pool),p.get(pool+'_max')
            pools.append(f'{pool.upper()} {value:,}'+(f' / {maximum:,}' if maximum else '') if value is not None else pool.upper()+' —')
        self.caption.configure(text=p['actor']+' / '+p.get('style_name','')+'\n'+'   '.join(pools))
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
