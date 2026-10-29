"""Bounded, filterable event console with semantic highlighting."""
from collections import deque
import re
import tkinter as tk
from tkinter import ttk

from . import ui_theme as t


def classify(kind, message):
    if kind in ('error','cleanup_error'): return 'ERROR','error','Errors'
    if kind=='edit_error': return 'WARN','warn','Errors'
    if kind=='route_review': return 'PAUSE','warn','Routes'
    if kind=='decision': return 'ROUTE','route','Routes'
    if kind=='radio':
        if 'ACK' in message: return 'ACK','success','Network'
        if 'MEC →' in message: return 'RECV','network','Network'
        if 'detected' in message: return 'DETECT','warn','Network'
        return 'RADIO','network','Network'
    if kind=='report': return 'REPORT','success','Network'
    return 'INFO','info','System'


class LogConsole(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent,style='Editor.TFrame')
        from .desktop_ui import Hint, icon
        self.records=deque(maxlen=1500)
        self.filter=tk.StringVar(value='All events')
        self.query=tk.StringVar()
        self.follow=tk.BooleanVar(value=True)
        self.count=tk.StringVar(value='0 events')
        self.timer=None
        bar=ttk.Frame(self);bar.pack(fill='x',pady=(0,3))
        select=ttk.Combobox(bar,textvariable=self.filter,values=['All events','Network','Routes','Errors','System'],state='readonly',width=12)
        select.pack(side='left',padx=(0,6))
        Hint(select,'Filter by event category')
        from .ui_icons import icon_image
        ttk.Label(bar,image=icon_image(bar,'search',t.MUTED)).pack(side='left',padx=(0,4))
        self.search=ttk.Entry(bar,textvariable=self.query,width=18)
        self.search.pack(side='left',fill='x',expand=True)
        Hint(self.search,'Search event text, vehicle ID or incident ID')
        ttk.Checkbutton(bar,text='Follow',variable=self.follow,command=self.scroll_end).pack(side='left',padx=6)
        icon(bar,'trash',self.clear,'Clear the local log view; simulation and MEC records are unchanged')
        ttk.Label(bar,textvariable=self.count,style='Muted.TLabel').pack(side='right',padx=5)
        area=ttk.Frame(self,style='Editor.TFrame');area.pack(fill='both',expand=True)
        self.text=tk.Text(area,height=5,wrap='none',font=('Consolas',9),background=t.EDITOR,
            foreground=t.FG,insertbackground=t.FG,selectbackground='#264f78',selectforeground='#ffffff',
            relief='flat',borderwidth=0,highlightthickness=0,padx=8,pady=5,state='disabled',takefocus=True)
        vertical=ttk.Scrollbar(area,command=self.user_scroll);vertical.pack(side='right',fill='y')
        self.text.configure(yscrollcommand=vertical.set);self.text.pack(fill='both',expand=True)
        horizontal=ttk.Scrollbar(self,orient='horizontal',command=self.text.xview);horizontal.pack(fill='x')
        self.text.configure(xscrollcommand=horizontal.set)
        self.text.bind('<MouseWheel>',lambda e:self.follow.set(False),add='+')
        for name,color in {'time':t.MUTED,'info':'#9da5b4','network':'#75beff','success':t.GREEN,
                           'route':'#c586c0','warn':'#dcdcaa','error':t.RED,'entity':'#9cdcfe'}.items():
            self.text.tag_configure(name,foreground=color)
        self.text.tag_configure('match',background='#613214',foreground='#ffffff')
        self.filter.trace_add('write',self.defer_render)
        self.query.trace_add('write',self.defer_render)

    def user_scroll(self,*args):
        self.follow.set(False)
        self.text.yview(*args)

    def scroll_end(self):
        if self.follow.get():self.text.see('end')

    def defer_render(self,*_):
        if self.timer:self.after_cancel(self.timer)
        self.timer=self.after(100,self.render)

    def clear(self):
        self.records.clear();self.render()

    def append(self,kind,message,sim=0):
        record=(float(sim),kind,str(message))
        removed=self.records[0] if len(self.records)==self.records.maxlen else None
        self.records.append(record)
        if removed and self.visible(removed):
            # Each event occupies one logical line. Trim that line instead of
            # rebuilding 1,500 highlighted rows on every subsequent event.
            self.text.configure(state='normal');self.text.delete('1.0','2.0');self.text.configure(state='disabled')
        if self.visible(record):
            self.text.configure(state='normal');self.insert(record);self.text.configure(state='disabled')
            self.scroll_end();self.update_count()
        else:self.update_count()

    def visible(self,record):
        _,kind,message=record
        category=classify(kind,message)[2]
        return (self.filter.get() in ('All events',category)) and self.query.get().casefold() in message.casefold()

    def update_count(self):
        count=sum(self.visible(r) for r in self.records)
        self.count.set(f'{count} / {len(self.records)} events' if count!=len(self.records) else f'{count} event' if count==1 else f'{count} events')

    def insert(self,record):
        sim,kind,message=record
        label,tag,_=classify(kind,message)
        minutes,seconds=divmod(sim,60)
        self.text.insert('end',f'{int(minutes):02d}:{seconds:05.2f}  ','time')
        self.text.insert('end',f'{label:<7} ',tag)
        start=self.text.index('end-1c')
        self.text.insert('end',message.replace('\n','  ')+'\n',tag if tag in ('error','warn') else 'info')
        for match in re.finditer(r'\b(?:MEC|H3|[A-Za-z0-9_-]+(?=[:]| v\d))\b',message):
            self.text.tag_add('entity',f'{start}+{match.start()}c',f'{start}+{match.end()}c')
        for match in re.finditer(r'ACK|Route changed|Route retained|NO COVERAGE',message):
            self.text.tag_add(tag,f'{start}+{match.start()}c',f'{start}+{match.end()}c')
        query=self.query.get()
        if query:
            for match in re.finditer(re.escape(query),message,re.IGNORECASE):
                self.text.tag_add('match',f'{start}+{match.start()}c',f'{start}+{match.end()}c')

    def render(self):
        self.timer=None
        position=self.text.yview()[0]
        self.text.configure(state='normal');self.text.delete('1.0','end')
        for record in self.records:
            if self.visible(record):self.insert(record)
        self.text.configure(state='disabled')
        self.update_count()
        if self.follow.get():self.text.see('end')
        else:self.text.yview_moveto(position)
