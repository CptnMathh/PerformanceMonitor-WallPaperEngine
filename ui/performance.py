"""
Performance views - detailed views for each metric type.
CPU, Memory, GPU, Disks, Network.
"""
import tkinter as tk
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "base"))

from config import C, T
from ui.graphs import MainGraph, CoreBarGraph
from ui.widgets import BigValueLabel, UnitLabel, SubtitleLabel, StatLabel, StatBox


class PerformanceView(tk.Frame):
    """Base class for performance views."""
    
    def __init__(self, parent, metric_meta, **kwargs):
        self.metric_meta = metric_meta
        super().__init__(parent, bg=C["panel_bg"], **kwargs)
        self.pack(fill="both", expand=True)
        
        # Order matters for the packer: fixed-height sections (header, value,
        # stats) are packed before the expanding graph so they always keep
        # their space and stay visible, while the graph flexes to fill the
        # rest. This keeps every section readable at any window size.
        self._build_header()
        self._build_value_display()
        self._build_stats()
        self._build_graph()
    
    def _build_header(self):
        """Build header with metric name."""
        self.header = tk.Frame(self, bg=C["panel_bg"])
        self.header.pack(fill="x", padx=20, pady=(16, 8))
        
        tk.Label(
            self.header, text=self.metric_meta["label"].upper(),
            font=("Segoe UI", 18, "bold"),
            bg=C["panel_bg"], fg=C["fg_hi"]
        ).pack(side="left")
        
        self.subtitle = SubtitleLabel(self.header)
        self.subtitle.pack(side="right", pady=(8, 0))
    
    def _build_value_display(self):
        """Build main value display."""
        self.value_frame = tk.Frame(self, bg=C["panel_bg"])
        self.value_frame.pack(fill="x", padx=20, pady=(0, 4))
        
        self.big_value = BigValueLabel(self.value_frame)
        self.big_value.pack(side="left")
        
        self.unit = UnitLabel(self.value_frame, text=self.metric_meta["unit"])
        self.unit.pack(side="left", padx=(4, 0), pady=(10, 0))
    
    def _build_graph(self):
        """Build main graph."""
        self.graph_container = tk.Frame(
            self, bg=C["graph_bg"],
            highlightbackground=C["border"], highlightthickness=1
        )
        self.graph_container.pack(fill="both", expand=True, padx=20, pady=(4, 8))
        
        self.graph_header = tk.Frame(self.graph_container, bg=C["graph_bg"])
        self.graph_header.pack(fill="x", padx=8, pady=(6, 2))
        
        tk.Label(
            self.graph_header, text="100 %",
            font=("Consolas", 7),
            bg=C["graph_bg"], fg=C["dim"]
        ).pack(side="right")
        
        tk.Label(
            self.graph_header, text="60 secondes",
            font=("Segoe UI", 7),
            bg=C["graph_bg"], fg=C["dim"]
        ).pack(side="left")
        
        self.main_graph = MainGraph(
            self.graph_container,
            self.metric_meta["key"],
            self.metric_meta["color"]
        )
        self.main_graph.pack(fill="both", expand=True, padx=4, pady=(0, 6))
    
    def _build_stats(self):
        """Build statistics section.

        Pinned to the bottom so the stat cards stay visible at any window size;
        the graph above flexes to fill the remaining space.
        """
        self.stats_frame = tk.Frame(self, bg=C["panel_bg"])
        self.stats_frame.pack(side="bottom", fill="x", padx=20, pady=(0, 12))
        self.stat_labels = {}
        self.stat_boxes = {}

    def _build_stat_grid(self, specs, cols=4):
        """Create a grid of StatBox cards. specs = [(key, title), ...]."""
        grid = tk.Frame(self.stats_frame, bg=C["panel_bg"])
        grid.pack(fill="x", pady=(8, 4))
        for c in range(cols):
            grid.columnconfigure(c, weight=1, uniform="stat")
        for i, (key, title) in enumerate(specs):
            r, cc = divmod(i, cols)
            box = StatBox(grid, title)
            box.grid(row=r, column=cc,
                     padx=(0 if cc == 0 else 6, 0), pady=3, sticky="ew")
            self.stat_boxes[key] = box
        return self.stat_boxes
    
    def update(self, data, history):
        """Update view with new data."""
        value = self._extract_value(data)
        
        # Update big value
        if value is None:
            self.big_value.configure(text="N/A", fg=C["dim"])
        else:
            self.big_value.configure(text=self._format_big_value(value))
            self._update_color(value)
        
        # Update subtitle
        self._update_subtitle(data)
        
        # Update graph: history may be the full hist dict or a list
        key = self.metric_meta["key"]
        hist = history.get(key, []) if isinstance(history, dict) else history
        self.main_graph.update(hist, self.metric_meta)
        
        # Update stats
        self._update_stats(data)
    
    def _extract_value(self, data):
        """Extract value from data."""
        key = self.metric_meta["key"]
        if key == "cpu":
            return data.get("cpu")
        elif key == "cpu_temp":
            return data.get("cpu_temp")
        elif key == "ram":
            return data.get("memory")
        elif key == "gpu":
            return data.get("gpu_usage")
        elif key == "gpu_temp":
            return data.get("gpu_temp")
        elif key == "vram":
            return data.get("vram_usage")
        elif key == "net_dn":
            return data.get("download_speed")
        elif key == "net_up":
            return data.get("upload_speed")
        elif key == "cpu_fan":
            return data.get("cpu_fan")
        elif key == "case_fans":
            return data.get("case_fans")
        elif key.startswith("disk_"):
            drive = key.replace("disk_", "")
            disks = data.get("_disks", {})
            if drive in disks:
                return disks[drive].get("pct")
        return None
    
    def _format_big_value(self, value):
        """Format value for big display."""
        key = self.metric_meta["key"]
        if key in ("cpu_fan", "case_fans"):
            return f"{int(value)}"
        elif key in ("net_dn", "net_up"):
            return f"{value:.2f}"
        elif key in ("cpu_temp", "gpu_temp"):
            return f"{value:.1f}"
        elif isinstance(value, float) and value != int(value):
            return f"{value:.1f}"
        else:
            return f"{int(value)}"
    
    def _update_color(self, value):
        """Update color based on thresholds."""
        warn = self.metric_meta.get("warn")
        hot = self.metric_meta.get("hot")
        
        if warn and value is not None:
            if value >= hot:
                self.big_value.configure(fg=C["hot"])
            elif value >= warn:
                self.big_value.configure(fg=C["warn"])
            else:
                self.big_value.configure(fg=self.metric_meta["color"])
        else:
            self.big_value.configure(fg=self.metric_meta["color"])
    
    def _update_subtitle(self, data):
        """Update subtitle."""
        key = self.metric_meta["key"]
        if key in ("gpu", "gpu_temp", "vram"):
            self.subtitle.configure(text=data.get("gpu_name", ""))
        elif key == "cpu":
            self.subtitle.configure(text=data.get("cpu_name", ""))
        else:
            self.subtitle.configure(text="")
    
    def _update_stats(self, data):
        """Update statistics (override in subclasses)."""
        pass


