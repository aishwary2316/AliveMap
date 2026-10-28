"""Visible, initially paused routing lab. Run: python -m laptop.lab"""
import argparse
import json
import queue
import threading
import time
import tkinter as tk
import math
from pathlib import Path
from tkinter import ttk

import h3

from .live_session import COLORS, FLEET, NAMES, LiveSession
from .network import load


class LabWorker(threading.Thread):
    def __init__(self, args):
        super().__init__(name="AliveMap-SUMO", daemon=False)
        self.args = args
        self.commands, self.updates = queue.Queue(), queue.Queue()
        self.session = None
        self.playing, self.automatic, self.healthy = False, False, False
        self.delay, self.phase = 0.25, 0
        self.last_poll = 0
        self.last_error = None
        self.speed, self.step_batch = 2.0, 1

    def emit(self, kind, **data):
        self.updates.put({"kind": kind, **data})

    def reset(self, automatic=False):
        self.playing, self.healthy = False, False
        if self.session:
            self.session.close()
        self.session = None
        backend = "local demo API" if getattr(self.args, "mec_mode", "physical") == "local" else "physical MEC"
        self.emit("loading", message=f"Loading SUMO and checking {backend}…")
        if getattr(self.args, "map_package", None):
            from .geo_session import ScenarioController
            factory = None
            if getattr(self.args, "mec_mode", "physical") == "local":
                from fastapi.testclient import TestClient
                from mec.baseline.main import app
                factory = lambda: TestClient(app)
            self.controller = ScenarioController(self.args, self.emit, http_factory=factory)
            self.session = self.controller.activate(self.args.map_package, getattr(self.args, "scenario", None))
            self.emit("map_loaded", provider=self.session.provider, scenario=self.session.scenario)
        else:
            self.session = LiveSession(self.args, self.emit)
        self.healthy, self.automatic, self.phase = True, automatic, 0
        self.last_error = None
        self.playing = automatic
        self.last_poll = time.monotonic()

    def publish(self):
        if self.session:
            frame = self.session.frame()
            frame.update(playing=self.playing, automatic=self.automatic, healthy=self.healthy, last_error=self.last_error,
                         requested_speed=self.speed, mec_mode=getattr(self.args, "mec_mode", "physical"))
            self.emit("frame", **frame)
            # Project-owned diagnostic snapshot; raw run logs remain ignored.
            path = self.session.output / "current.json"
            path.write_text(json.dumps(frame, indent=2), encoding="utf-8")

    def run(self):
        try:
            try:
                if not getattr(self.args, "defer_start", False):
                    self.reset()
                    self.publish()
            except Exception as exc:
                self.emit("error", message=str(exc))
            while True:
                try:
                    command = self.commands.get(timeout=self.delay if self.playing else 1.0)
                    action, value = command[:2]
                    if len(command) == 3 and command[2] != (self.session.run_id if self.session else None):
                        continue  # Commands captured for an old map cannot affect a new epoch.
                except queue.Empty:
                    action, value = ("tick", None) if self.playing else ("poll", None)
                if action == "stop":
                    break
                try:
                    if action == "load":
                        self.args.map_package, self.args.scenario = value[:2]
                        for key, setting in (value[2] if len(value) > 2 else {}).items():
                            setattr(self.args, key, setting)
                        self.reset(True)
                    elif action == "reset":
                        self.reset(False)
                    elif action == "demo":
                        self.reset(True)
                    elif action == "delay":
                        self.delay = max(0.01, float(value))
                    elif action == "speed":
                        self.speed = max(0.5, min(100, float(value)))
                        self.step_batch = max(1, math.ceil(self.speed/20))
                        self.delay = 0.5*self.step_batch/self.speed
                    elif action == "pause":
                        self.playing = False
                    elif self.session:
                        if action == "play":
                            if not self.healthy:
                                raise RuntimeError("Reconnect to MEC before advancing the simulation.")
                            self.playing = not self.session.complete
                        elif action == "report":
                            self.automatic = False
                            self.emit("busy", message=f"Sending {value.upper()} to the selected MEC backend…")
                            self.session.report(value)
                            self.healthy = True
                        elif action in ("poll", "refresh"):
                            if self.healthy or action == "refresh":
                                self.session.refresh()
                                self.healthy = True
                                self.last_poll = time.monotonic()
                        elif action in ("step", "tick") and not self.session.complete:
                            if not self.healthy:
                                raise RuntimeError("Reconnect to MEC before advancing the simulation.")
                            for _ in range(self.step_batch if action == "tick" else 1):
                                if self.session.complete:
                                    break
                                self.session.step()
                                timeline = self.session.scenario["events"] if hasattr(self.session, "scenario") else [
                                    {"sim_time_s": t, "kind": k} for t, k in zip((1, 45, 100), ("warning", "closed", "clear"))]
                                if self.automatic and self.phase < len(timeline) and self.session.sim_time >= timeline[self.phase]["sim_time_s"]:
                                    self.session.report(timeline[self.phase]["kind"])
                                    self.phase += 1
                            if time.monotonic() - self.last_poll >= 1:
                                self.session.refresh()
                                self.last_poll = time.monotonic()
                            if self.session.complete:
                                self.playing = False
                                self.emit("finished", sim=self.session.sim_time, message="All three vehicles arrived. Reset to explore again.")
                    self.publish()
                except Exception as exc:
                    self.playing, self.healthy = False, False
                    self.last_error = str(exc)
                    self.emit("error", message=str(exc))
                    try:
                        self.publish()
                    except Exception:
                        pass
        finally:
            if self.session:
                self.session.close()
            self.emit("stopped")


