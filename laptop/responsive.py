"""Size-aware desktop panes without a fixed monitor aspect ratio."""


class ResponsiveWorkspace:
    def __init__(self, app, vertical, upper, bottom, config, transport):
        self.app, self.root = app, app.root
        self.vertical, self.upper = vertical, upper
        self.bottom, self.config, self.transport = bottom, config, transport
        self.last_size = None
        self.timer = None
        self.bottom_fraction = None
        self.inspector_width = 254
        self.app._layout_ready = False
        vertical.bind('<Configure>', self.schedule, add='+')
        upper.bind('<ButtonRelease-1>', self.remember_inspector, add='+')
        vertical.bind('<ButtonRelease-1>', self.remember_bottom, add='+')
        app.inspector.bind('<Configure>', lambda e: config.configure(width=e.width), add='+')
        self.root.after(150, self.schedule)

    def schedule(self, _=None):
        if self.timer:
            self.root.after_cancel(self.timer)
        self.timer = self.root.after(60, self.arrange)

    def minimum_inspector(self):
        editor = getattr(self.app, 'editor', None)
        if not editor:
            return 254
        rows = [row.winfo_reqwidth()+24 for body in editor.page_bodies
                for row in body.winfo_children() if row.winfo_class()=='TFrame']
        toolbar = max((w.winfo_reqwidth()+12 for w in editor.top.winfo_children()), default=0)
        return max(254, toolbar, editor.tabs.winfo_reqwidth(), *rows)

    def minimum_bottom(self):
        # The fixed-width configuration column must show its complete controls.
        config_height = sum(w.winfo_reqheight()+4 for w in self.config.winfo_children())+12
        # Include enough console space after its filter bar wraps on narrow views.
        from tkinter import font, ttk
        console = self.app.console
        line = font.Font(font=console.text.cget('font')).metrics('linespace')
        tab_font = ttk.Style(self.root).lookup('TNotebook.Tab','font') or 'TkDefaultFont'
        tab = font.Font(font=tab_font).metrics('linespace')+10
        console_height = console.bar.winfo_reqheight()+2*line+tab+12
        return max(180, self.transport.winfo_reqheight()+max(config_height, console_height)+4)

    def arrange(self):
        self.timer = None
        if self.app.closing or not self.vertical.winfo_exists():
            return
        width, height = self.vertical.winfo_width(), self.vertical.winfo_height()
        if width < 600 or height < 350:
            return
        # Moving to a monitor with a different font/DPI scale also changes these
        # requested dimensions, even if the window's logical size stays equal.
        minimum_width = self.minimum_inspector()
        minimum_bottom = self.minimum_bottom()
        signature = (width, height, minimum_width, minimum_bottom)
        if signature == self.last_size:
            return
        self.last_size = signature
        inspector = min(max(minimum_width, self.inspector_width), max(minimum_width, width-420))
        self.upper.sashpos(0, inspector)
        fraction = self.bottom_fraction if self.bottom_fraction is not None else .25
        panel = min(max(minimum_bottom, round(height*fraction)), max(minimum_bottom, height-280))
        self.vertical.sashpos(0, height-panel)
        self.app._layout_ready = True
        self.app.draw_timeline()

    def remember_inspector(self, _=None):
        if self.app._layout_ready:
            self.inspector_width = self.upper.sashpos(0)

    def remember_bottom(self, _=None):
        if self.app._layout_ready:
            height = max(1, self.vertical.winfo_height())
            self.bottom_fraction = (height-self.vertical.sashpos(0))/height

    def fit_overview(self, _=None):
        overview = self.app.minimap
        if not overview.winfo_ismapped():
            return
        canvas = self.app.canvas
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 50 or height < 50:
            return
        if overview.expanded:
            size = (min(640, width-24), min(360, height-75))
        else:
            size = (max(220, min(250, width//3)), min(155, max(120,height-100)))
        overview.place_configure(width=size[0], height=size[1])