class CPUView(PerformanceView):
    """CPU detailed view with per-core display."""
    
    def _build_stats(self):
        """Build CPU-specific stats."""
        super()._build_stats()

        # Per-core graph (pinned just above the stat cards)
        self.core_graph_frame = tk.Frame(
            self, bg=C["graph_bg"],
            highlightbackground=C["border"], highlightthickness=1
        )
        self.core_graph_frame.pack(side="bottom", fill="x", padx=20, pady=(0, 8))

        tk.Label(
            self.core_graph_frame, text="Cœurs logiques",
            font=("Segoe UI", 8, "bold"),
            bg=C["graph_bg"], fg=C["dim"]
        ).pack(anchor="w", padx=8, pady=(6, 2))

        self.core_graph = CoreBarGraph(
            self.core_graph_frame, self.metric_meta["color"], height=90
        )
        self.core_graph.pack(fill="both", expand=True, padx=4, pady=(0, 6))

        # Stat cards
        self._build_stat_grid([
            ("cores", "Cœurs"),
            ("freq", "Fréquence"),
            ("processes", "Processus"),
            ("threads_count", "Threads"),
            ("uptime_sys", "Uptime système"),
            ("uptime_app", "Session"),
        ], cols=4)

    def _update_stats(self, data):
        """Update CPU stats."""
        from metrics import fmt_duration
        logical = data.get("cpu_logical", 0)
        physical = data.get("cpu_physical", 0)
        freq = data.get("cpu_freq_cur", 0)
        b = self.stat_boxes
        b["cores"].set(f"{physical} / {logical}")
        b["freq"].set(f"{freq:.2f} GHz")
        b["processes"].set(str(data.get("process_count", "—")))
        b["threads_count"].set(str(data.get("thread_count", "—")))
        b["uptime_sys"].set(fmt_duration(data.get("uptime_sys", 0)))
        b["uptime_app"].set(fmt_duration(data.get("uptime_app", 0)))

        # Per-core graph
        self.core_graph.update(data.get("cpu_percore", []))


