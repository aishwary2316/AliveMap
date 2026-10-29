"""Exercise real Tk geometry at both monitor ratios and larger text scales."""
import json
import subprocess
import sys
from pathlib import Path

import pytest


CASES=[(1920,1080,1),(1920,1200,1),(1280,720,1),(1280,800,1),
       (1536,864,1),(1440,900,1),(1024,640,1),(1280,800,1.25),
       (1280,800,1.5),(1024,640,1.5)]


@pytest.mark.parametrize('width,height,text_scale',CASES)
def test_monitor_layouts_and_resize(width,height,text_scale,tmp_path):
    result=subprocess.run([sys.executable,str(Path(__file__).resolve()),str(width),str(height),
        str(text_scale),str(tmp_path)],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=40)
    assert result.returncode==0,result.stdout+'\n'+result.stderr


def verify(width,height,text_scale,output):
    import time
    import _tkinter
    import tkinter as tk
    from types import SimpleNamespace
    from PIL import Image
    from laptop.map_canvas import TileStore
    from laptop.map_launcher import MapLauncher
    TileStore.load=lambda *a:Image.new('RGB',(256,256),'#222222')
    root=tk.Tk();root.withdraw()
    root.tk.call('tk','scaling',4/3*text_scale)
    root.maxsize(5000,4000)
    args=SimpleNamespace(gui=False,defer_start=True,map_package=None,scenario=None,mec_mode='local',
        mec_url=None,semantics_url=None,playground_url=None,output=str(output),remote=False,playground=False)
    app=MapLauncher(root,args)

    def pump(seconds=.45):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            for _ in range(12):
                if not root.tk.dooneevent(_tkinter.ALL_EVENTS|_tkinter.DONT_WAIT):break
            time.sleep(.005)
        # Flush deferred geometry after the bounded timer/render pump. Otherwise
        # a child may still report its previous size during a native resize.
        root.update_idletasks()
        assert not app.ui_errors,app.ui_errors

    def check_controls(widget):
        for child in widget.winfo_children():
            if child.winfo_ismapped():
                if child.winfo_class() in ('TButton','Button','TEntry','TCombobox','TCheckbutton'):
                    assert child.winfo_x()>=-1,(str(child),child.winfo_x())
                    assert child.winfo_x()+child.winfo_width()<=widget.winfo_width()+1,(
                        child.winfo_class(),str(child),child.winfo_x(),child.winfo_width(),widget.winfo_width(),
                        child.winfo_reqwidth(),child.grid_info(),widget.grid_info(),root.geometry(),app.console.compact_bar)
                    assert child.winfo_height()>=child.winfo_reqheight()-1,('height',str(child))
                check_controls(child)

    report=[]
    try:
        root.geometry(f'{width}x{height}');root.deiconify();pump(.8)
        assert (root.winfo_width(),root.winfo_height())==(width,height)
        assert app._layout_ready
        for current in [(width,height),(1280,800),(1280,720),(width,height)]:
            root.geometry(f'{current[0]}x{current[1]}');pump()
            assert app.canvas.winfo_width()>=400
            assert app.canvas.winfo_height()>=275
            assert abs(app.layout.config.winfo_width()-app.inspector.winfo_width())<=1
            # Every inspector tab and console configuration remains usable.
            for page in app.editor.tabs.tabs():
                app.editor.tabs.select(page);pump(.025)
                check_controls(app.editor.window)
            app.diagnostics.select(app.settings_page);pump(.025)
            check_controls(app.settings_page)
            app.diagnostics.select(0);pump(.025)
            app.console.count.set('1234 / 1500 events');pump(.1)
            check_controls(app.console.bar)
            app.layout.fit_overview()
            assert app.minimap.winfo_y()>=0
            assert app.minimap.winfo_x()+app.minimap.winfo_width()<=app.canvas.winfo_width()
            report.append({'window':current,'map':[app.canvas.winfo_width(),app.canvas.winfo_height()],
                'inspector':app.inspector.winfo_width(),'console_toolbar_wrapped':app.console.compact_bar})
        # Splitter choices survive a shrink/expand cycle within usable limits.
        app.layout.upper.sashpos(0,max(300,app.layout.minimum_inspector()))
        app.layout.remember_inspector()
        saved=app.layout.upper.sashpos(0)
        root.geometry('1440x900');pump()
        assert abs(app.layout.upper.sashpos(0)-saved)<=1
        print(json.dumps({'viewport':[width,height],'text_scale':text_scale,'layouts':report}))
    finally:
        app.worker.commands.put(('stop',None));app.worker.join(timeout=5)
        app.canvas.close();root.destroy()
        assert not app.worker.is_alive()


if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    verify(int(sys.argv[1]),int(sys.argv[2]),float(sys.argv[3]),Path(sys.argv[4]))
