"""Run locally with --baseline-source and an existing playground snapshot.

Save the old module with PowerShell:
  git show 6a3569c:laptop/map_canvas.py | Set-Content -Encoding utf8 .local/map_canvas_before.py
Then run python -m scripts.benchmark_map_ui --baseline-source .local/map_canvas_before.py
Results isolate native rendering with cached local roads; they do not measure
Internet speed, physical MEC health, initial map preparation or GPU utilization.
"""
import sys,json,time,statistics,tkinter as tk,importlib.util
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from routing_core.maps import PackageMapProvider,read_json
from laptop.map_canvas import MapCanvas,world_pixel
from laptop.offline_tiles import road_tile,grid_tile
rootdir=Path(__file__).resolve().parents[1]
import argparse
parser=argparse.ArgumentParser(description='Compare native map painting against a saved baseline module. No network requests are made.')
parser.add_argument('--baseline-source',type=Path,required=True)
parser.add_argument('--snapshot',type=Path,help='An existing ignored runs/**/current.json from a playground run')
parser.add_argument('--output',type=Path,default=rootdir/'runs/map-ui-benchmark.json')
args=parser.parse_args()
spec=importlib.util.spec_from_file_location('laptop.map_canvas_before',args.baseline_source)
old=importlib.util.module_from_spec(spec);sys.modules[spec.name]=old;spec.loader.exec_module(old)
for path in ([args.snapshot] if args.snapshot else sorted((rootdir/'runs').rglob('current.json'),key=lambda p:p.stat().st_mtime,reverse=True)):
    frame=read_json(path)
    if frame.get('playground') and frame.get('vehicles'):break
folder=rootdir/'map_packages'/frame['map_id']
provider=PackageMapProvider(folder/read_json(folder/'active.json')['revision'])
report={}
for label,cls in [('before',old.MapCanvas),('after',MapCanvas)]:
    root=tk.Tk();root.geometry('1600x900')
    canvas=cls(root);canvas.pack(fill='both',expand=True);canvas.request_tile=lambda key:None
    for _ in range(100):root.update_idletasks();root.tk.dooneevent(2);time.sleep(.005)
    canvas.provider=provider;canvas.scenario={'vehicles':frame['scene']['vehicles']};canvas.frame=frame
    canvas.center=tuple(next(iter(frame['vehicles'].values()))['lonlat'])
    if label=='after':
        # Local vector tiles are reused during subsequent movement. Network is
        # disabled in both runs to isolate UI work under an imagery outage.
        for z in range(16,20):
            cx,cy=world_pixel(*canvas.center,z)
            for x in range(int((cx-800)//256),int((cx+800)//256)+1):
                for y in range(int((cy-450)//256),int((cy+450)//256)+1):
                    canvas.tiles[('offline:'+str(id(provider)),z,x,y)]=road_tile(provider,z,x,y)
                    canvas.tiles[('grid:',z,x,y)]=grid_tile(z,x,y)
    paint=getattr(canvas,'_redraw_now',canvas.redraw)
    measurements=[]
    for i in range(16):
        canvas.zoom=16+i%4
        start=time.perf_counter();paint();root.update_idletasks();measurements.append(round((time.perf_counter()-start)*1000,2))
    report[label]={'redraw_ms':measurements,'median_ms':round(statistics.median(measurements),2),'max_ms':max(measurements),'canvas_items':len(canvas.find_all())}
    canvas.zoom=17
    for _ in range(100):
        paint();root.update_idletasks()
        if not getattr(canvas,'_needs_upload',False):break
    cx,cy=world_pixel(*canvas.center,17);pan=[]
    from laptop.map_canvas import pixel_lonlat
    for i in range(20):
        canvas.center=pixel_lonlat(cx+i*2,cy+i*2,17)
        start=time.perf_counter();paint();root.update_idletasks();pan.append(round((time.perf_counter()-start)*1000,2))
    report[label]['pan_ms']=pan
    report[label]['pan_median_ms']=round(statistics.median(pan),2)
    canvas.close()
    for timer in root.tk.call('after','info'):canvas.after_cancel(timer)
    root.destroy()
report['speedup_pan']=round(report['before']['pan_median_ms']/report['after']['pan_median_ms'],2)
report['conditions']={'viewport':[1600,900],'map':frame['map_id'],'zooms':[16,17,18,19],'network':'disabled to isolate rendering','after_cache':'warm raster data; native photo uploads budgeted per paint; pan measured after upload completion','radio':'simulated'}
print(json.dumps(report),flush=True)
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