class MemoryView(PerformanceView):
    """Memory detailed view."""
    
    def _build_stats(self):
        """Build memory-specific stats."""
        super()._build_stats()
        self._build_stat_grid([
            ("used", "Utilisée"),
            ("available", "Disponible"),
            ("total", "Totale"),
            ("uptime", "Session"),
        ], cols=4)

    def _update_stats(self, data):
        """Update memory stats."""
        from metrics import fmt_duration
        b = self.stat_boxes
        b["used"].set(f"{data.get('memory_used_gb', 0):.1f} GB")
        b["available"].set(f"{data.get('memory_avail_gb', 0):.1f} GB")
        b["total"].set(f"{data.get('memory_total_gb', 0):.1f} GB")
        b["uptime"].set(fmt_duration(data.get("uptime_app", 0)))


class GPUView(PerformanceView):
    """GPU detailed view."""
    
    def _build_stats(self):
        """Build GPU-specific stats."""
        super()._build_stats()
        self._build_stat_grid([
            ("gpu_usage", "Utilisation"),
            ("gpu_temp", "Température"),
            ("vram_used", "VRAM utilisée"),
            ("vram_total", "VRAM totale"),
        ], cols=4)

    def _update_stats(self, data):
        """Update GPU stats."""
        b = self.stat_boxes
        b["gpu_usage"].set(f"{data.get('gpu_usage', 0):.0f} %")
        b["gpu_temp"].set(f"{data.get('gpu_temp', 0):.0f} °C")
        b["vram_used"].set(f"{data.get('vram_used_gb', 0):.1f} GB")
        b["vram_total"].set(f"{data.get('vram_total_gb', 0):.1f} GB")


class DiskView(PerformanceView):
    """Disk detailed view."""
    
    def _build_stats(self):
        """Build disk-specific stats."""
        super()._build_stats()
        self._build_stat_grid([
            ("used", "Utilisé"),
            ("available", "Libre"),
            ("total", "Total"),
        ], cols=3)

    def _update_stats(self, data):
        """Update disk stats."""
        drive = self.metric_meta["key"].replace("disk_", "")
        disks = data.get("_disks", {})
        dd = disks.get(drive)
        b = self.stat_boxes
        if dd:
            b["used"].set(f"{dd.get('used', 0):.1f} GB")
            b["available"].set(f"{dd.get('free', 0):.1f} GB")
            b["total"].set(f"{dd.get('total', 0):.1f} GB")


