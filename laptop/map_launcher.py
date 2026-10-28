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
        self.frame, self.provider, self.scenario_data = None, None, None
        self.map = tk.StringVar(value="Delhi Urban")
        self.region, self.scenario = tk.StringVar(), tk.StringVar()
        self.mode, self.speed, self.layer = tk.StringVar(value="Local demo (no SSH)"), tk.StringVar(value="20x"), tk.StringVar(value="Streets")
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
        root.title("AliveMap - Geographic simulation")
        root.geometry(f"{min(1280, root.winfo_screenwidth()-60)}x{min(850, root.winfo_screenheight()-80)}+20+20")
        root.minsize(950, 680)
        outer = ttk.Frame(root, padding=8)
        outer.pack(fill="both", expand=True)
        sidebar = ttk.Frame(outer, width=330)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        controls_scroll = tk.Canvas(sidebar, highlightthickness=0, width=310)
        controls_bar = ttk.Scrollbar(sidebar, orient="vertical", command=controls_scroll.yview)
        controls_bar.pack(side="right", fill="y")
        controls_scroll.pack(side="left", fill="both", expand=True)
        controls_scroll.configure(yscrollcommand=controls_bar.set)
        controls = ttk.Frame(controls_scroll, padding=(6, 6, 8, 6))
        controls_item = controls_scroll.create_window((0, 0), window=controls, anchor="nw")
        controls.bind("<Configure>", lambda e: controls_scroll.configure(scrollregion=controls_scroll.bbox("all")))
        controls_scroll.bind("<Configure>", lambda e: controls_scroll.itemconfigure(controls_item, width=e.width))
        view = ttk.Frame(outer)
        view.pack(side="left", fill="both", expand=True)
        ttk.Label(controls, text="AliveMap", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(controls, text="Synthetic incidents · real OSM roads", font=("Segoe UI", 9)).pack(anchor="w")
        self.editor = None
        ttk.Button(controls, text="Open playground tools…", command=self.open_playground).pack(fill="x", pady=4)
        ttk.Label(controls, text="Play guided demo", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(8, 4))
        for label, package_id in DEMOS.items():
            ttk.Button(controls, text="▶  "+label, command=lambda pid=package_id: self.quick_demo(pid)).pack(fill="x", pady=2)
        self.map_box = self.combo(controls, "Map", self.map, list(GROUPS))
        self.region_box = self.combo(controls, "Subregion", self.region, [])
        self.scenario_box = self.combo(controls, "Scenario", self.scenario, [])
        self.scenario_box.master.pack_forget()
        self.combo(controls, "Incident", self.incident, list(INCIDENTS))
        self.map_box.bind("<<ComboboxSelected>>", lambda e: self.select_map())
        self.region_box.bind("<<ComboboxSelected>>", lambda e: self.select_region())
        self.combo(controls, "MEC", self.mode, ["Local demo (no SSH)", "Physical MEC (SSH)"])
        ttk.Checkbutton(controls, text="Also open native SUMO window", variable=self.sumo_gui).pack(anchor="w", pady=3)
        self.button_row(controls, [("Run without incident", lambda: self.load("none")), ("Run with incident", self.load)])
        self.button_row(controls, [("Pause", lambda: self.send("pause")), ("Resume", lambda: self.send("play"))])
        self.button_row(controls, [("Step", lambda: self.send("step")), ("Reset", lambda: self.send("reset")), ("Reconnect", lambda: self.send("refresh"))])
        ttk.Checkbutton(controls, text="Pause to inspect each route change", variable=self.pause_on_change,
                        command=lambda: self.worker.commands.put(("review_mode", self.pause_on_change.get()))).pack(anchor="w")
        box = self.combo(controls, "Time speed", self.speed, ["1x", "2x", "5x", "10x", "20x", "50x", "100x"])
        box.bind("<<ComboboxSelected>>", lambda e: self.set_speed())
        ttk.Label(controls, text="Follow vehicle + intended route", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 2))
        self.button_row(controls, [(label, lambda n=name: self.track(n)) for name, label in LABELS.items()])
        self.button_row(controls, [("All routes / overview", self.overview), ("+", lambda: self.canvas.change_zoom(1)), ("−", lambda: self.canvas.change_zoom(-1))])
        ttk.Label(view, textvariable=self.clock, font=("Segoe UI", 17, "bold")).pack(anchor="w", pady=3)
        ttk.Label(view, textvariable=self.comparison, wraplength=850).pack(anchor="w")
        ttk.Label(view, textvariable=self.status, wraplength=850).pack(anchor="w", pady=3)
        self.canvas = MapCanvas(view, status=self.tile_status.set)
        self.canvas.pack(fill="both", expand=True)
        self.minimap = RouteMiniMap(self.canvas)
        self.minimap.place(x=12, rely=1, y=-60, anchor="sw", width=340, height=220)
        box = self.combo(controls, "Map layer", self.layer, list(self.canvas.sources))
        box.bind("<<ComboboxSelected>>", lambda e: self.canvas.set_source(self.layer.get()))
        self.button_row(controls, [("Apply selected", lambda: self.send("report", INCIDENTS[self.incident.get()])), ("Clear incident", lambda: self.send("report", "clear"))])
        for variable in (self.story,):
            ttk.Label(controls, textvariable=variable, wraplength=300, justify="left").pack(anchor="w", pady=8)
        ttk.Label(view, textvariable=self.tile_status).pack(anchor="w", pady=3)
        ttk.Label(view, textvariable=self.vehicle_detail, wraplength=850).pack(anchor="w", pady=3)
        self.profile = tk.Canvas(view, height=85, background="#f7fafc", highlightthickness=0)
        self.profile.pack(fill="x")
        self.history = tk.Text(view, height=4, wrap="word", font=("Segoe UI", 9), background="#f1f5f9", relief="flat", state="disabled")
        self.history.pack(fill="x", pady=4)
        self.select_map()
        self.worker.start()
        self.set_speed()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(80, self.poll)
        root.after(100, self.tick_clock)
        if getattr(args, "playground", False):
            root.after(150, self.open_playground)

    def combo(self, frame, label, variable, values):
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=label, width=10).pack(side="left")
        box = ttk.Combobox(row, textvariable=variable, values=values, state="readonly", width=22)
        box.pack(side="left", fill="x", expand=True)
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
        self.editor.window.deiconify()
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
            while True:
                update = self.worker.updates.get_nowait()
                kind = update["kind"]
                if kind in ("ready", "report", "decision", "snapshot", "error", "finished", "route_review", "radio", "edit_error") and update.get("message"):
                    self.history.configure(state="normal")
                    self.history.insert("end", f"t={update.get('sim', 0):.1f}s · {update['message']}\n")
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
                    if update.get("last_error"):
                        self.story.set("Paused: "+update["last_error"])
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
                    self.status.set("Paused - "+update["message"])
                elif kind in ("loading", "finished", "route_review"):
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
    parser.add_argument("--mec-url", default="http://127.0.0.1:18765")
    parser.add_argument("--semantics-url", default=None)
    parser.add_argument("--playground-url", default="http://127.0.0.1:18767")
    parser.add_argument("--output", default="runs/maps")
    parser.add_argument("--playground", action="store_true", help="Open the editable scenario tools on launch")
    args = parser.parse_args()
    args.gui, args.defer_start, args.map_package, args.scenario, args.mec_mode = False, True, None, None, "local"
    root = tk.Tk()
    MapLauncher(root, args)
    root.mainloop()


if __name__ == "__main__":
    main()
