"""Small native map selector; SUMO GUI is the primary simulation view."""
import argparse
import json
import queue
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from .lab import LabWorker
from routing_core.maps import read_json

ROOT = Path(__file__).resolve().parents[1]
GROUPS = {"Delhi Urban": ["delhi_urban"], "Gujarat Coast": ["gujarat_coastal"],
          "Manipur Hills": ["manipur_mantripukhri", "manipur_mayangkhang"]}


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
        self.map = tk.StringVar(value="Delhi Urban")
        self.region, self.scenario = tk.StringVar(), tk.StringVar()
        self.status = tk.StringVar(value="Choose a map. Load / Start opens SUMO and checks the MEC connection.")
        self.details = tk.StringVar(value="Semantic incidents are synthetic. Roads, elevation and satellite context use real geographic data.")
        root.title("AliveMap - Map and scenario control")
        root.geometry("780x470")
        frame = ttk.Frame(root, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="AliveMap", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Real roads · independent vehicle routing · physical MEC").pack(anchor="w", pady=(0, 14))
        self.map_box = self.combo(frame, "Map", self.map, list(GROUPS))
        self.region_box = self.combo(frame, "Subregion", self.region, [])
        self.scenario_box = self.combo(frame, "Scenario", self.scenario, [])
        self.map_box.bind("<<ComboboxSelected>>", lambda e: self.select_map())
        self.region_box.bind("<<ComboboxSelected>>", lambda e: self.select_region())
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=12)
        for label, action in [("Load / Start", self.load), ("Pause", lambda: self.send("pause")),
                              ("Resume", lambda: self.send("play")), ("Step", lambda: self.send("step")),
                              ("Reset", lambda: self.send("reset")), ("Reconnect", lambda: self.send("refresh"))]:
            ttk.Button(buttons, text=label, command=action).pack(side="left", padx=2)
        buttons2 = ttk.Frame(frame)
        buttons2.pack(fill="x")
        for label, state in [("Report incident", "warning"), ("Close road", "closed"), ("Clear incident", "clear")]:
            ttk.Button(buttons2, text=label, command=lambda s=state: self.send("report", s)).pack(side="left", padx=2)
        ttk.Label(frame, textvariable=self.status, wraplength=730).pack(anchor="w", pady=15)
        ttk.Label(frame, textvariable=self.details, wraplength=730).pack(anchor="w")
        self.select_map()
        self.worker.start()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll)

    def combo(self, frame, label, variable, values):
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=label, width=12).pack(side="left")
        box = ttk.Combobox(row, textvariable=variable, values=values, state="readonly", width=65)
        box.pack(side="left", fill="x", expand=True)
        return box

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
            if (path/manifest["scenario"]).is_file():
                choices = [read_json(path/manifest["scenario"])["scenario_id"]]
        self.scenario_box["values"] = choices
        self.scenario.set(choices[0] if choices else "Package needs build - see map runbook")

    def load(self):
        path = self.packages.get(self.region.get())
        if not path or self.scenario.get().startswith("Package needs"):
            self.status.set(f"Not built: run python -m geospatial.build {self.region.get()}")
            return
        self.status.set("Loading selected map; stopping the previous simulation and creating a fresh epoch…")
        self.worker.commands.put(("load", (str(path), None)))

    def send(self, action, value=None):
        self.worker.commands.put((action, value, self.epoch))

    def poll(self):
        try:
            while True:
                update = self.worker.updates.get_nowait()
                if update["kind"] == "frame":
                    self.epoch = update["run_id"]
                    self.status.set(f"{update['map_id']} | {update['scenario_id']}\nEpoch {self.epoch}\n"
                                    f"t={update['time']:.1f}s | {'Running' if update['playing'] else 'Paused'} | MEC {'reachable' if update['healthy'] else 'unavailable'} | {update['state']}")
                    self.details.set("\n".join(update["decisions"].values()) + ("\nLast error: "+update["last_error"] if update.get("last_error") else ""))
                elif update["kind"] == "error":
                    self.status.set("Paused - last error: "+update["message"])
                elif update["kind"] in ("loading", "finished"):
                    self.status.set(update["message"])
                elif update["kind"] == "stopped" and self.closing:
                    self.root.destroy()
                    return
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def close(self):
        self.closing = True
        self.worker.commands.put(("stop", None))
        self.status.set("Closing SUMO and clearing this epoch's own event…")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mec-url", default="http://127.0.0.1:18765")
    parser.add_argument("--semantics-url", default=None)
    parser.add_argument("--output", default="runs/maps")
    args = parser.parse_args()
    args.gui, args.defer_start, args.map_package, args.scenario = True, True, None, None
    root = tk.Tk()
    MapLauncher(root, args)
    root.mainloop()


if __name__ == "__main__":
    main()