class NetworkView(PerformanceView):
    """Network detailed view."""
    
    def _build_stats(self):
        """Build network-specific stats."""
        super()._build_stats()
        self._build_stat_grid([
            ("download", "Téléchargement"),
            ("upload", "Envoi"),
        ], cols=2)

    def _update_stats(self, data):
        """Update network stats."""
        b = self.stat_boxes
        b["download"].set(f"{data.get('download_speed', 0):.2f} MB/s")
        b["upload"].set(f"{data.get('upload_speed', 0):.2f} MB/s")


class GeneralView(tk.Frame):
    """Summary view: min / max / avg for every tracked metric, no graphs."""

    # Human-readable labels for each stat key
    _LABELS = {
        "cpu":       ("CPU",         "%"),
        "ram":       ("RAM",         "%"),
        "gpu":       ("GPU",         "%"),
        "gpu_temp":  ("GPU Temp",    "°"),
        "vram":      ("VRAM",        "%"),
        "net_dn":    ("Réseau ↓",    "MB/s"),
        "net_up":    ("Réseau ↑",    "MB/s"),
        "cpu_temp":  ("CPU Temp",    "°"),
        "cpu_fan":   ("CPU Fan",     "RPM"),
        "case_fans": ("Case Fans",   "RPM"),
    }

    def __init__(self, parent, metric_meta, **kwargs):
        super().__init__(parent, bg=C["panel_bg"], **kwargs)
        self.pack(fill="both", expand=True)
        self._rows = {}
        self._build()

    def _build(self):
        header = tk.Frame(self, bg=C["panel_bg"])
        header.pack(fill="x", padx=20, pady=(16, 4))
        tk.Label(header, text="GÉNÉRAL", font=("Segoe UI", 18, "bold"),
                 bg=C["panel_bg"], fg=C["fg_hi"]).pack(side="left")
        tk.Label(header, text="min / max / avg par session",
                 font=("Segoe UI", 9), bg=C["panel_bg"],
                 fg=C["fg_dark"]).pack(side="left", padx=(12, 0), pady=(8, 0))

        tk.Frame(self, bg=C["border"], height=1).pack(fill="x", padx=20, pady=(0, 8))

        grid = tk.Frame(self, bg=C["panel_bg"])
        grid.pack(fill="both", expand=True, padx=20, pady=4)

        # Column headers
        for col, text in enumerate(("Métrique", "Min", "Max", "Moy")):
            tk.Label(grid, text=text, font=("Segoe UI", 8, "bold"),
                     bg=C["panel_bg"], fg=C["fg_dark"],
                     width=10, anchor="w").grid(row=0, column=col, padx=4, pady=(0, 6))

        for i, (key, (label, unit)) in enumerate(self._LABELS.items(), start=1):
            tk.Label(grid, text=label, font=("Segoe UI", 9),
                     bg=C["panel_bg"], fg=C["fg"], anchor="w",
                     width=10).grid(row=i, column=0, padx=4, pady=3, sticky="w")
            row_vars = {}
            for j, col in enumerate(("min", "max", "avg"), start=1):
                var = tk.StringVar(value="—")
                tk.Label(grid, textvariable=var, font=("Consolas", 9),
                         bg=C["surface2"], fg=C["fg_hi"], anchor="e",
                         width=10, relief="flat", padx=6, pady=4
                         ).grid(row=i, column=j, padx=4, pady=3, sticky="ew")
                row_vars[col] = var
            row_vars["unit"] = unit
            self._rows[key] = row_vars

    def update(self, data, history):
        stats = data.get("_stats", {})
        for key, row in self._rows.items():
            s = stats.get(key)
            if s:
                unit = row["unit"]
                row["min"].set(f"{s['min']}{unit}")
                row["max"].set(f"{s['max']}{unit}")
                row["avg"].set(f"{s['avg']}{unit}")


