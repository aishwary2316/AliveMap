"""Fixed racing-style network overview derived from the actual canonical graph."""
import math
import tkinter as tk

from shapely.geometry import box

from .map_canvas import COLORS, LABELS


def fit_transform(bounds, width, height, margin=14):
    west, south, east, north = bounds
    scale = min((width-2*margin)/max(east-west, 1), (height-2*margin)/max(north-south, 1))
    cx, cy = (west+east)/2, (south+north)/2
    return lambda x, y: (width/2+(x-cx)*scale, height/2-(y-cy)*scale)


class RouteMiniMap(tk.Canvas):
    def __init__(self, parent):
        super().__init__(parent, background="#f8fafc", highlightbackground="#64748b", highlightthickness=1)
        self.provider, self.frame, self.bounds, self.cache_key = None, None, None, None
        self.expanded = False
        self.create_text(170, 80, width=300, text="Start a demo to see available roads, current routes and dashed old routes.", fill="#64748b")
        self.bind("<Configure>", lambda event: self.draw())
        self.bind("<Double-Button-1>", self.toggle_size)

    def toggle_size(self, event=None):
        self.expanded = not self.expanded
        self.place_configure(width=min(640, self.master.winfo_width()-24) if self.expanded else 340,
                             height=min(360, self.master.winfo_height()-75) if self.expanded else 220)

    def set_map(self, provider):
        self.provider, self.frame, self.bounds, self.cache_key = provider, None, None, None
        self.delete("all")

    def update_frame(self, frame):
        self.frame = frame
        if self.bounds is None:
            paths = list(frame["baseline_routes"].values())
            points = [xy for path in paths for eid in path for xy in self.provider.edges[eid]["shape_xy"]]
            xs, ys = zip(*points)
            pad = max(150, math.hypot(max(xs)-min(xs), max(ys)-min(ys))*0.12)
            self.bounds = (min(xs)-pad, min(ys)-pad, max(xs)+pad, max(ys)+pad)
        # Expand only when a real computed detour leaves the original fixed view.
        points = [xy for path in frame["planned_routes"].values() for eid in path for xy in self.provider.edges[eid]["shape_xy"]]
        if points:
            xs, ys = zip(*points)
            self.bounds = (min(self.bounds[0], min(xs)-80), min(self.bounds[1], min(ys)-80),
                           max(self.bounds[2], max(xs)+80), max(self.bounds[3], max(ys)+80))
        self.draw()

    def path(self, route, project):
        return [v for eid in route for xy in self.provider.edges[eid]["shape_xy"] for v in project(*xy)]

    def draw(self):
        if not self.provider or not self.frame or not self.bounds:
            return
        width, height = self.winfo_width(), self.winfo_height()
        if width < 20 or height < 20:
            return
        project = fit_transform(self.bounds, width, height-54, margin=18)
        cache_key = (width, height, self.bounds)
        if cache_key != self.cache_key:
            self.delete("all")
            for position in self.provider.tree.query(box(*self.bounds)):
                eid = self.provider.edge_ids[int(position)]
                if "passenger" in self.provider.edges[eid]["allowed"]:
                    self.create_line(*self.path([eid], project), fill="#cbd1d8", width=1, tags="roads")
            self.cache_key = cache_key
        self.delete("overlay")
        frame = self.frame
        for name, route in frame["planned_routes"].items():
            route = frame["driven_edges"][name] if name in frame["blocked"] else route
            points = self.path(route, project)
            if len(points) >= 4:
                # Small cartographic offsets keep both vehicles visible on shared roads.
                offset = {"cautious": -2, "standard": 2, "unaffected": 0}[name]
                styled = [value+offset if i % 2 == 0 else value for i, value in enumerate(points)]
                self.create_line(*styled, fill=COLORS[name], width=2, tags="overlay")
        # Old Blue can share the road with current Orange: draw dashes above solids
        # so the historical path cannot be hidden by an unchanged vehicle's route.
        for name, records in frame["route_history"].items():
            for record in records[-4:]:
                points = self.path(record["old"], project)
                if len(points) >= 4:
                    self.create_line(*points, fill=COLORS[name], width=2, dash=(5, 4), tags="overlay")
        for name, vehicle in frame["vehicles"].items():
            x, y = project(*vehicle["position"])
            self.create_oval(x-4, y-4, x+4, y+4, fill=COLORS[name], outline="white", tags="overlay")
            if name in frame["blocked"]:
                self.create_text(x+6, y-8, text="STOP", anchor="w", fill="#be123c", font=("Segoe UI", 8, "bold"), tags="overlay")
        for fact in frame.get("facts", []):
            geometry = self.provider.geometry_to_xy(fact["geometry"])
            x, y = project(geometry.centroid.x, geometry.centroid.y)
            self.create_rectangle(x-4, y-4, x+4, y+4, fill="#ef4444", outline="white", tags="overlay")
        self.create_rectangle(0, height-54, width, height, fill="#f8fafc", outline="", tags="overlay")
        self.create_text(8, height-43, anchor="w", text="ROUTE OVERVIEW · double-click to resize", font=("Segoe UI", 9, "bold"), tags="overlay")
        self.create_text(8, height-26, anchor="w", text="Grey roads · solid current · dashed old", font=("Segoe UI", 8), tags="overlay")
        text = "  ".join(f"{LABELS[name]}: {count}" for name, count in frame["reroute_counts"].items())
        self.create_text(8, height-11, anchor="w", text="Reroutes · "+text, font=("Segoe UI", 8), tags="overlay")
