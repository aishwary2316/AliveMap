"""Native dark-shell checks, isolated from other Windows Tcl interpreters."""
import subprocess
import sys
from pathlib import Path


def test_dark_icons_compact_layout_and_semantic_console(tmp_path):
    result=subprocess.run([sys.executable,str(Path(__file__).resolve()),str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=45)
    assert result.returncode==0,result.stdout+'\n'+result.stderr


def verify(output):
    import time
    import _tkinter
    import tkinter as tk
    from types import SimpleNamespace
    from PIL import Image
    from laptop.map_launcher import MapLauncher
    from laptop.map_canvas import TileStore
    from laptop.ui_icons import icon_image
    from laptop import ui_theme as theme
    TileStore.load=lambda *a:Image.new('RGB',(256,256),'#222222')
    root=tk.Tk();root.withdraw()
    args=SimpleNamespace(gui=False,defer_start=True,map_package=None,scenario=None,mec_mode='local',
        mec_url=None,semantics_url=None,playground_url=None,output=str(output),remote=False,playground=False)
    app=MapLauncher(root,args)
    try:
        root.geometry('980x650');root.deiconify()
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            for _ in range(15):root.tk.dooneevent(_tkinter.ALL_EVENTS|_tkinter.DONT_WAIT)
            if app._layout_ready and app.editor.vehicle.widget.winfo_width()>10:break
            time.sleep(.01)
        assert app._layout_ready
        assert not app.ui_errors,app.ui_errors
        assert app.history.cget('background')==theme.EDITOR
        assert app.play_button.cget('text')=='' and app.play_button.cget('image')
        assert app.play_button.winfo_width()<40  # no default nine-character button minimum
        for name in ('play','pause','step','fast','restart','settings','plus','minus','map','folder',
                     'save','new','example','pin','send','clear','circle','rectangle','polygon','trash','car','search'):
            picture=icon_image(root,name)
            assert (picture.width(),picture.height())==(16,16)
        # Forms remain aligned, with all label text fitting their allocated column.
        from tkinter import font
        for variable in (app.editor.vehicle,app.editor.role,app.editor.profile,app.editor.origin_edge,
                         app.editor.destination_edge,app.editor.position):
            row=variable.widget.master
            label=row.winfo_children()[0]
            face=font.Font(font=label.cget('font') or 'TkDefaultFont')
            assert face.measure(label.cget('text'))<=label.winfo_width(),label.cget('text')
            assert variable.widget.winfo_x()+variable.widget.winfo_width()<=row.winfo_width()+1
        for page in app.editor.tabs.tabs():
            app.editor.tabs.select(page)
            root.update_idletasks()
            for button in app.editor.action_buttons:
                if button.winfo_ismapped():
                    assert button.winfo_width()>=button.winfo_reqwidth()-1,button.cget('text')
                    assert button.winfo_x()+button.winfo_width()<=button.master.winfo_width()+1
        console=app.console
        console.clear()
        console.append('radio','probe → MEC ACK: anomaly-1; H3 r8=1, r10=1',7.5)
        console.append('decision','cautious: Route changed; 1 known incident',7.5)
        console.append('error','Connection test failure',8)
        assert console.text.tag_ranges('success') and console.text.tag_ranges('error')
        assert console.text.tag_ranges('route') and console.text.tag_ranges('time')
        console.filter.set('Network');console.render()
        assert 'ACK' in console.text.get('1.0','end') and 'Connection' not in console.text.get('1.0','end')
        console.filter.set('All events');console.query.set('cautious');console.render()
        assert 'Route changed' in console.text.get('1.0','end')
        assert 'ACK' not in console.text.get('1.0','end')
        assert console.text.tag_ranges('match')
        console.user_scroll('moveto',0)
        assert not console.follow.get()
        console.query.set('');console.render()
        for i in range(1510):console.records.append((i,'ready','Bounded log fixture'))
        console.render()
        assert len(console.records)==1500
        assert '1500 events'==console.count.get()
        console.append('error','Live bounded-console check',1511)
        assert len(console.records)==1500
        assert int(console.text.index('end-1c').split('.')[0])==1501
        assert 'Live bounded-console check' in console.text.get('end-2l','end')
    finally:
        app.worker.commands.put(('stop',None));app.worker.join(timeout=5)
        app.canvas.close();root.destroy()
        assert not app.worker.is_alive()


if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    verify(Path(sys.argv[1]))
    print('DARK_SHELL_VERIFIED')
