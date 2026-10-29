"""Nonmodal editing tools: map clicks create intent, worker owns SUMO mutations."""
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from copy import deepcopy

from shapely.geometry import Point, Polygon, box, mapping

from routing_core.maps import PackageMapProvider, read_json
from routing_core.playground import empty_scene, example_scene, road_placement, validate_scene
from routing_core.agents import PROFILES
from . import ui_theme as theme


def drawn_geometry(provider, tool, points, radius=50):
    xy = [provider.lonlat_to_xy(*p) for p in points]
    if tool == "circle" and len(xy) == 1:
        area = Point(*xy[0]).buffer(radius, quad_segs=16)
    elif tool == "rectangle" and len(xy) == 2:
        area = box(min(xy[0][0], xy[1][0]), min(xy[0][1], xy[1][1]), max(xy[0][0], xy[1][0]), max(xy[0][1], xy[1][1]))
    elif tool == "polygon" and len(xy) >= 3:
        area = Polygon(xy)
    else:
        raise ValueError("Circle needs one click, rectangle two, polygon at least three")
    if not area.is_valid or area.area < 1 or len(area.exterior.coords) > 130:
        raise ValueError("Draw a non-intersecting area with 3–129 vertices")
    return provider.geometry_to_wgs84(area)


class FormScroll(ttk.Frame):
    """Clipped native form with no embedded canvas windows to lose on tab switches."""
    def __init__(self,parent):
        super().__init__(parent)
        self.offset=0
        self.bar=ttk.Scrollbar(self,orient='vertical',command=self.scroll)
        self.bar.pack(side='right',fill='y')
        self.viewport=ttk.Frame(self,width=250,height=200)
        self.viewport.pack(side='left',fill='both',expand=True)
        self.content=ttk.Frame(self.viewport,padding=(7,5))
        self.content.place(x=0,y=0,relwidth=1)
        self.viewport.bind('<Configure>',self.layout)
        self.content.bind('<Configure>',self.layout)

    def layout(self,_=None):
        width=max(1,self.viewport.winfo_width())
        for child in self.content.winfo_children():
            if child.winfo_class()=='TLabel' and int(child.cget('wraplength') or 0)>0:
                wrap=max(120,width-14)
                if int(child.cget('wraplength'))!=wrap:child.configure(wraplength=wrap)
        full=max(1,self.content.winfo_reqheight());visible=max(1,self.viewport.winfo_height())
        self.offset=max(0,min(self.offset,max(0,full-visible)))
        self.content.place_configure(y=-self.offset)
        self.bar.set(self.offset/full,min(1,(self.offset+visible)/full))

    def scroll(self,action,value,units=None):
        full=max(1,self.content.winfo_reqheight())
        if action=='moveto':self.offset=float(value)*full
        else:self.offset+=int(value)*(self.viewport.winfo_height()*.85 if units=='pages' else 22)
        self.layout()