class LHMView(tk.Frame):
    """Scrollable view showing all LibreHardwareMonitor sensors grouped by hardware."""

    # Colour accent per hardware type
    _HW_COLORS = {
        "cpu":  "#0078d4",
        "gpu":  "#107c10",
        "ram":  "#8764b8",
        "mb":   "#d83b01",
        "disk": "#ca5010",
    }

    # Friendly labels imported from collector helpers at runtime to avoid
    # a circular-import (performance.py → collector.py → config.py)
    _HW_LABELS   = None
    _GRP_LABELS  = None
    _GRP_ORDER   = None

    def __init__(self, parent, metric_meta, **kwargs):
        super().__init__(parent, bg=C["panel_bg"], **kwargs)
        self.pack(fill="both", expand=True)
        self._vars   = {}    # (hw_name, grp, sensor_name) → StringVar
        self._built  = False # True once the widget tree has been created
        self._was_ok = None  # last known connection state

        # Lazy-import labels from collector (avoids circular import at module level)
        if LHMView._HW_LABELS is None:
            try:
                import sys, os
                _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                sys.path.insert(0, os.path.join(_root, "base"))
                from collector import LHM_GROUP_LABELS, LHM_HW_LABELS, _LHM_GROUP_ORDER
                LHMView._HW_LABELS  = LHM_HW_LABELS
                LHMView._GRP_LABELS = LHM_GROUP_LABELS
                LHMView._GRP_ORDER  = _LHM_GROUP_ORDER
            except Exception:
                LHMView._HW_LABELS  = {}
                LHMView._GRP_LABELS = {}
                LHMView._GRP_ORDER  = []

        self._build_shell()

    # ── shell (header + scrollable canvas) ───────────────────────────────────

    def _build_shell(self):
        # Header row
        hdr = tk.Frame(self, bg=C["panel_bg"])
        hdr.pack(fill="x", padx=20, pady=(16, 4))
        tk.Label(hdr, text="HW MONITOR", font=("Segoe UI", 18, "bold"),
                 bg=C["panel_bg"], fg=C["fg_hi"]).pack(side="left")
        self._status_lbl = tk.Label(hdr, text="", font=("Segoe UI", 9),
                                    bg=C["panel_bg"], fg=C["fg_dark"])
        self._status_lbl.pack(side="left", padx=(14, 0), pady=(8, 0))
        tk.Frame(self, bg=C["border"], height=1).pack(fill="x", padx=20, pady=(0, 6))

        # Scrollable canvas
        self._canvas = tk.Canvas(self, bg=C["panel_bg"],
                                 highlightthickness=0, bd=0)
        self._sb = tk.Scrollbar(self, orient="vertical",
                                command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._sb.set)
        self._sb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._inner = tk.Frame(self._canvas, bg=C["panel_bg"])
        self._win   = self._canvas.create_window(
            (0, 0), window=self._inner, anchor="nw")

        self._inner.bind("<Configure>",
                         lambda e: self._canvas.configure(
                             scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
                          lambda e: self._canvas.itemconfig(
                              self._win, width=e.width))
        self._canvas.bind("<MouseWheel>",
                          lambda e: self._canvas.yview_scroll(
                              -1 * (e.delta // 120), "units"))

        # "not connected" placeholder
        self._placeholder = tk.Frame(self._inner, bg=C["panel_bg"])
        self._placeholder.pack(fill="x", padx=20, pady=40)
        tk.Label(self._placeholder, text="LibreHardwareMonitor non connecté",
                 font=("Segoe UI", 12, "bold"),
                 bg=C["panel_bg"], fg=C["fg_dark"]).pack()
        tk.Label(self._placeholder,
                 text=("Lancez LHM → Options → Remote Web Server\n"
                       "Activez 'Run' sur le port 8085, puis relancez."),
                 font=("Segoe UI", 9),
                 bg=C["panel_bg"], fg=C["fg_dark"],
                 justify="center").pack(pady=(8, 0))

    # ── build sensor widgets once LHM connects ────────────────────────────────

    def _build_sensors(self, hardware):
        """Create the full sensor widget tree from the hardware list."""
        self._placeholder.pack_forget()
        self._vars.clear()

        for widget in list(self._inner.children.values()):
            if widget is not self._placeholder:
                widget.destroy()

        hw_labels  = self._HW_LABELS  or {}
        grp_labels = self._GRP_LABELS or {}
        grp_order  = self._GRP_ORDER  or []

        for hw in hardware:
            hw_type  = hw.get("type", "")
            hw_name  = hw.get("name", "?")
            groups   = hw.get("groups", {})
            color    = self._HW_COLORS.get(hw_type, C["fg_dim"])
            hw_lbl   = hw_labels.get(hw_type, hw_type.upper())

            # Hardware card
            card = tk.Frame(self._inner, bg=C["surface"],
                            highlightbackground=color,
                            highlightthickness=1)
            card.pack(fill="x", padx=16, pady=(8, 2))

            # Card header
            card_hdr = tk.Frame(card, bg=color)
            card_hdr.pack(fill="x")
            tk.Label(card_hdr,
                     text=f"  {hw_lbl}  —  {hw_name}",
                     font=("Segoe UI", 8, "bold"),
                     bg=color, fg="#ffffff",
                     anchor="w", pady=4).pack(fill="x")

            body = tk.Frame(card, bg=C["surface"])
            body.pack(fill="x", padx=8, pady=6)

            # Sensor groups in defined order
            ordered_grps = [g for g in grp_order if g in groups]
            ordered_grps += [g for g in groups if g not in grp_order]

            for grp in ordered_grps:
                sensors = groups[grp]
                if not sensors:
                    continue
                glbl = grp_labels.get(grp, grp.capitalize())
                tk.Label(body, text=glbl,
                         font=("Segoe UI", 7, "bold"),
                         bg=C["surface"], fg=color,
                         anchor="w").pack(fill="x", padx=4, pady=(6, 2))

                for s in sensors:
                    row = tk.Frame(body, bg=C["surface"])
                    row.pack(fill="x", padx=4, pady=1)
                    tk.Label(row, text=s["name"],
                             font=("Segoe UI", 8),
                             bg=C["surface"], fg=C["fg"],
                             anchor="w", width=26).pack(side="left")
                    var = tk.StringVar(
                        value=f"{s['val']:.1f} {s['unit']}")
                    tk.Label(row, textvariable=var,
                             font=("Consolas", 9),
                             bg=C["surface2"], fg=C["fg_hi"],
                             anchor="e", width=14,
                             relief="flat", padx=6, pady=2
                             ).pack(side="right")
                    self._vars[(hw_name, grp, s["name"])] = var

        self._built = True

    # ── update (called every poll tick) ──────────────────────────────────────

    def update(self, data, history):
        lhm      = data.get("_lhm", {})
        is_ok    = bool(lhm.get("ok", False))
        hardware = lhm.get("hardware", [])

        # Update status badge
        if is_ok:
            self._status_lbl.configure(
                text="● Connecté via LHM", fg=C.get("ok", "#16c60c"))
        else:
            self._status_lbl.configure(
                text="○ En attente…", fg=C["fg_dark"])

        # If connection state changed, rebuild widget tree
        if is_ok != self._was_ok:
            self._was_ok = is_ok
            if is_ok:
                self._placeholder.pack_forget()
                self._build_sensors(hardware)
            else:
                self._built = False
                self._placeholder.pack(fill="x", padx=20, pady=40)
            return

        if not is_ok or not self._built:
            return

        # Efficient value-only updates via StringVars
        for hw in hardware:
            hw_name = hw.get("name", "")
            for grp, sensors in hw.get("groups", {}).items():
                for s in sensors:
                    key = (hw_name, grp, s["name"])
                    var = self._vars.get(key)
                    if var:
                        var.set(f"{s['val']:.1f} {s['unit']}")


class AMDView(tk.Frame):
    """View showing AMD Ryzen Master metrics."""

    def __init__(self, parent, metric_meta, **kwargs):
        super().__init__(parent, bg=C["panel_bg"], **kwargs)
        self.pack(fill="both", expand=True)
        self._vars = {}
        self._built = False
        self._was_ok = None
        self._build_shell()

    def _build_shell(self):
        # Header row
        hdr = tk.Frame(self, bg=C["panel_bg"])
        hdr.pack(fill="x", padx=20, pady=(16, 4))
        tk.Label(hdr, text="AMD RYZEN MASTER", font=("Segoe UI", 18, "bold"),
                 bg=C["panel_bg"], fg="#ff4500").pack(side="left")
        self._status_lbl = tk.Label(hdr, text="", font=("Segoe UI", 9),
                                    bg=C["panel_bg"], fg=C["fg_dark"])
        self._status_lbl.pack(side="left", padx=(14, 0), pady=(8, 0))
        tk.Frame(self, bg=C["border"], height=1).pack(fill="x", padx=20, pady=(0, 6))

        # Scrollable canvas
        self._canvas = tk.Canvas(self, bg=C["panel_bg"],
                                 highlightthickness=0, bd=0)
        self._sb = tk.Scrollbar(self, orient="vertical",
                                command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._sb.set)
        self._sb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._inner = tk.Frame(self._canvas, bg=C["panel_bg"])
        self._win = self._canvas.create_window(
            (0, 0), window=self._inner, anchor="nw")

        self._inner.bind("<Configure>",
                         lambda e: self._canvas.configure(
                             scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
                          lambda e: self._canvas.itemconfig(
                              self._win, width=e.width))
        self._canvas.bind("<MouseWheel>",
                          lambda e: self._canvas.yview_scroll(
                              -1 * (e.delta // 120), "units"))

        # "not connected" placeholder
        self._placeholder = tk.Frame(self._inner, bg=C["panel_bg"])
        self._placeholder.pack(fill="x", padx=20, pady=40)
        tk.Label(self._placeholder, text="AMD Ryzen Master SDK non connecté",
                 font=("Segoe UI", 12, "bold"),
                 bg=C["panel_bg"], fg=C["fg_dark"]).pack()
        tk.Label(self._placeholder,
                 text=("Le DLL AMDRyzenMasterMonitoringDLL.dll est présent\n"
                       "mais le SDK n'a pas pu être initialisé.\n"
                       "Vérifiez que vous avez les droits administrateur\n"
                       "et que le driver Ryzen Master est installé."),
                 font=("Segoe UI", 9),
                 bg=C["panel_bg"], fg=C["fg_dark"],
                 justify="center").pack(pady=(8, 0))

    def _build_metrics(self):
        """Build AMD metrics display."""
        self._placeholder.pack_forget()
        self._vars.clear()

        for widget in list(self._inner.children.values()):
            if widget is not self._placeholder:
                widget.destroy()

        # Group 1: Temperature & Power
        grp1 = tk.Frame(self._inner, bg=C["panel_bg"])
        grp1.pack(fill="x", padx=20, pady=(12, 8))
        tk.Label(grp1, text="TEMPÉRATURE & PUISSANCE", font=("Segoe UI", 10, "bold"),
                 bg=C["panel_bg"], fg=C["fg_hi"]).pack(anchor="w", pady=(0, 8))

        grid1 = tk.Frame(grp1, bg=C["panel_bg"])
        grid1.pack(fill="x")
        for c in range(2):
            grid1.columnconfigure(c, weight=1, uniform="amd")

        self._add_metric_card(grid1, "amd_temp", "Température CPU", "°C", 0, 0)
        self._add_metric_card(grid1, "amd_ppt", "PPT (Package Power)", "W", 0, 1)

        # Group 2: Current Limits
        grp2 = tk.Frame(self._inner, bg=C["panel_bg"])
        grp2.pack(fill="x", padx=20, pady=(8, 8))
        tk.Label(grp2, text="LIMITES DE COURANT", font=("Segoe UI", 10, "bold"),
                 bg=C["panel_bg"], fg=C["fg_hi"]).pack(anchor="w", pady=(0, 8))

        grid2 = tk.Frame(grp2, bg=C["panel_bg"])
        grid2.pack(fill="x")
        for c in range(2):
            grid2.columnconfigure(c, weight=1, uniform="amd")

        self._add_metric_card(grid2, "amd_edc", "EDC (Electrical Design Current)", "A", 0, 0)
        self._add_metric_card(grid2, "amd_tdc", "TDC (Thermal Design Current)", "A", 0, 1)

        # Group 3: Voltages
        grp3 = tk.Frame(self._inner, bg=C["panel_bg"])
        grp3.pack(fill="x", padx=20, pady=(8, 8))
        tk.Label(grp3, text="TENSIONS", font=("Segoe UI", 10, "bold"),
                 bg=C["panel_bg"], fg=C["fg_hi"]).pack(anchor="w", pady=(0, 8))

        grid3 = tk.Frame(grp3, bg=C["panel_bg"])
        grid3.pack(fill="x")
        for c in range(2):
            grid3.columnconfigure(c, weight=1, uniform="amd")

        self._add_metric_card(grid3, "amd_peak_voltage", "Tension de crête", "V", 0, 0)
        self._add_metric_card(grid3, "amd_avg_voltage", "Tension moyenne", "V", 0, 1)

        self._built = True

    def _add_metric_card(self, parent, key, label, unit, row, col):
        """Add a metric card to the grid."""
        card = tk.Frame(parent, bg=C["surface2"], relief="flat", bd=0)
        card.grid(row=row, column=col, padx=(0 if col == 0 else 6, 0), pady=3, sticky="ew")

        tk.Label(card, text=label, font=("Segoe UI", 8),
                 bg=C["surface2"], fg=C["fg_dim"]).pack(anchor="w", padx=8, pady=(6, 2))

        var = tk.StringVar(value="—")
        tk.Label(card, textvariable=var, font=("Consolas", 12, "bold"),
                 bg=C["surface2"], fg=C["fg_hi"]).pack(anchor="w", padx=8, pady=(0, 6))

        self._vars[key] = (var, unit)

    def update(self, data, history):
        """Update AMD metrics."""
        ryzen_ok = data.get("ryzen_ok", False)

        if ryzen_ok != self._was_ok:
            self._was_ok = ryzen_ok
            if ryzen_ok:
                self._status_lbl.configure(text="● Connecté", fg=C["ok"])
                if not self._built:
                    self._build_metrics()
            else:
                self._status_lbl.configure(text="○ Inactif", fg=C["fg_dark"])
                if self._built:
                    self._placeholder.pack(fill="x", padx=20, pady=40)
                    for widget in list(self._inner.children.values()):
                        if widget is not self._placeholder:
                            widget.destroy()
                    self._built = False

        if not ryzen_ok or not self._built:
            return

        # Update metric values
        for key, (var, unit) in self._vars.items():
            val = data.get(key)
            if val is not None:
                var.set(f"{val:.1f} {unit}")
            else:
                var.set("—")


def create_performance_view(parent, metric_meta):
    """Factory function to create appropriate performance view."""
    key = metric_meta["key"]

    if key == "general":
        return GeneralView(parent, metric_meta)
    elif key == "lhm":
        return LHMView(parent, metric_meta)
    elif key == "amd":
        return AMDView(parent, metric_meta)
    elif key == "cpu":
        return CPUView(parent, metric_meta)
    elif key == "ram":
        return MemoryView(parent, metric_meta)
    elif key in ("gpu", "gpu_temp", "vram"):
        return GPUView(parent, metric_meta)
    elif key.startswith("disk_"):
        return DiskView(parent, metric_meta)
    elif key in ("net_dn", "net_up"):
        return NetworkView(parent, metric_meta)
    else:
        return PerformanceView(parent, metric_meta)
