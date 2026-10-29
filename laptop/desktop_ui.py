"""Compact single-window desktop workspace, shared hints and fleet controls."""
import tkinter as tk
from tkinter import ttk

from .map_canvas import MapCanvas, color_for, label_for
from .route_minimap import RouteMiniMap


class Hint:
    def __init__(self, widget, text):
        self.widget, self.text, self.popup, self.timer = widget, text, None, None
        widget.bind('<Enter>', self.schedule, add='+')
        widget.bind('<Leave>', self.hide, add='+')
        widget.bind('<ButtonPress>', self.hide, add='+')
        widget.bind('<Destroy>', self.hide, add='+')

    def schedule(self, _=None):
        self.hide()
        self.timer = self.widget.after(450, self.show)

    def show(self):
        self.timer = None
        if not self.widget.winfo_exists():
            return
        text = self.text() if callable(self.text) else self.text
        if not text:
            return
        self.popup = tk.Toplevel(self.widget)
        self.popup.wm_overrideredirect(True)
        label = tk.Label(self.popup, text=text, background='#252526', foreground='#dddddd',
                 font=('Segoe UI', 9), padx=8, pady=5, wraplength=360, justify='left')
        label.pack()
        owner = self.widget.winfo_toplevel()
        x = min(self.widget.winfo_rootx()+8, owner.winfo_rootx()+owner.winfo_width()-label.winfo_reqwidth()-8)
        y = min(self.widget.winfo_rooty()+self.widget.winfo_height()+7,
                owner.winfo_rooty()+owner.winfo_height()-label.winfo_reqheight()-8)
        self.popup.wm_geometry(f'+{max(owner.winfo_rootx()+8,x)}+{max(owner.winfo_rooty()+8,y)}')

    def hide(self, _=None):
        if self.timer:
            self.widget.after_cancel(self.timer)
            self.timer = None
        if self.popup:
            self.popup.destroy()
            self.popup = None


def icon(parent, glyph, command, hint, width=3, text=None):
    from .ui_icons import icon_image
    aliases={'⚙':'settings','+':'plus','−':'minus','⌖':'focus','▧':'map','↺':'restart',
        '▶':'play','▸|':'step','»':'fast','▷':'play','⚑':'pin','□':'new','✦':'example'}
    name=aliases.get(glyph,glyph)
    image=icon_image(parent,name)
    button=ttk.Button(parent,image=image,text=(' '+text) if text else '',compound='left',
        command=command,style='Icon.TButton',takefocus=True,width=0)
    button._icon_ref=image
    button.pack(side='left',padx=1)
    Hint(button,hint)
    return button


