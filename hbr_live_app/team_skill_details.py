"""Use the shared local skill catalog; names are not skill identities."""
import tkinter as tk
from . import theme
from .damage_autofill import catalog_skill


def show_skill(parent, observed, lookup=None):
    from hbr_data.cards import DetailCards
    from hbr_data.details import skill_detail
    lookup = lookup or catalog_skill
    label = observed.get('label')
    raw = lookup(label) if label else {}
    window = tk.Toplevel(parent)
    window.title('技能详情 · '+(observed.get('name') or label or '未识别'))
    window.geometry('760x720')
    window.minsize(620, 450)
    window.configure(bg=theme.BG)
    window.transient(parent)
    level = observed.get('level')
    tk.Label(window, text=f"档案技能等级  Lv.{level if level is not None else '?'}", bg=theme.BG,
             fg=theme.CYAN, font=theme.ui(13,'bold')).pack(anchor='w',padx=18,pady=(12,4))
    tk.Label(window, text='详情来自本地技能资料库，威力为资料基础值，非当前等级结算伤害。',bg=theme.BG,
             fg=theme.DIM,font=theme.ui(10),wraplength=680,justify='left').pack(anchor='w',padx=18,pady=(0,8))
    cards=DetailCards(window)
    cards.pack(fill='both',expand=True)
    if raw:
        cards.render_skill(skill_detail(raw),1)
        cards.bind_wheel(cards.body)
    else:
        body=cards.card('暂无可唯一匹配的技能资料')
        cards.label(body,'技能标识：'+(label or '未读取'),10)
        cards.label(body,'可能是资料未收录或存在同标识的不同版本。不会用同名技能或基础技能替代当前变体。',10)
    return window
