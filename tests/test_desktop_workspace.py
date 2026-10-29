"""Exercise the docked workspace through real Tk callbacks and real SUMO."""
import time
import _tkinter
import tkinter as tk
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from types import SimpleNamespace

from laptop.map_launcher import MapLauncher


def wait_for(root, app, predicate, timeout=40):
    deadline = time.monotonic()+timeout
    while time.monotonic()<deadline:
        # Like mainloop, dispatch bounded events. update() tries to drain an
        # always-active Windows render/timer queue completely and can starve
        # the assertion even while the actual UI remains responsive.
        for _ in range(20):
            if not root.tk.dooneevent(_tkinter.ALL_EVENTS | _tkinter.DONT_WAIT):
                break
        assert not app.ui_errors, app.ui_errors
        if predicate():
            return
        if app.frame and app.frame.get('last_error'):
            raise AssertionError(app.frame['last_error'])
        time.sleep(.02)
    raise AssertionError('Timed out: '+app.status.get()+' / '+app.editor.note.get())


def test_docked_editor_pins_custom_vehicle_play_pause_and_scene_switch(tmp_path):
    # Windows Tcl interpreter teardown is process-global. Keep this rendered
    # event-loop test isolated from the separate form-only Tk test.
    result = subprocess.run([sys.executable,str(Path(__file__).resolve()),str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=180)
    assert result.returncode==0, result.stdout+'\n'+result.stderr


def exercise_workspace(tmp_path):
    from PIL import Image
    from laptop.map_canvas import TileStore
    TileStore.load=lambda *a:Image.new('RGB',(256,256),'#eef2f5')
    root = tk.Tk(); root.withdraw()
    args = SimpleNamespace(gui=False,defer_start=True,map_package=None,scenario=None,mec_mode='local',
        mec_url=None,semantics_url=None,playground_url=None,output=str(tmp_path),remote=False,playground=False)
    app = MapLauncher(root,args)
    try:
        root.geometry('1280x800');root.deiconify()
        wait_for(root,app,lambda: app._layout_ready and app.canvas.winfo_height()>250)
        assert app.editor.embedded
        assert len(app.editor.tabs.tabs())==4
        assert len(app.diagnostics.tabs())==4
        assert not any(isinstance(w,tk.Toplevel) for w in root.winfo_children())
        app.editor.open_scene(True)
        wait_for(root,app,lambda: app.frame and app.frame.get('playground'))
        assert not app.frame['playing'] and app.frame['healthy']
        app.send('play')
        wait_for(root,app,lambda:sum(app.frame['reroute_counts'].values())>0)
        assert not app.frame['playing']  # inspection pause occurs at a real change
        labels=[app.minimap.itemcget(i,'text') for i in app.minimap.find_all() if app.minimap.type(i)=='text']
        counters=[label for label in labels if label.startswith('Reroutes')]
        assert len(counters)==1 and 'Blue: 1' in counters[0],labels
        app.select_fleet_vehicle('cautious')
        assert app.canvas.selected=='cautious'
        assert set(app.canvas.pins)=={'origin','destination'}
        origin=app.editor.origin_edge.get(); destination=app.editor.destination_edge.get()
        app.new_vehicle()
        assert app.editor.vehicle.get()=='vehicle-1'
        point=app.provider.edges[origin]['shape_wgs84'][0]
        app.editor.road_picked('origin',point)
        app.editor.destination_edge.widget['values']=[destination]
        app.editor.destination_edge.set(destination)
        app.editor.sync_pins()
        # Actual hit-test, drag motion and drop callbacks preserve road snapping.
        x,y=app.canvas.screen(*app.canvas.pins['origin'])
        app.canvas.begin_drag(SimpleNamespace(x=x,y=y-20))
        assert app.canvas.drag_pin=='origin'
        app.canvas.drag(SimpleNamespace(x=x+2,y=y-20))
        app.canvas.end_drag(SimpleNamespace(x=x+2,y=y-20))
        assert app.editor.origin_edge.get() in app.provider.edges
        # A stable viewport reuses canvas tile IDs, not merely bitmap bytes.
        app.canvas.redraw()
        tiles=dict(app.canvas._tile_items)
        app.canvas.redraw()
        assert app.canvas._tile_items==tiles
        app.editor.role.set('receiver'); app.editor.put_vehicle()
        wait_for(root,app,lambda:'vehicle-1' in app.frame.get('vehicle_status',{}))
        assert app.frame['scene']['vehicles']['vehicle-1']['role']=='receiver'
        size=app.worker.commands.qsize()
        app.keyboard_play(SimpleNamespace(widget=app.editor.vehicle.widget))
        assert app.worker.commands.qsize()==size
        app.render_fleet(True)
        assert app.fleet_expanded
        app.select_fleet_vehicle('vehicle-1')
        app.send('step')
        previous=app.frame['time']
        wait_for(root,app,lambda:app.frame['time']>previous)
        assert app.frame['healthy'] and not app.frame['playing']
        app.pause_on_change.set(False)
        app.worker.commands.put(('review_mode',False))
        app.toggle_play()
        wait_for(root,app,lambda:app.frame['playing'])
        app.toggle_play()
        wait_for(root,app,lambda:not app.frame['playing'])
        old=app.epoch
        app.map.set('Gujarat Coast'); app.select_map(); app.editor.open_scene(True)
        wait_for(root,app,lambda: app.epoch!=old and app.frame['map_id']=='gujarat_coastal')
        assert app.frame['healthy'] and not app.frame['playing']
        assert app.canvas.pins=={}
        assert 'last_error' in app.frame and app.frame['last_error'] is None
    finally:
        app.worker.commands.put(('stop',None))
        app.worker.join(timeout=20)
        app.canvas.close()
        root.destroy()
        assert not app.worker.is_alive()


if __name__ == '__main__':
    exercise_workspace(Path(sys.argv[1]))
    print('DOCKED_WORKSPACE_VERIFIED')