def build_workspace(app):
    from .map_launcher import GROUPS, INCIDENTS
    from . import ui_theme as t
    from .log_console import LogConsole
    root=app.root
    t.apply(root)
    root.title('AliveMap · Simulation workspace')
    root.geometry(f'{min(1360,root.winfo_screenwidth()-50)}x{min(860,root.winfo_screenheight()-80)}+16+16')
    root.minsize(980,620)
    outer=ttk.Frame(root);outer.pack(fill='both',expand=True)
    header=ttk.Frame(outer,padding=(8,3));header.pack(fill='x')
    ttk.Label(header,text='AliveMap',style='Title.TLabel').pack(side='left',padx=(0,14))
    ttk.Label(header,text='SIMULATION',style='Muted.TLabel').pack(side='left')
    region=ElidedLabel(header,app.region,foreground=t.ACCENT)
    region.pack(side='left',padx=10,fill='x',expand=True)
    Hint(region,lambda:app.region.get())
    app.connection_led=tk.Button(header,text='MEC',foreground=t.MUTED,background=t.PANEL,
        activebackground=t.FIELD,activeforeground=t.FG,relief='flat',borderwidth=0,padx=6,pady=1,
        font=('Segoe UI',9),cursor='hand2',command=app.reconnect)
    app.connection_led.pack(side='right',padx=(6,0))
    Hint(app.connection_led,lambda:app.connection_hint())
    settings=icon(header,'settings',app.show_settings,'Settings and connection details')
    settings.pack_forget();settings.pack(side='right',padx=2)
    ttk.Label(header,textvariable=app.clock,font=('Consolas',9)).pack(side='right',padx=10)
    ttk.Separator(outer).pack(fill='x')

    vertical=ttk.Panedwindow(outer,orient='vertical');vertical.pack(fill='both',expand=True)
    upper=ttk.Panedwindow(vertical,orient='horizontal');vertical.add(upper,weight=5)
    app.inspector=ttk.Frame(upper,width=254);upper.add(app.inspector,weight=0)
    app.map_host=ttk.Frame(upper,style='Editor.TFrame');upper.add(app.map_host,weight=1)
    app.canvas=MapCanvas(app.map_host,status=app.tile_status.set);app.canvas.pack(fill='both',expand=True)
    app.notice_label=ttk.Label(app.canvas,textvariable=app.notice,style='Muted.TLabel',padding=(6,4),wraplength=550)
    app.notice_label.place(x=8,y=38)
    Hint(app.notice_label,lambda:app.notice.get())
    app.canvas.bind('<Configure>',lambda e:app.notice_label.configure(wraplength=max(180,min(550,e.width-170))),add='+')
    app.canvas.on_vehicle_select=app.select_fleet_vehicle
    app.minimap=RouteMiniMap(app.canvas)
    app.minimap.place(x=8,rely=1,y=-54,anchor='sw',width=250,height=155)
    Hint(app.minimap,'Route overview: grey roads, solid current routes, dashed abandoned sections. Double-click to expand.')
    app.fleet_panel=ttk.Frame(app.map_host,padding=2)
    app.fleet_panel.place(relx=1,x=-8,y=8,anchor='ne')
    app.fleet_signature=None;app.fleet_expanded=False
    app.render_fleet()
    tools=ttk.Frame(app.map_host,padding=1);tools.place(relx=1,rely=1,x=-8,y=-31,anchor='se')
    icon(tools,'plus',lambda:app.canvas.change_zoom(1),'Zoom in')
    icon(tools,'minus',lambda:app.canvas.change_zoom(-1),'Zoom out')
    icon(tools,'focus',app.overview,'Show all vehicles and routes')
    icon(tools,'map',app.toggle_minimap,'Show or hide route overview')

    bottom=ttk.Frame(vertical,height=188);vertical.add(bottom,weight=1)
    transport=ttk.Frame(bottom,padding=(5,2));transport.pack(fill='x')
    icon(transport,'restart',lambda:app.send('reset'),'Restart this scene from its initial state')
    app.play_button=icon(transport,'play',app.toggle_play,'Play / pause · Space')
    icon(transport,'step',lambda:app.send('step'),'One simulation step · Right arrow')
    icon(transport,'fast',app.faster,'Increase target playback speed')
    speed=ttk.Combobox(transport,textvariable=app.speed,values=['1x','2x','5x','10x','20x','50x','100x'],state='readonly',width=5)
    speed.pack(side='left',padx=(6,8));speed.bind('<<ComboboxSelected>>',lambda e:app.set_speed())
    Hint(speed,'Target simulation speed. Status shows the measured rate.')
    app.timeline=tk.Canvas(transport,height=24,background=t.PANEL,highlightthickness=0)
    app.timeline.pack(side='left',fill='x',expand=True,padx=(0,8))
    Hint(app.timeline,'Elapsed simulation time; amber markers are route changes. Restart replays the scene.')
    ttk.Checkbutton(transport,text='Pause on reroute',variable=app.pause_on_change,
        command=lambda:app.worker.commands.put(('review_mode',app.pause_on_change.get()))).pack(side='right',padx=5)
    ttk.Separator(bottom).pack(fill='x')
    details=ttk.Frame(bottom);details.pack(fill='both',expand=True)
    config=ttk.Frame(details,width=254,padding=(8,4));config.pack(side='left',fill='y')
    config.pack_propagate(False)

    app.backend_box=app.combo(config,'Backend',app.mode,['Local demo (no SSH)','Physical MEC (HTTPS / SSH)'])
    app.map_box=app.combo(config,'Map',app.map,list(GROUPS))
    app.region_box=app.combo(config,'Region',app.region,[])
    app.scenario_box=ttk.Combobox(config,textvariable=app.scenario,state='readonly')
    app.combo(config,'Run',app.condition,['With incident','Without incident'])
    app.combo(config,'Incident',app.incident,list(INCIDENTS))
    app.map_box.bind('<<ComboboxSelected>>',lambda e:(app.select_map(),app.editor.open_scene(True)))
    app.region_box.bind('<<ComboboxSelected>>',lambda e:(app.select_region(),app.editor.open_scene(True)))
    actions=ttk.Frame(config);actions.pack(fill='x',pady=(3,0))
    icon(actions,'play',app.load,'Load and play the selected story, with or without an incident',text='Run')
    icon(actions,'pin',lambda:app.load('none'),'Run identical trips without an incident for comparison',text='Baseline')
    icon(actions,'new',lambda:app.editor.open_scene(False),'New empty playground')
    icon(actions,'example',lambda:app.editor.open_scene(True),'Load editable example for this map')
    ttk.Separator(details,orient='vertical').pack(side='left',fill='y')
    app.diagnostics=ttk.Notebook(details);app.diagnostics.pack(side='left',fill='both',expand=True)
    pages=[ttk.Frame(app.diagnostics,padding=5,style='Editor.TFrame') for _ in range(4)]
    logs,status,state,settings=pages
    for page,name in zip(pages,('Logs','Status','Current state','Settings')):app.diagnostics.add(page,text=name)
    app.settings_page=settings
    app.console=LogConsole(logs);app.console.pack(fill='both',expand=True)
    app.history=app.console.text
    for variable in (app.status,app.comparison,app.story):
        label=ttk.Label(status,textvariable=variable,background=t.EDITOR,wraplength=700)
        label.pack(anchor='w',fill='x',pady=(0,5))
        label.bind('<Configure>',lambda e,w=label:w.configure(wraplength=max(150,e.width-4)))
    label=ttk.Label(state,textvariable=app.vehicle_detail,background=t.EDITOR,wraplength=700)
    label.pack(anchor='w',fill='x')
    label.bind('<Configure>',lambda e:label.configure(wraplength=max(150,e.width-4)))
    app.profile=tk.Canvas(state,height=88,background=t.EDITOR,highlightthickness=0);app.profile.pack(fill='both',expand=True)
    app.profile.bind('<Configure>',lambda e:app.show_vehicle())
    app.combo(settings,'MEC',app.mode,['Local demo (no SSH)','Physical MEC (HTTPS / SSH)'])
    app.combo(settings,'Layer',app.layer,list(app.canvas.sources)).bind('<<ComboboxSelected>>',lambda e:app.canvas.set_source(app.layer.get()))
    ttk.Checkbutton(settings,text='Open native SUMO on next load',variable=app.sumo_gui).pack(anchor='w',pady=3)
    ttk.Label(settings,text='Backend changes apply on the next load. Tower coverage is simulated.',style='Muted.TLabel').pack(anchor='w')
    ttk.Separator(outer).pack(fill='x')
    footer=ttk.Frame(outer,padding=(8,2));footer.pack(fill='x')
    app.footer_label=ElidedLabel(footer,app.tile_status,style='Muted.TLabel');app.footer_label.pack(fill='x')
    Hint(app.footer_label,lambda:app.tile_status.get())
    root.bind('<space>',app.keyboard_play);root.bind('<Right>',app.keyboard_step)
    from .responsive import ResponsiveWorkspace
    app.layout=ResponsiveWorkspace(app,vertical,upper,bottom,config,transport)
    app.canvas.bind('<Configure>',app.layout.fit_overview,add='+')
    app.console.bar.bind('<Configure>',app.layout.schedule,add='+')
    root.after(200,lambda:dark_titlebar(root))


class ElidedLabel(ttk.Label):
    """One-line context text with a real ellipsis instead of clipped glyphs."""
    def __init__(self,parent,source,**kwargs):
        self.source,self.display=source,tk.StringVar(parent)
        super().__init__(parent,textvariable=self.display,width=1,anchor='w',**kwargs)
        self.bind('<Configure>',self.refresh)
        self.trace=source.trace_add('write',self.refresh)
        self.bind('<Destroy>',lambda e:source.trace_remove('write',self.trace) if e.widget is self else None)
    def refresh(self,*_):
        from tkinter import font
        font=font.Font(font=self.cget('font') or 'TkDefaultFont')
        value=self.source.get().replace('\n','  ')
        width=max(20,self.winfo_width()-2)
        if font.measure(value)>width:
            while value and font.measure(value+'…')>width:value=value[:-1]
            value+='…'
        self.display.set(value)


def dark_titlebar(root):
    import sys
    if sys.platform!='win32':return
    try:
        import ctypes
        hwnd=ctypes.windll.user32.GetParent(root.winfo_id())
        enabled=ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd,20,ctypes.byref(enabled),ctypes.sizeof(enabled))
    except (AttributeError,OSError):pass
