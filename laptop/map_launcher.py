"""Native geographic simulation: live SUMO positions on sharp interactive maps."""
import argparse
import queue
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from .lab import LabWorker
from .map_canvas import MapCanvas, LABELS, color_for, label_for
from .route_minimap import RouteMiniMap
from routing_core.maps import read_json

ROOT = Path(__file__).resolve().parents[1]
GROUPS = {"Delhi Urban": ["delhi_urban"], "Gujarat Coast": ["gujarat_coastal"],
          "Manipur Hills": ["manipur_mantripukhri", "manipur_mayangkhang"]}
DEMOS = {"Delhi congestion": "delhi_urban", "Gujarat flood": "gujarat_coastal",
         "Mantripukhri landslide": "manipur_mantripukhri", "Mayangkhang closure": "manipur_mayangkhang"}
INCIDENTS = {"Congestion": "congestion", "Flood (0.25 m)": "flood", "Landslide / road closure": "landslide"}


def clock_text(seconds):
    hours, remainder = divmod(max(0, seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{seconds:04.1f}"


def available_packages():
    result = {}
    for ids in GROUPS.values():
        for package_id in ids:
            folder = ROOT/"map_packages"/package_id
            if (folder/"active.json").exists():
                path = folder/read_json(folder/"active.json")["revision"]
                if (path/"manifest.json").exists():
                    result[package_id] = path
    return result


class MapLauncher:
    def __init__(self, root, args):
        self.root, self.worker = root, LabWorker(args)
        self.packages, self.epoch, self.closing = available_packages(), None, False
        self.loading = False
        self.ui_errors = []
        root.report_callback_exception = self.callback_error
        self.frame, self.provider, self.scenario_data = None, None, None
        self.map = tk.StringVar(value="Delhi Urban")
        self.region, self.scenario = tk.StringVar(), tk.StringVar()
        self.mode, self.speed, self.layer = tk.StringVar(value="Local demo (no SSH)"), tk.StringVar(value="20x"), tk.StringVar(value="Streets")
        if getattr(args, 'remote', False):
            self.mode.set('Physical MEC (HTTPS / SSH)')
        self.sumo_gui = tk.BooleanVar(value=False)
        self.incident = tk.StringVar(value="Congestion")
        self.pause_on_change = tk.BooleanVar(value=True)
        self.clock = tk.StringVar(value="SIM 00:00:00.0   |   WALL 00:00:00.0")
        self.comparison = tk.StringVar(value="Compare the same seeded trips with and without an incident.")
        self.wall_started, self.completed_runs = None, {}
        self.status = tk.StringVar(value="Ready. Open playground tools to build a scenario, or choose a guided demo.")
        self.story = tk.StringVar(value="Real OSM roads. SUMO moves the vehicles; agents compute their own routes. Incidents are synthetic.")
        self.vehicle_detail = tk.StringVar(value="Track Blue, Orange or Green to inspect its actual position and intended path.")
        self.tile_status = tk.StringVar(value="Drag to pan · wheel or + / − to zoom · colored circles are vehicles")
        self.rate_sample = None
        from .desktop_ui import build_workspace
        build_workspace(self)
        from .playground_editor import PlaygroundEditor
        self.editor = PlaygroundEditor(self, parent=self.inspector)
        self.select_map()
        self.worker.start()
        self.set_speed()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(80, self.poll)
        root.after(100, self.tick_clock)
        if getattr(args, "playground", False):
            root.after(150, lambda: self.editor.open_scene(True))

    def callback_error(self, kind, error, trace):
        import traceback
        self.ui_errors.append(str(error))
        self.status.set('Interface error: '+str(error))
        self.story.set('The error was recorded. Simulation controls remain available.')
        self.worker.commands.put(('pause',None))
        if hasattr(self,'history'):
            self.history.configure(state='normal')
            self.history.insert('end','UI ERROR · '+str(error)+'\n')
            self.history.see('end');self.history.configure(state='disabled')
        traceback.print_exception(kind,error,trace)

    def connection_hint(self):
        if not self.frame:
            return 'MEC has not been checked. Load a scene to connect. Click to retry after loading.'
        return ('Connected' if self.frame.get('healthy') else 'Disconnected / paused')+'\n'+self.frame.get('mec_endpoint', self.mode.get())+'\n'+(self.frame.get('last_error') or 'Click to reconnect / refresh. Tower coverage is simulated.')

    def show_settings(self):
        self.diagnostics.select(self.settings_page)

    def toggle_play(self):
        self.send('pause' if self.frame and self.frame.get('playing') else 'play')

    def keyboard_play(self, event):
        if event.widget.winfo_class() not in ('TEntry', 'TCombobox', 'Text', 'Entry'):
            self.toggle_play()
            return 'break'

    def keyboard_step(self, event):
        if event.widget.winfo_class() not in ('TEntry', 'TCombobox', 'Text', 'Entry'):
            self.send('step')
            return 'break'

    def faster(self):
        speeds = [1,2,5,10,20,50,100]
        current = float(self.speed.get().rstrip('x'))
        self.speed.set(str(next((s for s in speeds if s > current), 100))+'x')
        self.set_speed()

    def toggle_minimap(self):
        if self.minimap.winfo_ismapped():
            self.minimap.place_forget()
        else:
            self.minimap.place(x=12, rely=1, y=-62, anchor='sw', width=270, height=175)

    def select_fleet_vehicle(self, name):
        self.track(name)
        if self.editor and self.editor.scene and name in self.editor.scene['vehicles']:
            self.editor.vehicle_box.set(name)
            self.editor.select_vehicle()

    def new_vehicle(self):
        self.open_playground()
        self.editor.tabs.select(self.editor.vehicle_page)
        names = self.editor.scene['vehicles'] if self.editor.scene else {}
        index = 1
        while 'vehicle-'+str(index) in names:
            index += 1
        self.editor.vehicle_box.set('')
        self.editor.vehicle.set('vehicle-'+str(index))
        self.editor.origin_edge.set(''); self.editor.destination_edge.set('')
        self.editor.origin = self.editor.destination = None
        self.canvas.pins = {}
        self.canvas.redraw()
        self.editor.note.set('New vehicle: place A origin and B destination pins, choose role, then Save vehicle.')

    def render_fleet(self, expanded=None):
        from .desktop_ui import Hint
        if expanded is not None:
            self.fleet_expanded = expanded
        names = tuple(self.frame.get('vehicle_status', {})) if self.frame else ()
        signature = (names, self.fleet_expanded, self.canvas.selected)
        if signature == self.fleet_signature:
            return
        self.fleet_signature = signature
        for child in self.fleet_panel.winfo_children():
            child.destroy()
        title = ttk.Button(self.fleet_panel, text='▾ Fleet' if self.fleet_expanded else '◉', width=14 if self.fleet_expanded else 3,
            command=lambda: self.render_fleet(not self.fleet_expanded))
        title.pack(fill='x'); Hint(title, 'Expand / collapse vehicle legend')
        title.bind('<Enter>', lambda e: self.render_fleet(True), add='+')
        for name in names:
            row = ttk.Frame(self.fleet_panel); row.pack(fill='x')
            label = '● '+label_for(name) if self.fleet_expanded else '●'
            button = tk.Button(row, text=label, fg=color_for(name), bg='white' if name == self.canvas.selected else '#edf2f7',
                relief='flat', borderwidth=0, font=('Segoe UI',10,'bold'), anchor='w', cursor='hand2',
                command=lambda n=name: self.select_fleet_vehicle(n))
            button.pack(side='left', fill='x', expand=True)
            Hint(button, lambda n=name: n+' · '+(self.frame or {}).get('vehicle_status',{}).get(n,'')+'\nClick to follow and load vehicle settings')
            if self.fleet_expanded:
                gear = ttk.Button(row, text='⚙', width=2, command=lambda n=name: self.configure_vehicle(n))
                gear.pack(side='right'); Hint(gear, 'Edit role, destination and routing profile')
        add = ttk.Button(self.fleet_panel, text='+ Vehicle' if self.fleet_expanded else '+', width=3, command=self.new_vehicle)
        add.pack(fill='x'); Hint(add, 'Add a vehicle to the playground')

    def configure_vehicle(self, name):
        self.select_fleet_vehicle(name)
        if self.editor:
            self.editor.tabs.select(self.editor.vehicle_page)

    def draw_timeline(self):
        canvas = self.timeline
        canvas.delete('all')
        width = max(80, canvas.winfo_width()-12)
        elapsed = self.frame.get('time',0) if self.frame else 0
        span = max(120, (int(elapsed/120)+1)*120)
        canvas.create_line(4,12,width,12,fill='#cbd5e1',width=4)
        end = 4+(width-4)*elapsed/span
        canvas.create_line(4,12,end,12,fill='#2563eb',width=4)
        if self.frame:
            for records in self.frame.get('route_history',{}).values():
                for record in records:
                    x=4+(width-4)*record['sim_time']/span
                    canvas.create_line(x,5,x,19,fill='#f59e0b',width=2)
        canvas.create_oval(end-4,8,end+4,16,fill='#2563eb',outline='')
        canvas.create_text(width,24,anchor='se',text=f'{elapsed:.1f} / {span:g} s',fill='#64748b',font=('Consolas',8))

    def combo(self, frame, label, variable, values):
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=label, width=10).pack(side="left")
        box = ttk.Combobox(row, textvariable=variable, values=values, state="readonly", width=18)
        box.pack(side="left", fill="x", expand=True)
        from .desktop_ui import Hint
        Hint(box, {'Map':'Select a geographic map, then load an example or run a comparison.',
            'Subregion':'Select the road extract within this map.',
            'Incident':'Incident type for the guided comparison; playground incidents are edited at left.',
            'MEC':'Local runs on this laptop. Physical sends reports to your configured MEC over HTTPS. Applies on next load.',
            'Map layer':'Zoomable streets or topographic background.'}.get(label,label))
        return box

    def button_row(self, parent, buttons):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=3)
        for label, action in buttons:
            ttk.Button(row, text=label, command=action).pack(side="left", fill="x", expand=True, padx=1)

    def select_map(self):
        values = GROUPS[self.map.get()]
        self.region_box["values"] = values
        self.region.set(values[0])
        self.select_region()

    def select_region(self):
        path = self.packages.get(self.region.get())
        choices = []
        if path:
            manifest = read_json(path/"manifest.json")
            self.incident.set(next(label for label, kind in INCIDENTS.items() if kind == manifest["demonstration"]))
            if (path/manifest["scenario"]).is_file():
                choices = [read_json(path/manifest["scenario"])["scenario_id"]]
        self.scenario_box["values"] = choices
        self.scenario.set(choices[0] if choices else "Package needs build")

    def quick_demo(self, package_id):
        self.map.set(next(group for group, ids in GROUPS.items() if package_id in ids))
        self.select_map()
        self.region.set(package_id)
        self.select_region()
        self.load()

    def load(self, incident_kind=None):
        path = self.packages.get(self.region.get())
        if not path or self.scenario.get().startswith("Package needs"):
            self.status.set(f"Build this map first: python -m geospatial.build {self.region.get()}")
            return
        incident_kind = incident_kind or INCIDENTS[self.incident.get()]
        self.status.set("Loading identical seeded trips with "+("no incident" if incident_kind == "none" else incident_kind+" at t=20s"))
        self.story.set("No automatic incident in this run. Apply one manually whenever you want." if incident_kind == "none" else
                       "Incident at t=20s, held until Clear. The overview retains old dashed paths; routing decisions pause for inspection.")
        options = {"mec_mode": "local" if self.mode.get().startswith("Local") else "physical", "gui": self.sumo_gui.get(),
                   "incident_kind": incident_kind, "incident_at": 20, "pause_on_change": self.pause_on_change.get(), "playground_scene": None}
        self.worker.commands.put(("load", (str(path), None, options)))
        self.set_speed()

    def set_speed(self):
        self.worker.commands.put(("speed", float(self.speed.get().rstrip("x"))))

    def open_playground(self):
        if not self.editor:
            from .playground_editor import PlaygroundEditor
            self.editor = PlaygroundEditor(self)
        self.editor.window.lift()
        if self.frame:
            self.editor.update(self.frame)

    def tick_clock(self):
        if self.closing:
            return
        elapsed = time.monotonic()-self.wall_started if self.wall_started else 0
        sim = self.frame["time"] if self.frame else 0
        paused = "  PAUSED" if self.frame and not self.frame["playing"] else ""
        self.clock.set(f"SIM {clock_text(sim)}   |   WALL {clock_text(elapsed)}{paused}")
        self.root.after(100, self.tick_clock)

    def update_comparison(self, frame):
        key = frame["map_id"]
        kind = frame.get("comparison_condition", "legacy")
        if frame["complete"]:
            self.completed_runs[(key, kind)] = {"counts": frame["reroute_counts"].copy(), "arrivals": frame["arrival_times"].copy()}
        clear = self.completed_runs.get((key, "none"))
        text = "Without incident: "+("not run yet" if not clear else " / ".join(f"{label_for(name)} {clock_text(t)}" for name, t in clear["arrivals"].items()))
        counts = " / ".join(f"{label_for(name)} {count}" for name, count in frame["reroute_counts"].items())
        self.comparison.set(text+f"\nCurrent: {kind} · actual reroutes: {counts}"+ (" · no feasible route: "+", ".join(label_for(n) for n in frame["blocked"]) if frame["blocked"] else ""))

    def send(self, action, value=None):
        if action == "report" and self.frame and self.frame.get("playground"):
            self.open_playground()
            self.editor.note.set("Select an anomaly here, then Publish operator incident or Clear selected. Add / update leaves it for vehicle detection.")
            return
        self.worker.commands.put((action, value, self.epoch))

    def track(self, name):
        self.canvas.track(name)
        self.show_vehicle()
        self.render_fleet()

    def overview(self):
        self.canvas.all_routes = True
        self.canvas.overview()

    def show_vehicle(self):
        if not self.frame or not self.provider:
            return
        name = self.canvas.selected
        if name not in self.frame["vehicle_status"]:
            self.vehicle_detail.set("Empty playground. Open tools to place vehicles, anomalies and simulated towers.")
            self.profile.delete("all")
            return
        state = self.frame["vehicles"].get(name)
        status = self.frame["vehicle_status"][name]
        if state:
            edge = self.provider.edges.get(state["edge"])
            road = (edge.get("name") or state["edge"]) if edge else state["edge"]
            osm = ", ".join(edge["osm_ids"]) if edge else "junction"
            text = f"{label_for(name)} · {state['speed']*3.6:.1f} km/h · {road} · OSM way {osm}\n"+self.frame["decisions"].get(name, "Following its initial computed route")
            self.draw_profile(state["route"])
        else:
            text = f"{label_for(name)}: {status}. "+("Waiting for safe insertion; grey marker = spawn location." if status == "queued" else "Destination reached. Choose another vehicle or replay.")
            self.profile.delete("all")
            self.profile.create_text(12, 20, anchor="w", text=label_for(name)+": "+status)
        self.vehicle_detail.set(text)

    def draw_profile(self, route):
        self.profile.delete("all")
        samples, distance = [], 0
        for eid in route:
            edge, attr = self.provider.edges[eid], self.provider.attributes[eid]
            if attr.get("elevation_quality") == "valid_dsm_derived":
                for d, h in zip(attr.get("sample_distances_m", []), attr.get("elevation_samples_m", [])):
                    samples.append((distance+d, h))
            distance += edge["length_m"]
        if len(samples) < 2:
            self.profile.create_text(10, 22, anchor="w", text="No valid DEM samples for the remaining route; elevation is not invented.")
            return
        low, high = min(h for d, h in samples), max(h for d, h in samples)
        width = max(200, self.profile.winfo_width()-100)
        points = [(70+d/max(distance, 1)*width, 75-(h-low)/max(10, high-low)*45) for d, h in samples]
        self.profile.create_text(10, 12, anchor="w", text=f"Remaining route elevation: {low:.0f}–{high:.0f} m · Copernicus 30 m DSM, approximate")
        self.profile.create_line(*[v for point in points for v in point], fill="#447a46", width=2)
        self.profile.create_text(70, 90, anchor="w", text="Now")
        self.profile.create_text(width+70, 90, anchor="e", text=f"Destination · {distance/1000:.1f} km")

    def poll(self):
        try:
            pending = []
            while True:
                try:
                    pending.append(self.worker.updates.get_nowait())
                except queue.Empty:
                    break
            # Coalesce only adjacent visual snapshots; lifecycle and log events
            # retain ordering, and the simulation never skips a SUMO step.
            updates = []
            for item in pending:
                if updates and item['kind'] == updates[-1]['kind'] == 'frame':
                    updates[-1] = item
                else:
                    updates.append(item)
            for update in updates:
                kind = update["kind"]
                if kind in ("ready", "report", "decision", "snapshot", "error", "finished", "route_review", "radio", "edit_error", "cleanup_error", "busy") and update.get("message"):
                    self.history.configure(state="normal")
                    self.history.insert("end", f"t={update.get('sim', 0):.1f}s · {update['message']}\n")
                    if int(self.history.index('end-1c').split('.')[0]) > 1200:
                        self.history.delete('1.0', '201.0')
                    self.history.see("end")
                    self.history.configure(state="disabled")
                if kind == "map_loaded":
                    self.frame = None
                    self.provider, self.scenario_data = update["provider"], update["scenario"]
                    self.canvas.set_map(self.provider, self.scenario_data)
                    self.minimap.set_map(self.provider)
                    self.rate_sample = None
                    self.wall_started = time.monotonic()
                    self.history.configure(state="normal")
                    self.history.delete("1.0", "end")
                    self.history.configure(state="disabled")
                elif kind == "frame":
                    self.epoch, self.frame = update["run_id"], update
                    backend = "LOCAL DEMO API" if update["mec_mode"] == "local" else "PHYSICAL MEC"
                    rate, now = "", time.monotonic()
                    if self.rate_sample and now-self.rate_sample[0] >= 1:
                        rate = f" · measured {(update['time']-self.rate_sample[1])/(now-self.rate_sample[0]):.1f}x"
                    if not self.rate_sample or now-self.rate_sample[0] >= 2:
                        self.rate_sample = (now, update["time"])
                    self.status.set(f"{update['map_id']} · {'Running' if update['playing'] else 'Paused'} · target {update['requested_speed']:g}x{rate} · {backend} · {update['state']} · {len(update['vehicles'])} active / {len(update['arrived'])} arrived")
                    if update['mec_mode'] == 'physical' and update.get('mec_endpoint'):
                        self.status.set(self.status.get()+' · '+update['mec_endpoint'])
                    if update.get("last_error"):
                        self.story.set("Paused: "+update["last_error"])
                    self.play_button.configure(text='Ⅱ' if update['playing'] else '▶')
                    self.loading = False
                    self.connection_led.configure(text='● LOCAL' if update['mec_mode']=='local' else '● MEC',
                        foreground='#059669' if update['healthy'] else '#dc2626', background='#d1fae5' if update['healthy'] else '#fee2e2')
                    self.render_fleet()
                    self.draw_timeline()
                    self.canvas.update_frame(update)
                    self.minimap.update_frame(update)
                    self.update_comparison(update)
                    self.show_vehicle()
                    if self.editor:
                        self.editor.update(update)
                    if update.get("playground"):
                        self.comparison.set("PLAYGROUND · vehicle perception → MEC H3 → tower-scoped delivery → individual routes")
                elif kind == "scene_changed":
                    self.scenario_data = update["scenario"]
                    self.canvas.scenario = self.scenario_data
                    if self.canvas.selected not in self.scenario_data["vehicles"]:
                        self.canvas.selected = next(iter(self.scenario_data["vehicles"]), "")
                    self.minimap.bounds, self.minimap.cache_key = None, None
                elif kind == "edit_error":
                    self.story.set(update["message"])
                    if self.editor:
                        self.editor.note.set(update["message"])
                elif kind == "report":
                    self.story.set(update["message"]+"\nEach vehicle evaluates that same semantic fact independently.")
                elif kind == "decision":
                    self.story.set(update["message"])
                elif kind == "error":
                    self.loading = False
                    self.status.set("Paused - "+update["message"])
                    self.connection_led.configure(foreground='#ef4444')
                elif kind in ("loading", "finished", "route_review"):
                    if kind=='loading':
                        self.loading = True
                        self.connection_led.configure(foreground='#d97706',background='#fef3c7')
                    self.story.set(update["message"])
                elif kind == "stopped" and self.closing:
                    self.canvas.close()
                    self.root.destroy()
                    return
        except queue.Empty:
            pass
        self.root.after(80, self.poll)

    def close(self):
        self.closing = True
        self.worker.commands.put(("stop", None))
        self.status.set("Closing this experiment and clearing its own incident…")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mec-url", default=None)
    parser.add_argument("--semantics-url", default=None)
    parser.add_argument("--playground-url", default=None, help="Override private MEC endpoint configuration")
    parser.add_argument("--output", default="runs/maps")
    parser.add_argument("--playground", action="store_true", help="Open the editable scenario tools on launch")
    parser.add_argument('--remote', action='store_true', help='Select the configured physical MEC backend')
    args = parser.parse_args()
    args.gui, args.defer_start, args.map_package, args.scenario, args.mec_mode = False, True, None, None, "local"
    root = tk.Tk()
    MapLauncher(root, args)
    root.mainloop()


if __name__ == "__main__":
    main()
