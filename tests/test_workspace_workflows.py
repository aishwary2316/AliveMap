"""Exercise the visible workflow handlers and real Tk map events with SUMO/MEC."""
import subprocess,sys
from pathlib import Path


def test_comparison_drawing_publication_vehicle_and_replay(tmp_path):
    from test_geo_maps import package
    package()
    result=subprocess.run([sys.executable,str(Path(__file__).resolve()),str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=160)
    assert result.returncode==0,result.stdout+'\n'+result.stderr


def exercise(output):
    import tkinter as tk,time,_tkinter
    from types import SimpleNamespace
    from PIL import Image
    from laptop.map_canvas import TileStore
    from laptop.map_launcher import MapLauncher
    TileStore.load=lambda *args:Image.new('RGB',(256,256),'#e8edf1')
    root=tk.Tk();root.withdraw()
    args=SimpleNamespace(gui=False,defer_start=True,map_package=None,scenario=None,mec_mode='local',
        mec_url=None,semantics_url=None,playground_url=None,output=str(output),remote=False,playground=False)
    app=MapLauncher(root,args)
    root.geometry('1280x800');root.deiconify()
    def pump(seconds=.08):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            for _ in range(2):
                if not root.tk.dooneevent(_tkinter.ALL_EVENTS|_tkinter.DONT_WAIT):break
                if time.monotonic()>=until:break
            time.sleep(.003)
        assert not app.ui_errors,app.ui_errors
    def wait(predicate):
        deadline=time.monotonic()+35
        while time.monotonic()<deadline:
            pump()
            if predicate():return
            if app.frame and app.frame.get('last_error'):raise AssertionError(app.frame['last_error'])
        raise AssertionError(app.status.get()+' / '+app.editor.note.get())
    def button(text):
        deadline=time.monotonic()+4
        while True:
            candidates=[b for b in app.editor.action_buttons if b.winfo_ismapped() and b.cget('text').strip()==text]
            if candidates or time.monotonic()>deadline:break
            pump(.03)
        assert len(candidates)==1,(text,len(candidates),app.editor.tabs.select(),[(b.cget('text'),b.winfo_ismapped()) for b in app.editor.action_buttons])
        return candidates[0]
    def click(x,y):
        app.canvas.event_generate('<ButtonPress-1>',x=int(x),y=int(y))
        app.canvas.event_generate('<ButtonRelease-1>',x=int(x),y=int(y));pump()
    try:
        pump(.3)
        app.load('none')
        wait(lambda:app.frame and app.frame.get('playground') and app.frame['playing'])
        assert app.condition.get()=='Without incident' and not app.frame['scene']['anomalies']
        app.send('pause');wait(lambda:not app.frame['playing'])
        print('baseline ready',flush=True)
        previous=app.epoch
        app.condition.set('With incident');app.load()
        wait(lambda:app.epoch!=previous and app.frame and len(app.frame['network'].get('incidents',[]))==1 and len(app.frame['network']['incidents'][0].get('reporters',[]))==2)
        app.send('pause');wait(lambda:not app.frame['playing'])
        print('two-report story ready',flush=True)
        assert app.frame['healthy'] and app.frame['reroute_counts']['cautious']>=1
        pump(.2);assert app.canvas.find_withtag('old-route'),'main-map old route not visible'
        assert any(app.canvas.itemcget(item,'dash') for item in app.canvas.find_withtag('old-route'))
        editor=app.editor
        editor.tabs.select(editor.anomaly_page);pump()
        editor.incident.set('custom-area')
        button('Rect').invoke();pump()
        assert app.canvas.edit_tool=='rectangle'
        ll=app.frame['vehicles']['cautious']['lonlat'];x,y=app.canvas.screen(*ll)
        click(x-14,y-14);assert len(app.canvas.edit_points)==1
        click(x+14,y+14)
        assert editor.geometry and app.canvas.draft_geometry
        pump(.1);assert app.canvas.find_withtag('draft')
        button('Save area').invoke()
        wait(lambda:any(a['id']=='custom-area' for a in app.frame['scene']['anomalies']))
        print('rectangle saved',flush=True)
        assert not app.canvas.draft_geometry
        button('Publish').invoke()
        wait(lambda:any(a['id']=='custom-area' for a in app.frame['network']['incidents']))
        print('published',flush=True)
        assert not app.frame.get('narration'),'custom edit must not claim a scripted scout story'
        button('Clear').invoke()
        wait(lambda:next(r for r in app.frame['network']['incidents'] if r['id']=='custom-area')['status']=='cleared')
        editor.edit('remove_anomaly',{'id':'custom-area'})
        wait(lambda:not any(a['id']=='custom-area' for a in app.frame['scene']['anomalies']))
        button('Polygon').invoke();click(x-12,y-12);button('Finish').invoke();pump()
        assert app.canvas.edit_tool=='polygon' and len(app.canvas.edit_points)==1
        click(x+12,y-12);click(x,y+12);button('Finish').invoke();pump()
        assert app.canvas.draft_geometry
        button('Cancel').invoke();pump()
        assert editor.geometry is None and app.canvas.draft_geometry is None
        button('Circle').invoke();click(x,y);assert app.canvas.draft_geometry
        button('Cancel').invoke();pump()
        app.new_vehicle();pump()
        route=app.frame['vehicles']['cautious']['route']
        origin=route[min(2,len(route)-1)];destination=route[min(6,len(route)-1)]
        button('Origin').invoke();pump();assert app.canvas.edit_tool=='point'
        point=app.provider.edges[origin]['shape_wgs84'][0]
        px,py=app.canvas.screen(*point);click(px,py)
        assert editor.origin_edge.get() in app.provider.edges
        editor.origin_edge.widget['values']=[origin];editor.origin_edge.set(origin);editor.position.set('0')
        button('Destination').invoke();pump();assert app.canvas.edit_tool=='point'
        point=app.provider.edges[destination]['shape_wgs84'][0]
        px,py=app.canvas.screen(*point);click(px,py)
        assert editor.destination_edge.get() in app.provider.edges
        editor.destination_edge.widget['values']=[destination];editor.destination_edge.set(destination)
        editor.sync_pins();editor.role.set('receiver');button('Save').invoke()
        wait(lambda:'vehicle-1' in app.frame['scene']['vehicles'])
        assert app.frame['scene']['vehicles']['vehicle-1']['role']=='receiver'
        assert set(app.canvas.pins)=={'origin','destination'}
        assert 'Applied' in app.console.text.get('1.0','end')
        print('WORKSPACE_WORKFLOWS_VERIFIED',flush=True)
    finally:
        app.worker.commands.put(('stop',None));app.worker.join(timeout=15)
        app.canvas.close();root.destroy()
        assert not app.worker.is_alive()


if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    exercise(Path(sys.argv[1]))
