"""Exercise the real Tk form callbacks without a second interactive simulation."""
import json
import queue
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import Mock, patch

from laptop.map_launcher import MapLauncher
from laptop.playground_editor import PlaygroundEditor
from routing_core.maps import PackageMapProvider, read_json
from routing_core.playground import example_scene
from test_geo_maps import package


def test_forms_map_clicks_shapes_save_load_and_epoch_reset(tmp_path):
    provider=PackageMapProvider(package())
    scene=example_scene(provider,read_json(provider.path/provider.manifest['scenario']))
    root=tk.Tk(); root.withdraw()
    app=SimpleNamespace(root=root, canvas=Mock(), send=Mock(), track=Mock(), frame={'playground':True},
                        provider=provider, worker=SimpleNamespace(commands=queue.Queue()),
                        packages={scene['map_id']:provider.path}, mode=tk.StringVar(root,value='Local demo (no SSH)'),
                        sumo_gui=tk.BooleanVar(root,value=False),pause_on_change=tk.BooleanVar(root,value=True))
    app.button_row=lambda parent,buttons: MapLauncher.button_row(app,parent,buttons)
    editor=PlaygroundEditor(app); editor.window.withdraw()
    try:
        frame={'scene':scene,'run_id':'epoch-one','network':{},'knowledge':{}}
        editor.update(frame)
        assert editor.kind.get()==scene['anomalies'][0]['kind']
        assert editor.geometry==scene['anomalies'][0]['geometry']
        assert editor.tower_point is not None
        # Choosing a fleet entry loads real OD/profile and calls track.
        editor.vehicle_box.set('cautious'); editor.select_vehicle()
        app.track.assert_called_with('cautious')
        editor.vehicle.set('custom'); editor.role.set('receiver'); editor.put_vehicle()
        command=app.send.call_args.args
        assert command[0]=='edit' and command[1][0]=='vehicle'
        assert command[1][1]['id']=='custom' and command[1][1]['role']=='receiver'
        # Map-click callbacks actually project to a directed OSM edge.
        point=provider.edges[scene['vehicles']['cautious']['origin']]['shape_wgs84'][0]
        editor.pick_road('origin')
        app.canvas.start_edit.call_args.args[1]([point])
        assert editor.origin_edge.get() in provider.edges and float(editor.position.get())>=0
        editor.draw('circle')
        app.canvas.start_edit.call_args.args[1]([point])
        editor.incident.set('custom-area'); editor.kind.set('flood'); editor.put_anomaly()
        command=app.send.call_args.args[1]
        assert command[0]=='anomaly' and command[1]['geometry']['type']=='Polygon' and command[1]['kind']=='flood'
        editor.pick_tower(); app.canvas.start_edit.call_args.args[1]([point]); editor.put_tower()
        assert app.send.call_args.args[1][0]=='tower'
        # Same-epoch frames must not overwrite an edit the user is composing.
        editor.kind.set('landslide'); editor.update(frame)
        assert editor.kind.get()=='landslide'
        path=tmp_path/'scene.json'
        with patch('laptop.playground_editor.filedialog.asksaveasfilename',return_value=str(path)):
            editor.save()
        assert json.loads(path.read_text())['map_build_id']==scene['map_build_id']
        with patch('laptop.playground_editor.filedialog.askopenfilename',return_value=str(path)):
            editor.load()
        load=app.worker.commands.get_nowait()
        assert load[0]=='load' and load[1][2]['playground_scene']['vehicles']==scene['vehicles']
        editor.update({**frame,'run_id':'epoch-two'})
        assert not editor.origin_edge.get() and editor.kind.get()==scene['anomalies'][0]['kind']
    finally:
        root.destroy()
