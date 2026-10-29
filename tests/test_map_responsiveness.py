"""Responsiveness while imagery is stalled, using the real local OSM graph."""
import subprocess
import sys
from pathlib import Path


def test_display_grid_is_rasterized_and_broad_views_are_bounded(monkeypatch):
    import h3
    from laptop.offline_tiles import grid_tile
    from laptop.map_canvas import world_pixel
    x,y=world_pixel(77.28,28.63,17)
    image=grid_tile(17,int(x//256),int(y//256))
    assert image.mode=='RGBA' and image.size==(256,256)
    assert image.getbbox() is not None
    def oversized(*args):raise AssertionError('broad view attempted an H3 cover')
    monkeypatch.setattr(h3,'geo_to_cells',oversized)
    assert grid_tile(6,45,25).getbbox() is None


def test_stalled_tiles_do_not_queue_old_views_or_block_input(tmp_path):
    from test_geo_maps import package
    package()  # Skip on checkouts without the separately built map assets.
    result=subprocess.run([sys.executable,str(Path(__file__).resolve()),str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=45)
    assert result.returncode==0,result.stdout+'\n'+result.stderr


def verify(output):
    import _tkinter
    import threading
    import time
    import tkinter as tk
    from PIL import Image
    from laptop.map_canvas import MapCanvas,pixel_lonlat,world_pixel
    from routing_core.maps import PackageMapProvider,read_json
    from test_geo_maps import package
    provider=PackageMapProvider(package())
    root=tk.Tk();root.geometry('1200x750')
    canvas=MapCanvas(root);canvas.pack(fill='both',expand=True)
    errors=[];root.report_callback_exception=lambda *args:errors.append(str(args[1]))
    release=threading.Event();calls=[]
    def blocked(source,z,x,y):
        calls.append((source.name,z,x,y))
        assert release.wait(15),'test did not release blocked downloader'
        return Image.new('RGB',(256,256),'#ccddee')
    canvas.store.load=blocked
    heartbeat=[]
    def beat():
        heartbeat.append(time.perf_counter())
        if not canvas.closed:root.after(20,beat)
    def pump(seconds):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            for _ in range(24):
                if not root.tk.dooneevent(_tkinter.ALL_EVENTS|_tkinter.DONT_WAIT):break
            time.sleep(.002)
        root.update_idletasks()
        assert not errors,errors
    try:
        root.after(20,beat);pump(.3)
        canvas.set_map(provider,read_json(provider.path/provider.manifest['scenario']))
        canvas.frame={'playground':True,'scene':{'towers':[],'anomalies':[]},
            'network':{'associations':{},'incidents':[]},'vehicles':{},'vehicle_status':{}}
        pump(1.2)
        assert len(calls)==4  # active sockets only, no queued viewport download batch
        assert len(canvas.pending)<=6
        assert any(key[0].startswith('offline:') for key in canvas.tiles)
        paint=canvas._redraw_now;paints=[]
        def counted():paints.append(time.perf_counter());paint()
        canvas._redraw_now=counted
        for _ in range(100):canvas.change_zoom(1);canvas.change_zoom(-1)
        pump(.1)
        assert len(paints)<=5,('input burst was not coalesced',len(paints))
        cx,cy=world_pixel(*canvas.center,canvas.zoom)
        canvas.center=pixel_lonlat(cx+10000,cy+10000,canvas.zoom);canvas.redraw();pump(.15)
        current=set(canvas.wanted)
        assert len(calls)==4
        release.set();pump(.7)
        assert set(calls[4:]).issubset(current),'obsolete views were downloaded after a pan'
        deadline=time.monotonic()+4
        while time.monotonic()<deadline and (not current.issubset(canvas.photos) or canvas._needs_upload):pump(.1)
        assert current.issubset(canvas.photos),'native image uploads never converged'
        assert not canvas._needs_upload,'a repaint loop is starving form geometry'
        gaps=[b-a for a,b in zip(heartbeat,heartbeat[1:])]
        assert max(gaps,default=0)<.8,('UI heartbeat stalled',max(gaps))
        print('MAP_RESPONSIVE',{'max_heartbeat_gap_ms':round(max(gaps)*1000,2),
            'burst_paints':len(paints),'max_downloads_in_flight':4},flush=True)
    finally:
        release.set();canvas.close();root.destroy()


if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    verify(Path(sys.argv[1]))