class Lab:
    def __init__(self, root, args):
        self.root, self.args = root, args
        self.net, _ = load()
        self.frame = None
        self.closing = False
        self.worker = LabWorker(args)
        self.selected = tk.StringVar(value="cautious")
        self.show_h3 = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Connecting to your physical MEC…")
        self.clock = tk.StringVar(value="Loading")
        self.road_state = tk.StringVar(value="Road: clear")
        self.mode = tk.StringVar(value="Manual: you control the hazard reports")
        self.details = tk.StringVar(value="Select a vehicle to inspect its route and decision.")
        root.title("AliveMap — Live MEC Routing Lab")
        width, height = min(1280, root.winfo_screenwidth()-40), min(860, root.winfo_screenheight()-70)
        root.geometry(f"{width}x{height}+12+12")
        root.minsize(min(1060, width), min(650, height))
        root.configure(bg="#f1f5f9")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#f1f5f9")
        style.configure("TLabel", background="#f1f5f9", foreground="#0f172a", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10), padding=(12, 8))
        style.configure("Title.TLabel", font=("Segoe UI", 24, "bold"))
        style.configure("Clock.TLabel", font=("Segoe UI", 16, "bold"))
        outer = ttk.Frame(root, padding=18)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)
        heading = ttk.Frame(outer)
        heading.grid(row=0, column=0, sticky="ew")
        ttk.Label(heading, text="AliveMap", style="Title.TLabel").pack(side="left")
        ttk.Label(heading, text="  Live SUMO + physical MEC · Routing lab").pack(side="left", padx=10)
        ttk.Label(heading, textvariable=self.clock, style="Clock.TLabel").pack(side="right")
        self.status_label = ttk.Label(outer, textvariable=self.status, wraplength=1150)
        self.status_label.grid(row=1, column=0, sticky="ew", pady=(5, 12))
        controls = ttk.Frame(outer)
        controls.grid(row=2, column=0, sticky="ew")
        self.buttons = []
        for label, action in (("▶ Play", "play"), ("Ⅱ Pause", "pause"), ("Step +0.5 s", "step"),
                              ("Reset / manual", "reset"), ("Replay guided demo", "demo")):
            button = ttk.Button(controls, text=label, command=lambda a=action: self.send(a))
            button.pack(side="left", padx=(0, 6))
            self.buttons.append(button)
        ttk.Label(controls, text="Step delay").pack(side="left", padx=(12, 4))
        scale = ttk.Scale(controls, from_=0.05, to=1.0, value=0.25,
                          command=lambda value: self.send("delay", value))
        scale.pack(side="left", fill="x", expand=True)
        self.mode_label = ttk.Label(outer, textvariable=self.mode)
        self.mode_label.grid(row=3, column=0, sticky="ew", pady=(10, 8))
        middle = ttk.Frame(outer)
        middle.grid(row=4, column=0, sticky="nsew")
        self.canvas = tk.Canvas(middle, background="#ffffff", highlightthickness=1,
                                highlightbackground="#cbd5e1", width=740, height=500)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda event: self.draw())
        tabs = ttk.Notebook(middle, width=315)
        tabs.pack(side="right", fill="y", padx=(12, 0))
        panel = ttk.Frame(tabs, padding=10)
        vehicle_panel = ttk.Frame(tabs, padding=10)
        tabs.add(panel, text="Road controls")
        tabs.add(vehicle_panel, text="Vehicle decisions")
        ttk.Label(panel, text="Control the road", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(panel, textvariable=self.road_state, style="Clock.TLabel").pack(anchor="w", pady=6)
        for label, state in (("Warning — compare risk policies", "warning"),
                             ("Close road — both must avoid it", "closed"),
                             ("Clear road — recompute shortest", "clear")):
            button = ttk.Button(panel, text=label, command=lambda s=state: self.send("report", s))
            button.pack(fill="x", pady=3)
            self.buttons.append(button)
        ttk.Button(panel, text="Refresh / reconnect MEC", command=lambda: self.send("refresh")).pack(fill="x", pady=(8, 5))
        ttk.Checkbutton(panel, text="Show MEC H3 cell after a report", variable=self.show_h3,
                        command=self.draw).pack(anchor="w", pady=8)
        ttk.Label(vehicle_panel, text="Inspect a vehicle", font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(8, 5))
        for vehicle in FLEET:
            tk.Radiobutton(vehicle_panel, text=NAMES[vehicle], value=vehicle, variable=self.selected,
                           command=self.select_vehicle, bg="#f1f5f9", fg=COLORS[vehicle],
                           font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x")
        ttk.Label(vehicle_panel, textvariable=self.details, wraplength=285, justify="left").pack(fill="x", pady=8)
        ttk.Label(panel, text="Solid dots = actual SUMO positions\nColored lines = remaining computed routes\nPurple dot = reporting probe\nRoad outline = hazard location\n\nNative SUMO window follows these controls.",
                  wraplength=300, justify="left").pack(anchor="w", pady=(8, 0))
        ttk.Label(outer, text="What just happened?", font=("Segoe UI", 12, "bold")).grid(row=5, column=0, sticky="w", pady=(10, 4))
        self.history = tk.Text(outer, height=5, bg="#0f172a", fg="#e2e8f0", relief="flat",
                               font=("Segoe UI", 10), padx=10, pady=7, state="disabled", wrap="word")
        self.history.grid(row=6, column=0, sticky="ew")
        self.worker.start()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.receive)
        self.draw()

    def send(self, action, value=None):
        if not self.closing:
            self.worker.commands.put((action, value))
            if action == "report":
                self.status.set(f"Queued {value.upper()} report to the physical MEC…")

    def message(self, text):
        self.history.configure(state="normal")
        self.history.insert("end", text + "\n")
        self.history.see("end")
        self.history.configure(state="disabled")

    def receive(self):
        try:
            while True:
                update = self.worker.updates.get_nowait()
                kind = update["kind"]
                if kind == "frame":
                    first = self.frame is None
                    self.frame = update
                    self.clock.set(f"t = {update['time']:.1f} s · {'RUNNING' if update['playing'] else 'PAUSED'}")
                    self.road_state.set("Road: " + update["state"].upper())
                    self.mode.set("Guided demo: warning 1s → closure 45s → clear 100s" if update["automatic"] else "Manual: use the road buttons whenever you choose")
                    if update["healthy"]:
                        self.status.set(f"Physical MEC connected · semantic change #{update['version']} · run {update['run_id'][:8]} · Starts paused so you can inspect")
                        self.status_label.configure(foreground="#047857")
                    for button in self.buttons:
                        button.configure(state="normal")
                    self.inspect()
                    self.draw()
                    if first:
                        self.root.lift()
                elif kind == "error":
                    self.status.set("Paused — " + update["message"])
                    self.status_label.configure(foreground="#b91c1c")
                    self.message("ERROR: " + update["message"])
                elif kind == "busy":
                    self.status.set(update["message"])
                elif kind == "loading":
                    self.frame = None
                    self.clock.set("Loading")
                    self.status.set(update["message"])
                    self.draw()
                elif "message" in update:
                    self.message(update["message"])
        except queue.Empty:
            pass
        if self.closing and not self.worker.is_alive():
            self.root.destroy()
        else:
            self.root.after(100, self.receive)

    def inspect(self):
        if not self.frame:
            return
        vehicle = self.selected.get()
        info = self.frame["vehicles"].get(vehicle)
        if vehicle in self.frame["arrived"]:
            text = "Arrived at its destination."
        elif info:
            text = f"Speed: {info['speed']:.1f} m/s\nCurrent road: {info['edge']}\nRemaining route: {len(info['route'])} edges\n\n{self.frame['decisions'].get(vehicle, '')}\n\n" + " → ".join(info["route"])
        else:
            text = "Waiting to enter the network."
        self.details.set(text)

    def select_vehicle(self):
        self.inspect()
        self.draw()

    def draw(self):
        canvas = self.canvas
        canvas.delete("all")
        w, h = max(500, canvas.winfo_width()), max(400, canvas.winfo_height())
        xmin, ymin, xmax, ymax = self.net.getBoundary()
        scale = min((w-100)/(xmax-xmin), (h-90)/(ymax-ymin))
        left, top = (w-(xmax-xmin)*scale)/2, (h-(ymax-ymin)*scale)/2

        def point(xy):
            return left+(xy[0]-xmin)*scale, top+(ymax-xy[1])*scale

        def line(shape, **options):
            coords = [v for xy in shape for v in point(xy)]
            if len(coords) >= 4:
                canvas.create_line(*coords, **options)

        for edge in self.net.getEdges():
            line(edge.getLanes()[0].getShape(), fill="#cbd5e1", width=3)
        for node in self.net.getNodes():
            x, y = point(node.getCoord())
            canvas.create_text(x, y+13, text=node.getID(), fill="#94a3b8", font=("Segoe UI", 8))
        if not self.frame:
            canvas.create_text(w/2, h/2, text="Loading actual SUMO vehicles…", font=("Segoe UI", 18), fill="#334155")
            return
        frame = self.frame
        hazard = self.net.getEdge(frame["hazard_edge"])
        shade = {"clear": "#9333ea", "warning": "#f59e0b", "closed": "#dc2626"}[frame["state"]]
        line(hazard.getLanes()[0].getShape(), fill=shade, width=7, dash=(7, 4))
        if self.show_h3.get() and frame["mapping"]:
            boundary = h3.cell_to_boundary(frame["mapping"][0]["h3_cell"])
            points = [v for lat, lon in boundary for v in point(self.net.convertLonLat2XY(lon, lat))]
            canvas.create_polygon(*points, outline="#a16207", fill="#fef3c7", stipple="gray25", width=2)
        for vehicle, info in sorted(frame["vehicles"].items(), key=lambda item: item[0] == self.selected.get()):
            if vehicle not in FLEET:
                continue
            for eid in info["route"]:
                line(self.net.getEdge(eid).getLanes()[0].getShape(), fill=COLORS[vehicle], width=3 if vehicle == self.selected.get() else 2,
                     dash=(10, 5) if vehicle == "standard" else (3, 3) if vehicle == "unaffected" else ())
        for vehicle, info in frame["vehicles"].items():
            x, y = point(info["position"])
            canvas.create_oval(x-8, y-8, x+8, y+8, fill=COLORS[vehicle], outline="white", width=2)
            offset = {"cautious": -22, "standard": 22, "unaffected": 22, "probe": -22}[vehicle]
            canvas.create_text(x+10, y+offset, text=vehicle, anchor="w", fill=COLORS[vehicle], font=("Segoe UI", 10, "bold"))
        canvas.create_text(16, 15, text="Live TraCI positions · fictional 300 m grid", anchor="nw", fill="#475569", font=("Segoe UI", 10))

    def close(self):
        if self.closing:
            return
        self.closing = True
        self.status.set("Stopping SUMO and clearing this session's own MEC event…")
        for button in self.buttons:
            button.configure(state="disabled")
        self.worker.commands.put(("stop", None))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mec-url", default="http://127.0.0.1:18765")
    parser.add_argument("--semantics-url", default="http://127.0.0.1:18766/semantics")
    parser.add_argument("--output", default="runs/interactive")
    parser.add_argument("--no-sumo-window", dest="gui", action="store_false", default=True)
    args = parser.parse_args()
    root = tk.Tk()
    Lab(root, args)
    root.mainloop()


if __name__ == "__main__":
    main()
