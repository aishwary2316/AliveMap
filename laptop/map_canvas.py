"""Native interactive tile map. Positions/routes come exclusively from live SUMO.

Web Mercator is a display projection only: the canonical routing map stays UTM.
Only visible tiles are fetched; OSM responses are cached with their cache headers.
Satellite services are configured explicitly in ignored .local/map-provider.json.
"""
import hashlib
import io
import json
import math
import queue
import time
import tkinter as tk
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageTk

ROOT = Path(__file__).resolve().parents[1]
COLORS = {"cautious": "#2563eb", "standard": "#ea580c", "unaffected": "#059669"}
LABELS = {"cautious": "Blue", "standard": "Orange", "unaffected": "Green"}


def color_for(name):
    palette = ("#9333ea", "#0891b2", "#db2777", "#b45309", "#475569", "#4f46e5")
    return COLORS.get(name, palette[int(hashlib.sha256(name.encode()).hexdigest()[:8], 16) % len(palette)])


def label_for(name):
    return LABELS.get(name, name)


def world_pixel(lon, lat, zoom):
    lat = max(-85.05112878, min(85.05112878, lat))
    scale = 256*2**zoom
    return (lon+180)/360*scale, (1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*scale


def pixel_lonlat(x, y, zoom):
    scale = 256*2**zoom
    return x/scale*360-180, math.degrees(math.atan(math.sinh(math.pi*(1-2*y/scale))))


@dataclass(frozen=True)
class TileSource:
    name: str
    url: str
    attribution: str
    max_zoom: int
    cache: bool = True


def tile_sources():
    sources = {
        "Streets": TileSource("Streets", "https://tile.openstreetmap.org/{z}/{x}/{y}.png", "© OpenStreetMap contributors · openstreetmap.org/copyright", 19),
        "Terrain": TileSource("Terrain", "https://a.tile.opentopomap.org/{z}/{x}/{y}.png", "© OpenStreetMap contributors, SRTM · OpenTopoMap (CC-BY-SA)", 17),
    }
    config = ROOT/".local/map-provider.json"
    if config.is_file():
        custom = json.loads(config.read_text(encoding="utf-8"))
        for name, item in custom.items():
            if not item["url"].startswith("https://") or not all(token in item["url"] for token in ("{z}", "{x}", "{y}")):
                raise ValueError("Tile source needs HTTPS and z/x/y placeholders")
            sources[name] = TileSource(name, item["url"], item["attribution"], min(22, int(item.get("max_zoom", 19))), False)
    return sources


class TileStore:
    def __init__(self, cache=None, fetch=None):
        self.cache = Path(cache or ROOT/".local/tiles")
        self.cache.mkdir(parents=True, exist_ok=True)
        self.fetch = fetch or urllib.request.urlopen

    def load(self, source, z, x, y):
        url = source.url.format(z=z, x=x, y=y)
        key = hashlib.sha256(url.encode()).hexdigest()
        file, meta = self.cache/(key+".tile"), self.cache/(key+".json")
        if source.cache and file.exists() and meta.exists():
            try:
                if json.loads(meta.read_text())["expires"] > time.time():
                    with Image.open(file) as raw:cached=raw.convert('RGB')
                    if cached.size not in ((256,256),(512,512)):raise ValueError('Invalid cached tile size')
                    return cached.resize((256, 256), Image.Resampling.LANCZOS) if cached.size == (512, 512) else cached
            except (OSError,ValueError,KeyError):
                pass  # A partial cache from an interrupted run is refetched.
        request = urllib.request.Request(url, headers={"User-Agent": "AliveMap/0.4 (interactive research map; github.com/aishwary2316/AliveMap)"})
        with self.fetch(request, timeout=4) as response:
            data = response.read(4_000_001)
            control = response.headers.get("Cache-Control", "")
        if len(data) > 4_000_000:
            raise ValueError("Oversize tile response")
        image = Image.open(io.BytesIO(data)).convert("RGB")
        if image.size not in ((256, 256), (512, 512)):
            raise ValueError("Expected a square 256 or 512 pixel map tile")
        if image.size == (512, 512):
            image = image.resize((256, 256), Image.Resampling.LANCZOS)
        if source.cache and "no-store" not in control:
            ttl = 7*86400
            for option in control.split(","):
                if option.strip().startswith("max-age="):
                    ttl = max(0, int(option.strip().split("=")[1]))
            if "no-cache" in control:
                ttl = 0
            file.write_bytes(data)
            meta.write_text(json.dumps({"expires": time.time()+ttl}))
        return image


class MapCanvas(tk.Canvas):
    def __init__(self, parent, status=lambda text: None, **kwargs):
        super().__init__(parent, background="#e8edf1", highlightthickness=0, **kwargs)
        self.status, self.sources = status, tile_sources()
        self.source = self.sources["Streets"]
        self.zoom, self.center = 16, (77.25, 28.63)
        self.provider, self.scenario, self.frame = None, None, None
        self.selected, self.follow, self.all_routes = "cautious", True, False
        self.pool, self.results = ThreadPoolExecutor(max_workers=4), queue.Queue()
        self.local_pool = ThreadPoolExecutor(max_workers=2,thread_name_prefix='AliveMap-roads')
        self.store, self.tiles, self.pending, self.failed = TileStore(), {}, set(), {}
        self.photos, self.drag_origin, self.closed = {}, None, False
        self._previews = {}
        self.wanted = set()
        self.edit_callback, self.edit_points, self.edit_tool = None, [], None
        self.pins, self.pin_callback, self.pin_start, self.drag_pin = {}, None, None, None
        self.on_vehicle_select = None
        self._overlay_mode = True
        self._tile_items = {}
        self._grid_items = {}
        self._redraw_timer = None
        self._drawing = False
        self._grid_cache, self._boundary_cache = {}, {}
        self.show_cells, self.show_towers = True, True
        self.bind("<Configure>", lambda event: self.redraw())
        self.bind("<MouseWheel>", self.wheel)
        self.bind("<ButtonPress-1>", self.begin_drag)
        self.bind("<B1-Motion>", self.drag)
        self.bind("<ButtonRelease-1>", self.end_drag)
        self._drain_timer=self.after(40, self.drain)

    def set_map(self, provider, scenario):
        self.provider, self.scenario, self.frame = provider, scenario, None
        self.pins = {}
        self._grid_cache.clear(); self._boundary_cache.clear()
        self.follow, self.selected = True, next(iter(scenario["vehicles"]), "")
        if self.selected:
            self.center = tuple(provider.edges[scenario["vehicles"][self.selected]["origin"]]["shape_wgs84"][0])
            self.zoom = min(17, self.source.max_zoom)
        else:
            west, south, east, north = provider.manifest["bounds_wgs84"]
            self.center, self.zoom = ((west+east)/2, (south+north)/2), 13
        self.redraw()

    def set_source(self, name):
        self.source = self.sources[name]
        self.zoom = min(self.zoom, self.source.max_zoom)
        self.redraw()

    def update_frame(self, frame):
        self.frame = frame
        if self.follow and self.selected in frame["vehicles"]:
            self.center = tuple(frame["vehicles"][self.selected]["lonlat"])
        elif self.follow and frame.get("vehicle_status", {}).get(self.selected) == "arrived":
            destination = self.scenario["vehicles"][self.selected]["destination"]
            self.center = tuple(self.provider.edges[destination]["shape_wgs84"][-1])
        self.redraw()

    def track(self, name):
        if not self.scenario or name not in self.scenario["vehicles"]:
            return
        self.selected, self.follow = name, True
        self.zoom = min(17, self.source.max_zoom)
        if self.frame and name in self.frame["vehicles"]:
            self.center = tuple(self.frame["vehicles"][name]["lonlat"])
        elif self.scenario:
            arrived = self.frame and self.frame.get("vehicle_status", {}).get(name) == "arrived"
            edge = self.scenario["vehicles"][name]["destination" if arrived else "origin"]
            self.center = tuple(self.provider.edges[edge]["shape_wgs84"][-1 if arrived else 0])
        self.redraw()

    def overview(self):
        self.follow = False
        if not self.scenario:
            return
        points = [xy for vehicle in self.scenario["vehicles"].values() for eid in (vehicle["origin"], vehicle["destination"]) for xy in self.provider.edges[eid]["shape_wgs84"]]
        if not points:
            west, south, east, north = self.provider.manifest["bounds_wgs84"]
            points = [(west, south), (east, north)]
        west, east = min(p[0] for p in points), max(p[0] for p in points)
        south, north = min(p[1] for p in points), max(p[1] for p in points)
        self.center = ((west+east)/2, (south+north)/2)
        for z in range(self.source.max_zoom, 5, -1):
            a, b = world_pixel(west, north, z), world_pixel(east, south, z)
            if b[0]-a[0] < self.winfo_width()-100 and b[1]-a[1] < self.winfo_height()-100:
                self.zoom = z
                break
        self.redraw()

    def screen(self, lon, lat):
        x, y = world_pixel(lon, lat, self.zoom)
        if self._drawing:
            return x-self._left, y-self._top
        cx, cy = world_pixel(*self.center, self.zoom)
        return x-cx+self.winfo_width()/2, y-cy+self.winfo_height()/2

    def change_zoom(self, delta):
        self.zoom = max(6, min(self.source.max_zoom, self.zoom+delta))
        self.redraw()

    def wheel(self, event):
        self.change_zoom(1 if event.delta > 0 else -1)

    def begin_drag(self, event):
        for name, ll in self.pins.items():
            x,y = self.screen(*ll)
            if math.hypot(x-event.x,y-18-event.y) <= 16:
                self.drag_pin = name
                self.follow = False
                if self.pin_start:
                    self.pin_start()
                return
        if self.edit_tool:
            cx, cy = world_pixel(*self.center, self.zoom)
            ll = pixel_lonlat(cx+event.x-self.winfo_width()/2, cy+event.y-self.winfo_height()/2, self.zoom)
            self.edit_points.append(ll)
            if self.edit_tool in ("point", "circle") or self.edit_tool == "rectangle" and len(self.edit_points) == 2:
                self.finish_edit()
            else:
                self.redraw()
            return
        self.drag_origin = (event.x, event.y, world_pixel(*self.center, self.zoom))

    def start_edit(self, tool, callback):
        self.edit_tool, self.edit_callback, self.edit_points, self.follow = tool, callback, [], False
        self.configure(cursor="crosshair")
        self.status("Click the map: "+tool+". Polygon: click vertices then Finish shape in tools. Cancel exits drawing.")

    def finish_edit(self):
        callback, points = self.edit_callback, list(self.edit_points)
        self.cancel_edit()
        if callback:
            callback(points)

    def cancel_edit(self):
        self.edit_tool, self.edit_callback, self.edit_points = None, None, []
        self.configure(cursor="")
        self.redraw()

    def end_drag(self, event):
        self.drag_origin = None
        if self.drag_pin:
            name, self.drag_pin = self.drag_pin, None
            point = self.pins[name]
            if self.pin_callback:
                self.pin_callback(name, point)
            self.redraw()

    def drag(self, event):
        if self.drag_pin:
            cx,cy = world_pixel(*self.center,self.zoom)
            self.pins[self.drag_pin] = pixel_lonlat(cx+event.x-self.winfo_width()/2,
                cy+event.y+18-self.winfo_height()/2,self.zoom)
            self.redraw()
            return
        if self.drag_origin:
            x, y, (cx, cy) = self.drag_origin
            self.follow = False
            self.center = pixel_lonlat(cx+x-event.x, cy+y-event.y, self.zoom)
            self.redraw()

    def request_tile(self, key):
        if key in self.pending or time.monotonic()-self.failed.get(key, -100) < 30:
            return
        local=key[0].startswith(('offline:','grid:'))
        # Never queue an entire old viewport behind slow sockets. The next
        # completion picks from the latest view, not an obsolete FIFO backlog.
        if sum(k[0].startswith(('offline:','grid:'))==local for k in self.pending)>=(2 if local else 4):
            return
        self.pending.add(key)
        source,provider = self.source,self.provider
        def work():
            if self.closed:
                self.results.put((key, None, None))
                return
            try:
                if local:
                    from .offline_tiles import road_tile,grid_tile
                    image=grid_tile(*key[1:]) if key[0].startswith('grid:') else road_tile(provider,*key[1:])
                else:
                    image = self.store.load(source, *key[1:])
                self.results.put((key, image, None))
            except Exception:
                self.results.put((key, None, "Map tiles unavailable; live vehicle/route overlays remain active."))
        (self.local_pool if local else self.pool).submit(work)

    def drain(self):
        if self.closed:
            return
        dirty = False
        try:
            while True:
                key, image, error = self.results.get_nowait()
                self.pending.discard(key)
                if image:
                    self.tiles[key] = image
                    if len(self.tiles) > 300:
                        del self.tiles[next(iter(self.tiles))]
                elif error:
                    self.failed[key] = time.monotonic()
                    self.status(error)
                dirty = True
        except queue.Empty:
            pass
        if dirty:
            self.redraw()
        self._drain_timer=self.after(40, self.drain)

    def _create(self, itemType, args, kw):
        # Keep downloaded tile items alive; only transient overlays are rebuilt.
        # Tk image allocation/teardown otherwise dominates panning/following.
        kw = dict(kw)
        tags = kw.get('tags', ())
        if isinstance(tags,str):
            tags = (tags,)
        kw['tags'] = (*tags, 'overlay' if getattr(self, '_overlay_mode', True) else 'tiles')
        return super()._create(itemType,args,kw)

    def redraw(self):
        # Coalesce mouse, timer, tile and simulation events into one paint.
        if not self.closed and self._redraw_timer is None:
            self._redraw_timer=self.after(16,self._redraw_now)

    def _redraw_now(self):
        self._redraw_timer=None
        if self.closed or self.winfo_width() < 10:
            return
        self.delete('overlay')
        # Native image uploads must also be budgeted: a cached viewport can
        # otherwise allocate dozens of Tk images in one blocking callback.
        self._upload_deadline=time.perf_counter()+.008
        self._needs_upload=False
        self._overlay_mode = False
        width, height = self.winfo_width(), self.winfo_height()
        cx, cy = world_pixel(*self.center, self.zoom)
        left, top = cx-width/2, cy-height/2
        self._left,self._top,self._drawing=left,top,True
        available = 0
        self.wanted = {(self.source.name, self.zoom, tx % 2**self.zoom, ty)
                       for tx in range(math.floor(left/256), math.floor((left+width)/256)+1)
                       for ty in range(math.floor(top/256), math.floor((top+height)/256)+1) if 0 <= ty < 2**self.zoom}
        for key in set(self._tile_items)-self.wanted:
            self.delete(self._tile_items.pop(key)[0])
        for tx in range(math.floor(left/256), math.floor((left+width)/256)+1):
            for ty in range(math.floor(top/256), math.floor((top+height)/256)+1):
                if not 0 <= ty < 2**self.zoom:
                    continue
                key = (self.source.name, self.zoom, tx % 2**self.zoom, ty)
                x, y = tx*256-left, ty*256-top
                if key in self.tiles:
                    photo=self.photo(key)
                    if photo is None:continue
                    available += 1
                    existing = self._tile_items.get(key)
                    if existing and existing[1] == 'image':
                        self.coords(existing[0],x,y)
                        self.itemconfigure(existing[0],image=self.photos[key])
                    else:
                        if existing:
                            self.delete(existing[0])
                        self._tile_items[key] = (self.create_image(x,y,image=self.photos[key],anchor='nw'),'image')
                else:
                    fallback=('offline:'+str(id(self.provider)),self.zoom,key[2],ty)
                    if self.provider and fallback not in self.tiles:self.request_tile(fallback)
                    photo_key=fallback if fallback in self.tiles else None
                    preview=self.parent_preview(key)
                    if photo_key or preview is not None:
                        photo=preview if preview is not None else self.photo(photo_key)
                        if photo is None:continue
                        existing=self._tile_items.get(key)
                        if existing and existing[1]=='image':
                            self.coords(existing[0],x,y)
                            self.itemconfigure(existing[0],image=photo)
                        else:
                            if existing:self.delete(existing[0])
                            self._tile_items[key]=(self.create_image(x,y,image=photo,anchor='nw'),'image')
                        continue
                    existing = self._tile_items.get(key)
                    if existing and existing[1]=='placeholder':
                        self.coords(existing[0],x,y,x+256,y+256)
                    else:
                        if existing:self.delete(existing[0])
                        self._tile_items[key] = (self.create_rectangle(x,y,x+256,y+256,outline='#d7dfe5'),'placeholder')
        for key in sorted(self.wanted,key=lambda k:(k[2]*256+128-cx)**2+(k[3]*256+128-cy)**2):
            if key not in self.tiles:self.request_tile(key)
        self._overlay_mode = True
        self.draw_grid_tiles()
        if self.provider and self.frame:
            self.draw_network()
            self.draw_live()
        for name, ll in self.pins.items():
            x,y = self.screen(*ll)
            color = '#2563eb' if name == 'origin' else '#db2777'
            self.create_polygon(x-7,y-17,x+7,y-17,x,y,fill=color,outline='white',width=2)
            self.create_oval(x-12,y-32,x+12,y-8,fill=color,outline='white',width=2)
            self.create_text(x,y-20,text='A' if name == 'origin' else 'B',fill='white',font=('Segoe UI',10,'bold'))
        if self.edit_points:
            coords = [v for ll in self.edit_points for v in self.screen(*ll)]
            if len(coords) >= 4:
                self.create_line(*coords, fill="#7c3aed", width=3, dash=(4, 3))
            for ll in self.edit_points:
                x, y = self.screen(*ll)
                self.create_oval(x-4, y-4, x+4, y+4, fill="#7c3aed")
        self.create_rectangle(0,height-19,width,height,fill='#1f1f1f',outline='')
        self.create_text(8,height-10,text=self.source.attribution,anchor='w',font=('Segoe UI',8),fill='#a0a0a0')
        metres_per_pixel = 156543.033928*math.cos(math.radians(self.center[1]))/2**self.zoom
        distance = min((10, 20, 50, 100, 200, 500, 1000, 2000, 5000), key=lambda value: abs(value/metres_per_pixel-100))
        bar = distance/metres_per_pixel
        self.create_line(12, height-40, 12+bar, height-40, fill="white", width=6)
        self.create_line(12, height-40, 12+bar, height-40, fill="#192d42", width=2)
        self.create_text(12, height-53, anchor="w", text=f"{distance:g} m", fill="#192d42", font=("Segoe UI", 9, "bold"))
        name=label_for(self.selected)
        text=f"z{self.zoom}  /  "+(('Following '+name[:24]+('…' if len(name)>24 else '')) if self.follow else 'Free map')
        from tkinter import font
        extent=min(width-20,font.Font(family='Segoe UI',size=8).measure(text)+18)
        self.create_rectangle(8,8,8+extent,30,fill='#1f1f1f',outline='#343434')
        self.create_text(16,19,anchor='w',text=text,font=('Segoe UI',8),fill='#cccccc',width=max(1,extent-12))
        if len(self.photos) > 220:
            self.photos = {key: photo for key, photo in self.photos.items() if key in self.tiles}
        tile_status=(self.source.name,available,len(self.wanted),sum(k in self.failed for k in self.wanted))
        if not self.edit_tool and tile_status!=getattr(self,'_last_tile_status',None):
            self._last_tile_status=tile_status
            self.status(f'{self.source.name} · {available}/{len(self.wanted)} background tiles · '+
                ('ready' if available==len(self.wanted) else 'background unavailable; local OSM roads remain usable' if tile_status[3] else 'loading in background; local OSM roads remain usable'))
        self._drawing=False
        if self._needs_upload:self.redraw()

    def photo(self,key):
        if key not in self.photos:
            if time.perf_counter()>self._upload_deadline:
                self._needs_upload=True
                return None
            self.photos[key]=ImageTk.PhotoImage(self.tiles[key])
        return self.photos[key]

    def draw_grid_tiles(self):
        keys={('grid:',*key[1:]) for key in self.wanted} if self.show_cells and self.frame and self.frame.get('playground') else set()
        for key in set(self._grid_items)-keys:self.delete(self._grid_items.pop(key))
        for key in keys:
            if key not in self.tiles:
                self.request_tile(key)
                continue
            photo=self.photo(key)
            if photo is None:continue
            x,y=key[2]*256-self._left,key[3]*256-self._top
            if key in self._grid_items:self.coords(self._grid_items[key],x,y)
            else:
                self._overlay_mode=False
                self._grid_items[key]=self.create_image(x,y,image=self.photos[key],anchor='nw')
                self._overlay_mode=True
            self.tag_raise(self._grid_items[key])

    def parent_preview(self,key):
        """Reuse an already fetched parent while sharper visible tiles arrive."""
        if key in self._previews:return self._previews[key]
        name,z,x,y=key
        for depth in range(1,min(4,z)+1):
            factor=2**depth
            parent=(name,z-depth,x//factor,y//factor)
            if parent not in self.tiles:continue
            if time.perf_counter()>self._upload_deadline:
                self._needs_upload=True
                return None
            size=256/factor;left=(x%factor)*size;top=(y%factor)*size
            image=self.tiles[parent].crop((left,top,left+size,top+size)).resize((256,256),Image.Resampling.BILINEAR)
            photo=ImageTk.PhotoImage(image)
            self._previews[key]=photo
            if len(self._previews)>100:
                self._previews={k:v for k,v in self._previews.items() if k in self.wanted}
            return photo
        return None

    def draw_offline_roads(self):
        from shapely.geometry import box
        cx, cy = world_pixel(*self.center, self.zoom)
        west, north = pixel_lonlat(cx-self.winfo_width()/2, cy-self.winfo_height()/2, self.zoom)
        east, south = pixel_lonlat(cx+self.winfo_width()/2, cy+self.winfo_height()/2, self.zoom)
        a, b = self.provider.lonlat_to_xy(west, south), self.provider.lonlat_to_xy(east, north)
        for position in self.provider.tree.query(box(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))):
            edge = self.provider.edges[self.provider.edge_ids[int(position)]]
            points = [v for ll in edge["shape_wgs84"] for v in self.screen(*ll)]
            self.create_line(*points, fill="#75879a", width=2)
        self.create_text(10, 12, anchor="nw", text="Offline OSM simulation network · waiting for background tiles", fill="#243b53")

    def draw_live(self):
        frame = self.frame
        names = list(frame["vehicles"])
        if self.selected in names:
            names.remove(self.selected)
            names.append(self.selected)
        for name in names:
            if name != self.selected and not self.all_routes:
                continue
            points = [self.screen(*ll) for eid in frame["vehicles"][name]["route"] if eid in self.provider.edges for ll in self.provider.edges[eid]["shape_wgs84"]]
            if len(points) > 1:
                flat = [v for xy in points for v in xy]
                self.create_line(*flat, fill="white", width=8)
                self.create_line(*flat, fill=color_for(name), width=4)
                x, y = points[-1]
                self.create_text(x, y-12, text=label_for(name)+" destination", fill=color_for(name), font=("Segoe UI", 10, "bold"))
        for fact in frame.get("facts", []):
            geometries = [fact["geometry"]["coordinates"]] if fact["geometry"]["type"] == "Polygon" else fact["geometry"]["coordinates"]
            for coords in geometries:
                flat = [v for ll in coords[0] for v in self.screen(*ll)]
                self.create_polygon(*flat, outline="#c92036", fill="#ed5b67", stipple="gray50", width=3)
        ordered = sorted(frame.get("vehicle_status", {}), key=lambda name: name == self.selected)
        for name in ordered:
            status = frame["vehicle_status"][name]
            state = frame["vehicles"].get(name)
            edge = self.scenario["vehicles"][name]["destination" if status == "arrived" else "origin"]
            ll = state["lonlat"] if state else self.provider.edges[edge]["shape_wgs84"][-1 if status == "arrived" else 0]
            x, y = self.screen(*ll)
            r = 11 if name == self.selected else 9
            self.create_oval(x-r-3, y-r-3, x+r+3, y+r+3, fill="white", outline="white")
            marker = self.create_oval(x-r, y-r, x+r, y+r, fill=color_for(name) if state else "white" if status == "arrived" else "#94a3b8", outline=color_for(name), width=3)
            self.tag_bind(marker, "<Button-1>", lambda event, n=name: self.select_vehicle(n))
            if state:
                angle = math.radians(state.get("angle", 0))
                forward = (math.sin(angle), -math.cos(angle))
                right = (math.cos(angle), math.sin(angle))
                arrow = [(x+forward[0]*8, y+forward[1]*8),
                         (x-forward[0]*5+right[0]*5, y-forward[1]*5+right[1]*5),
                         (x-forward[0]*5-right[0]*5, y-forward[1]*5-right[1]*5)]
                self.create_polygon(*[v for point in arrow for v in point], fill="white", outline="")
            text = f"{label_for(name)} · {state['speed']*3.6:.0f} km/h" if state else label_for(name)+" · "+status
            offset = {"cautious": -38, "standard": -18, "unaffected": 18}.get(name, -24)
            self.create_text(x+17, y+offset+1, anchor="w", text=text, font=("Segoe UI", 11, "bold"), fill="white", width=220)
            self.create_text(x+16, y+offset, anchor="w", text=text, font=("Segoe UI", 11, "bold"), fill=color_for(name), width=220)

    def select_vehicle(self, name):
        if self.on_vehicle_select:
            self.on_vehicle_select(name)
        else:
            self.track(name)

    def cell_boundary(self, cell):
        import h3
        if cell not in self._boundary_cache:
            self._boundary_cache[cell] = tuple((lon,lat) for lat,lon in h3.cell_to_boundary(cell))
            if len(self._boundary_cache) > 6000:
                self._boundary_cache.pop(next(iter(self._boundary_cache)))
        return self._boundary_cache[cell]

    def draw_network(self):
        if not self.frame.get("playground"):
            return
        from shapely.geometry import Point
        scene, network = self.frame["scene"], self.frame["network"]
        if self.show_towers:
            for tower in scene["towers"]:
                xy = self.provider.lonlat_to_xy(tower["longitude"], tower["latitude"])
                ring = Point(*xy).buffer(tower["radius_m"], quad_segs=24).exterior.coords
                flat = [v for p in ring for v in self.screen(*self.provider.xy_to_lonlat(*p))]
                self.create_polygon(*flat, fill="", outline="#7c3aed", dash=(6, 4), width=2)
                x, y = self.screen(tower["longitude"], tower["latitude"])
                self.create_line(x-7, y+10, x, y-12, x+7, y+10, fill="#6d28d9", width=3)
                self.create_text(x+12, y-13, text=tower["id"]+" · simulated 5G", anchor="w", fill="#6d28d9", font=("Segoe UI", 10, "bold"))
            for name, association in network.get("associations", {}).items():
                vehicle = self.frame["vehicles"].get(name)
                tower = next((t for t in scene["towers"] if t["id"] == association["tower_id"]), None)
                if vehicle and tower:
                    self.create_line(*self.screen(*vehicle["lonlat"]), *self.screen(tower["longitude"], tower["latitude"]), fill="#a78bfa", dash=(2, 5))
        if self.show_cells:
            # Display grid is computed locally; affected red cells are authoritative
            # values returned by MEC. At broad zoom use the macro r8 grid.
            res = 10 if self.zoom >= 15 else 8
            for record in network.get("incidents", []):
                if record["status"] != "active":
                    continue
                for cell in record["h3_cells"][str(res)]:
                    flat = [v for lon, lat in self.cell_boundary(cell) for v in self.screen(lon, lat)]
                    self.create_polygon(*flat, fill="#fca5a5", stipple="gray25", outline="#dc2626", width=2)
        for anomaly in scene["anomalies"]:
            flat = [v for ll in anomaly["geometry"]["coordinates"][0] for v in self.screen(*ll)]
            published = self.frame.get("published", {}).get(anomaly["id"], 0) >= anomaly.get("event_version", 1)
            shade = "#94a3b8" if anomaly.get("disabled") else "#dc2626" if published else "#d97706"
            self.create_polygon(*flat, fill="", outline=shade, width=3, dash=() if published else (5, 4))
            area = self.provider.geometry_to_xy(anomaly["geometry"]).centroid
            x, y = self.screen(*self.provider.xy_to_lonlat(area.x, area.y))
            self.create_text(x, y-18, text=anomaly["id"]+" · "+("cleared" if anomaly.get("disabled") else "MEC known" if published else "undetected ground truth"), fill=shade, font=("Segoe UI", 9, "bold"))

    def close(self):
        self.closed = True
        if self._redraw_timer is not None:self.after_cancel(self._redraw_timer)
        self.after_cancel(self._drain_timer)
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.local_pool.shutdown(wait=False, cancel_futures=True)