class PlaygroundEditor:
    def __init__(self, app, parent=None):
        self.app, self.scene = app, None
        self.embedded = parent is not None
        self.window = parent if self.embedded else tk.Toplevel(app.root)
        self.epoch = None
        self.action_buttons=[]
        self.page_bodies=[]
        self.origin, self.destination, self.geometry, self.tower_point = None, None, None, None
        if not self.embedded:
            self.window.title('AliveMap · Playground tools')
            self.window.geometry('400x760')
            self.window.protocol('WM_DELETE_WINDOW', self.window.withdraw)
        top = self.top = ttk.Frame(self.window, padding=(6,4)); top.pack(fill='x')
        self.body = top
        self.note = tk.StringVar(value="Load an example or create a scene")
        if hasattr(app,'notice'):self.note.trace_add('write',lambda *_:app.notice.set(self.note.get()))
        from .desktop_ui import ElidedLabel, Hint
        note=ElidedLabel(self.body,self.note,style='Muted.TLabel')
        note.pack(fill='x',pady=(0,3));Hint(note,lambda:self.note.get())
        self.buttons([('Empty playground',lambda: self.open_scene(False)),('Load example',lambda: self.open_scene(True)),
            ('Load scene…',self.load),('Save scene…',self.save)])
        self.tabs = ttk.Notebook(self.window)
        self.tabs.pack(fill='both', expand=True)
        self.tabs.bind('<<NotebookTabChanged>>',lambda _:self.tabs.update_idletasks(),add='+')
        self.vehicle_page = self.page('Vehicles')
        self.heading('VEHICLE')
        self.vehicle = self.field("Vehicle ID", "vehicle-1")
        vehicle_row = self.vehicle.widget.master
        self.vehicle.widget.destroy()
        self.vehicle_box = ttk.Combobox(vehicle_row,textvariable=self.vehicle,width=10,state='normal')
        self.vehicle_box.pack(side='left',fill='x',expand=True)
        self.vehicle.widget = self.vehicle_box
        self.vehicle_box.bind('<<ComboboxSelected>>',self.select_vehicle)
        from .desktop_ui import Hint
        Hint(self.vehicle_box,'Select an existing vehicle, or use the fleet Plus to create a new ID.')
        self.role = self.field("Role", "both", ["both", "reporter", "receiver", "offline"])
        self.profile = self.field("Policy", "time_sensitive", list(PROFILES))
        self.buttons([("Pick origin", lambda: self.pick_road("origin")), ("Pick destination", lambda: self.pick_road("destination"))])
        self.origin_edge = self.field("From road", "", [])
        self.destination_edge = self.field("To road", "", [])
        self.position = self.field("Position (m)", "0")
        self.buttons([("Add / update", self.put_vehicle), ("Remove", lambda: self.edit("remove_vehicle", {"id": self.vehicle.get()})), ("Track", lambda: app.track(self.vehicle.get()))])

        self.anomaly_page = self.page("Incidents")
        self.heading("INCIDENT")
        self.incident = self.field("Incident ID", "anomaly-1")
        self.incident_box=self.selector(self.incident,self.select_anomaly)
        self.kind = self.field("Type", "landslide", ["congestion", "flood", "landslide"])
        self.radius = self.field("Radius (m)", "50")
        self.depth = self.field("Depth (m)", "0.25")
        self.ratio = self.field("Speed ratio", "0.08")
        self.ttl = self.field("TTL (real s)", "1800")
        self.sensor = self.field("Sensor (m)", "20")
        self.buttons([(tool.title(), lambda t=tool: self.draw(t)) for tool in ("circle", "rectangle", "polygon")])
        self.buttons([("Finish shape", app.canvas.finish_edit), ("Cancel drawing", self.cancel_drawing)])
        self.buttons([("Add / update anomaly", self.put_anomaly), ("Remove", lambda: self.edit("remove_anomaly", {"id": self.incident.get()}))])
        self.buttons([("Publish operator incident", lambda: self.edit("publish", {"id": self.incident.get()})), ("Clear selected", lambda: self.edit("clear", {"id": self.incident.get()}))])
        note=ttk.Label(self.body,text='Discover via vehicle, or publish manually.',style='Muted.TLabel',wraplength=245)
        note.pack(fill='x',pady=(3,0))
        Hint(note,'Save creates ground truth. A reporting vehicle must discover it. Publish is explicit operator injection.')
        self.tower_page = self.page("Towers")
        self.heading("SIMULATED 5G")
        self.tower = self.field("Tower ID", "Sim-gNB-1")
        self.tower_box=self.selector(self.tower,self.select_tower)
        self.coverage = self.field("Coverage (m)", "1000")
        self.buttons([("Pick tower position", self.pick_tower), ("Add / update", self.put_tower), ("Remove", lambda: self.edit("remove_tower", {"id": self.tower.get()}))])
        self.cells, self.towers = tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        ttk.Checkbutton(self.body, text="H3 grid and affected cells", variable=self.cells, command=self.overlays).pack(anchor="w")
        ttk.Checkbutton(self.body, text="Towers and coverage", variable=self.towers, command=self.overlays).pack(anchor="w")
        self.radio_page = self.page("Radio")
        self.heading("PERCEPTION → MEC → DELIVERY")
        self.network_text = tk.StringVar(value="No playground loaded")
        ttk.Label(self.body, textvariable=self.network_text, wraplength=260).pack(fill="x")
        ttk.Label(self.body,text='Simulated coverage · HTTP application delivery',style='Muted.TLabel',wraplength=245).pack(fill='x',pady=4)

    def selector(self,variable,callback):
        row=variable.widget.master
        variable.widget.destroy()
        box=ttk.Combobox(row,textvariable=variable,state='normal',width=10)
        box.pack(side='left',fill='x',expand=True)
        variable.widget=box
        box.bind('<<ComboboxSelected>>',callback)
        from .desktop_ui import Hint
        Hint(box,'Select an existing ID, or enter a new ID to create another object')
        return box

    def heading(self, text):
        # The selected inspector tab already identifies the object type.
        pass

    def field(self, label, value, choices=None):
        variable = tk.StringVar(value=value)
        row = ttk.Frame(self.body); row.pack(fill="x", pady=1)
        ttk.Label(row, text=label, width=13).pack(side="left")
        widget = ttk.Entry(row, textvariable=variable, width=10) if choices is None else ttk.Combobox(row, textvariable=variable, values=choices, state="readonly", width=10)
        widget.pack(side="left", fill="x", expand=True)
        from .desktop_ui import Hint
        Hint(widget, {'Role':'Reporter: senses/uploads. Receiver: listens. Both: both. Offline: neither.',
            'Policy':'Each vehicle plans independently using this travel-time, clearance and risk policy.',
            'From road':'Directed OSM road. A pin selects the location; choose the correct direction here.',
            'To road':'Directed destination road. Drag the B pin to change it, then Save.',
            'TTL (real s)':'Expiry in real seconds. Speeding the simulation does not speed MEC expiry.',
            'Sensor (m)':'How close a reporter must get to discover this synthetic anomaly.',
            'Coverage (m)':'Synthetic circular tower coverage; this is not measured radio coverage.'}.get(label,label))
        variable.widget = widget
        return variable

    def page(self, title):
        page = ttk.Frame(self.tabs)
        self.tabs.add(page, text=title)
        scroll=FormScroll(page)
        scroll.pack(fill='both',expand=True)
        self.body=scroll.content
        self.page_bodies.append(self.body)
        def wheel(event):
            if event.widget.winfo_class() != 'TCombobox' and str(event.widget).startswith(str(page)):
                scroll.scroll('scroll',-int(event.delta/120)*3,'units')
        self.window.winfo_toplevel().bind('<MouseWheel>', wheel, add='+')
        return page

    def buttons(self, pairs):
        from .desktop_ui import Hint
        from .ui_icons import icon_image
        actions={'Empty playground':('new','New'), 'Load example':('example','Example'),
            'Load scene…':('folder',''), 'Save scene…':('save',''),
            'Pick origin':('pin','Origin'), 'Pick destination':('pin','Destination'),
            'Add / update':('check','Save'), 'Remove':('trash',''), 'Track':('focus',''),
            'Add / update anomaly':('check','Save area'), 'Publish operator incident':('send','Publish'),
            'Clear selected':('clear','Clear'), 'Pick tower position':('pin','Place'),
            'Finish shape':('check','Finish'), 'Cancel drawing':('close','Cancel'),
            'Circle':('circle','Circle'),'Rectangle':('rectangle','Rect'),'Polygon':('polygon','Polygon')}
        row=ttk.Frame(self.body);row.pack(fill='x',pady=3)
        for label,action in pairs:
            name,text=actions[label]
            color='#75beff' if label=='Pick origin' else '#c586c0' if label=='Pick destination' else theme.FG
            image=icon_image(row,name,color)
            button=ttk.Button(row,image=image,text=(' '+text) if text else '',compound='left',command=action,
                style='Primary.TButton' if label.startswith('Add / update') else 'TButton',width=0)
            button._icon_ref=image
            self.action_buttons.append(button)
            button.pack(side='left',padx=(0,3))
            Hint(button,{
                'Circle':'Click the map centre; radius comes from Radius (m). Then Save area.',
                'Rectangle':'Click two opposite map corners. Then Save area.',
                'Polygon':'Click at least three map vertices, then Finish and Save area.',
                'Finish shape':'Close a polygon after at least three vertices. Circle and rectangle finish automatically.',
                'Cancel drawing':'Discard the unsaved drawing; saved incidents are kept.',
                'Add / update anomaly':'Save ground truth. A reporter must encounter it before MEC knows about it.',
                'Publish operator incident':'Inject the selected saved incident directly into MEC; bypasses vehicle discovery.',
                'Clear selected':'Send a versioned clearance and disable discovery of this incident.',
                'Add / update':'Apply this form to the paused simulation. A changed origin starts a new manual placement.'
            }.get(label,label))

    def guard(self, action):
        try:
            action()
        except Exception as exc:
            self.note.set(str(exc))
            self.app.story.set(str(exc)) if hasattr(self.app, "story") else None
            if hasattr(self.app,'console'):self.app.console.append('edit_error',str(exc),self.app.frame.get('time',0) if self.app.frame else 0)

    def require(self):
        if getattr(self.app,'loading',False):
            raise ValueError('Wait for the new scene to finish loading')
        if not self.scene or not self.app.frame or not self.app.frame.get("playground"):
            raise ValueError("Open an empty playground or example first")

    def activate(self, provider, scene):
        scene = validate_scene(provider, scene)
        if hasattr(self.app, "map"):
            from .map_launcher import GROUPS
            self.app.map.set(next(group for group, ids in GROUPS.items() if scene["map_id"] in ids))
            self.app.select_map()
            self.app.region.set(scene["map_id"])
            self.app.select_region()
        self.app.worker.commands.put(("load", (str(provider.path), None,
            {"playground_scene": scene, "incident_kind": "none", "mec_mode": "local" if self.app.mode.get().startswith("Local") else "physical",
             "gui": self.app.sumo_gui.get(), "pause_on_change": self.app.pause_on_change.get()})))
        self.note.set("Loading editable world; starts paused. Add anomalies, vehicles and towers, then Resume.")
        self.app.canvas.cancel_edit()

    def open_scene(self, example, story_kind=None, autoplay=False):
        def action():
            path = self.app.packages.get(self.app.region.get())
            if not path:
                raise ValueError('Build the selected map first')
            options = {'incident_kind':'none', 'mec_mode':'local' if self.app.mode.get().startswith('Local') else 'physical',
                'gui':self.app.sumo_gui.get(), 'pause_on_change':self.app.pause_on_change.get()}
            from .map_launcher import INCIDENTS
            if example:options.update(story_kind=story_kind or INCIDENTS[self.app.incident.get()],autoplay=autoplay)
            if hasattr(self.app,'last_load'):self.app.last_load=(example,story_kind)
            self.app.loading=True
            self.app.frame=None
            self.scene=None
            self.app.worker.commands.put(('prepare_scene',(str(path),bool(example),options)))
            self.note.set('Preparing map in background…')
            self.app.canvas.cancel_edit()
        self.guard(action)

    def edit(self, operation, payload):
        def action():
            self.require()
            if operation in ('publish','clear','remove_anomaly') and not any(a['id']==payload.get('id') for a in self.scene['anomalies']):
                raise ValueError('Select a saved incident first, or draw an area and Save area.')
            if operation=='publish' and self.app.canvas.draft_geometry:
                raise ValueError('This area is still a draft. Click Save area before Publish.')
            self.app.send("edit", (operation, payload))
            self.note.set("Edit queued; simulation paused. Resume when ready.")
        self.guard(action)

    def road_picked(self, which, point):
        def action():
            provider = self.app.provider
            placement = road_placement(provider, point)
            xy = Point(*provider.lonlat_to_xy(*point))
            nearby = [provider.edge_ids[int(i)] for i in provider.tree.query(xy.buffer(50))]
            candidates = sorted((provider.lines[eid].distance(xy), eid) for eid in nearby
                if 'passenger' in provider.edges[eid]['allowed'] and provider.lines[eid].distance(xy) <= 50)
            variable = self.origin_edge if which == 'origin' else self.destination_edge
            variable.widget['values'] = [eid for _,eid in candidates[:12]]
            variable.set(placement['edge'])
            setattr(self, which, point)
            if which == 'origin':
                self.position.set(f"{placement['position_m']:.2f}")
            self.sync_pins()
            self.note.set(which.title()+' snapped to OSM road. Drag the pin to move it; choose direction below.')
        self.guard(action)
        self.sync_pins()

    def sync_pins(self):
        if not self.app.provider:
            return
        pins = {}
        for which, variable in (('origin', self.origin_edge),('destination',self.destination_edge)):
            edge = variable.get()
            if edge in self.app.provider.edges:
                line = self.app.provider.lines[edge]
                position = float(self.position.get() or 0)/max(self.app.provider.edges[edge]['sumo_length_m'],1)*line.length if which == 'origin' else line.length
                point = line.interpolate(min(position,line.length))
                pins[which] = self.app.provider.xy_to_lonlat(point.x,point.y)
        self.app.canvas.pins = pins
        self.app.canvas.pin_callback = self.road_picked
        self.app.canvas.pin_start = lambda: self.app.send('pause')
        self.app.canvas.redraw()

    def pick_road(self, which):
        self.guard(lambda: (self.require(), self.app.send('pause'),
            self.app.canvas.start_edit('point',lambda points: self.road_picked(which,points[0]))))

    def put_vehicle(self):
        def action():
            self.require()
            self.edit("vehicle", {"id": self.vehicle.get(), "origin": self.origin_edge.get(), "destination": self.destination_edge.get(),
                                  "position_m": float(self.position.get()), "profile": self.profile.get(), "role": self.role.get()})
        self.guard(action)

    def select_vehicle(self, _event=None):
        name = self.vehicle_box.get(); self.vehicle.set(name)
        vehicle = self.scene["vehicles"][name]
        for variable, key in ((self.origin_edge, "origin"), (self.destination_edge, "destination")):
            variable.widget["values"] = [vehicle[key]]; variable.set(vehicle[key])
        self.position.set(str(vehicle.get("position_m", 0)))
        self.role.set(vehicle.get("role", "both")); self.profile.set(vehicle["profile"])
        self.sync_pins()
        self.app.track(name)

    def draw(self, tool):
        def picked(points):
            self.guard(lambda: self.set_geometry(drawn_geometry(self.app.provider, tool, points, float(self.radius.get()))))
        self.guard(lambda: (self.require(), self.app.send("pause"), self.app.canvas.start_edit(tool, picked)))
        if self.app.canvas.edit_tool:self.note.set('Draw '+tool+': '+('click its centre on the map' if tool=='circle' else 'click two opposite corners' if tool=='rectangle' else 'click at least three vertices, then Finish'))

    def cancel_drawing(self):
        self.app.canvas.cancel_edit()
        self.app.canvas.draft_geometry=None
        self.geometry=None
        self.app.canvas.redraw()
        self.note.set('Drawing cancelled; saved incidents were not changed.')

    def set_geometry(self, geometry):
        self.geometry = geometry
        self.app.canvas.draft_geometry=geometry
        self.app.canvas.redraw()
        self.note.set("Area drawn. Choose type and values, then Add / update anomaly.")

    def put_anomaly(self):
        def action():
            if not self.geometry:
                raise ValueError("Draw an area first")
            self.edit("anomaly", {"id": self.incident.get(), "kind": self.kind.get(), "geometry": self.geometry,
                                  "water_depth_m": float(self.depth.get()), "traffic_speed_ratio": float(self.ratio.get()),
                                  "ttl_s": float(self.ttl.get()), "detect_m": float(self.sensor.get())})
        self.guard(action)

    def select_anomaly(self, _event=None):
        name = self.incident_box.get(); self.incident.set(name)
        a = next(a for a in self.scene["anomalies"] if a["id"] == name)
        self.geometry = deepcopy(a["geometry"]); self.kind.set(a["kind"])
        for variable, key, default in ((self.depth, "water_depth_m", .25), (self.ratio, "traffic_speed_ratio", .08),
                                       (self.ttl, "ttl_s", 1800), (self.sensor, "detect_m", 20)):
            variable.set(str(a.get(key, default)))

    def pick_tower(self):
        self.guard(lambda: (self.require(), self.app.send("pause"), self.app.canvas.start_edit("point", lambda points: self.set_tower_point(points[0]))))

    def set_tower_point(self, point):
        self.tower_point = point; self.note.set("Tower position chosen. Set radius and Add / update.")

    def put_tower(self):
        def action():
            if not self.tower_point:
                raise ValueError("Pick a tower position first")
            self.edit("tower", {"id": self.tower.get(), "longitude": self.tower_point[0], "latitude": self.tower_point[1], "radius_m": float(self.coverage.get())})
        self.guard(action)

    def select_tower(self, _event=None):
        name = self.tower_box.get(); self.tower.set(name)
        tower = next(t for t in self.scene["towers"] if t["id"] == name)
        self.tower_point = tower["longitude"], tower["latitude"]
        self.coverage.set(str(tower["radius_m"]))

    def overlays(self):
        self.app.canvas.show_cells, self.app.canvas.show_towers = self.cells.get(), self.towers.get()
        self.app.canvas.redraw()

    def update(self, frame):
        self.scene = frame.get("scene")
        if not self.scene:
            return
        for widget,values in ((self.vehicle_box,tuple(self.scene['vehicles'])),
                              (self.incident_box,tuple(a['id'] for a in self.scene['anomalies'])),
                              (self.tower_box,tuple(t['id'] for t in self.scene['towers']))):
            if tuple(widget['values'])!=values:widget['values']=values
        if self.epoch != frame["run_id"]:
            self.epoch = frame["run_id"]
            self.origin, self.destination, self.geometry, self.tower_point = None, None, None, None
            self.origin_edge.set(""); self.destination_edge.set("")
            self.origin_edge.widget["values"] = []; self.destination_edge.widget["values"] = []
            self.position.set("0")
            self.vehicle_box.set("")
            for records, widget, select in ((self.scene["anomalies"], self.incident_box, self.select_anomaly),
                                             (self.scene["towers"], self.tower_box, self.select_tower)):
                widget.set(records[0]["id"] if records else "")
                if records:
                    select()
            self.note.set("Ready · edits pause playback" if self.scene['vehicles'] else 'Empty world: add a vehicle, a tower for coverage, then draw an incident.')
        associations = frame["network"].get("associations", {})
        lines = [f"{n}: {self.scene['vehicles'][n].get('role', 'both')} · {a['tower_id'] or 'NO COVERAGE'} · knows {', '.join(frame['knowledge'].get(n, [])) or 'none'}" for n, a in associations.items()]
        lines += [f"{e['sim_time']:.1f}s {e['message']}" for e in frame.get("radio_events", [])[-10:]]
        self.network_text.set("\n".join(lines) or "No active vehicles or acknowledged reports")

    def save(self):
        def action():
            self.require()
            scene = deepcopy(self.scene)
            for a in scene["anomalies"]:
                a.pop("event_version", None); a.pop("disabled", None)
            file = filedialog.asksaveasfilename(parent=self.window, defaultextension=".json", filetypes=[("AliveMap scene", "*.json")])
            if file:
                with open(file, "w", encoding="utf-8") as output:
                    json.dump(scene, output, indent=2)
                self.note.set("Saved initial placements, roles, areas and towers. Loading starts a fresh experiment.")
        self.guard(action)

    def load(self):
        def action():
            file = filedialog.askopenfilename(parent=self.window, filetypes=[("AliveMap scene", "*.json")])
            if file:
                scene = read_json(file)
                path = self.app.packages.get(scene["map_id"])
                if not path:
                    raise ValueError("Scene's map package is unavailable")
                self.activate(PackageMapProvider(path), scene)
        self.guard(action)
