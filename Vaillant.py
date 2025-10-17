"""
Heating curves visualizer for Vaillant calorMATIC 630 (Tkinter + Matplotlib)

Model:
  T_flow = clamp(Tmin, T_room + Hc(slope) * (T_room - T_out), Tmax)

Where:
  - slope in [0.2, 4.0] is the "опалювальна крива" number shown on the Vaillant chart
  - Hc(slope) is an empirical gain calibrated to the official chart (visual interpolation)
  - clamp applies user-configured Tmin / Tmax for the selected circuit (e.g. floor/rads)
  - Parallel shift by room setpoint (18/20/22 °C lines on Fig. 3.4) is naturally captured.

DISCLAIMER:
  Vaillant does not publish an exact formula in the public user manual; this code uses a
  carefully calibrated approximation. If you have a more precise digitization of the chart,
  just update the ANCHORS list below — the rest will work automatically.

Author: ChatGPT
License: MIT
"""

import math
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


# -----------------------------
# Calibration of Hc(slope)
# -----------------------------
# Each tuple is (slope, Hc). Hc ≈ (Tflow - Troom) / (Troom - Tout) for the 20 °C room baselines on the chart.
# Points below are taken/estimated from the official Vaillant chart (visual interpolation of gridlines):
ANCHORS: List[Tuple[float, float]] = [
    (0.2, 0.40),   # @0°C → ~28 °C
    (0.4, 0.70),   # mild estimate between 0.2 and 0.6 (chart spacing suggests ~0.7)
    (0.6, 1.00),   # @0°C → ~40 °C
    (0.8, 1.40),   # estimated from chart progression near 0.8
    (1.0, 1.75),   # @0°C → ~55 °C
    (1.2, 1.90),   # near 58–59 °C @0°C (thin spacing region)
    (1.5, 2.00),   # @0°C → ~60 °C; also matches 67 °C @0°C when room 22 °C in manual example
    (2.0, 2.25),   # @0°C → ~65 °C
    (2.5, 2.50),   # @0°C → ~70 °C
    (3.0, 2.75),   # @0°C → ~75 °C
    # For 4.0 we have a reliable point at +5 °C: Tflow ≈ 82 °C → Hc ≈ (82-20)/(20-5) = 4.133...
    # Using it as anchor (will be slightly conservative at 0 °C but clamped by Tmax anyway).
    (3.5, 3.40),   # smooth transition towards the steepest curve
    (4.0, 4.133),
]

SLOPE_MIN, SLOPE_MAX = 0.2, 4.0


def hc_from_slope(s: float) -> float:
    """Linear interpolation of Hc(slope) through ANCHORS."""
    s_vals = np.array([p[0] for p in ANCHORS], dtype=float)
    h_vals = np.array([p[1] for p in ANCHORS], dtype=float)
    s_clamped = np.clip(s, s_vals.min(), s_vals.max())
    return float(np.interp(s_clamped, s_vals, h_vals))


def tflow(room: float, tout: float, slope: float, tmin: float, tmax: float) -> float:
    """Compute supply temperature by the calibrated model with clamp."""
    hc = hc_from_slope(slope)
    tf = room + hc * (room - tout)
    return float(max(tmin, min(tmax, tf)))


# -----------------------------
# UI helpers / styling
# -----------------------------
PRIMARY_BG = "#0f172a"   # slate-900
CARD_BG    = "#111827"   # gray-900
ACCENT     = "#22c55e"   # green-500
MUTED      = "#94a3b8"   # slate-400
FG         = "#e5e7eb"   # gray-200


@dataclass
class State:
    room: float = 20.0
    tout: float = 0.0
    slope: float = 1.0
    tmin: float = 25.0
    tmax: float = 90.0
    show_all: bool = True
    show_grid: bool = True
    highlight_182022: bool = True


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("calorMATIC 630 • Heating Curves (Tkinter)")
        self.state = State()

        # window
        self.configure(bg=PRIMARY_BG)
        self.geometry("1120x720")
        self.minsize(960, 640)

        # ttk theme (clam) + custom styles
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=PRIMARY_BG)
        style.configure("Card.TFrame", background=CARD_BG, relief="flat")
        style.configure("TLabel", background=PRIMARY_BG, foreground=FG, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=CARD_BG, foreground=FG, font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 13))
        style.configure("H1.TLabel", font=("Segoe UI Semibold", 16))
        style.configure("TButton", background=ACCENT, foreground="#0b1320", font=("Segoe UI Semibold", 10), borderwidth=0, padding=8)
        style.map("TButton", background=[("active", "#16a34a")])
        style.configure("TCheckbutton", background=CARD_BG, foreground=FG)

        # Layout: left controls, right plot
        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=16, pady=16)

        left = ttk.Frame(main, style="Card.TFrame")
        left.pack(side="left", fill="y", padx=(0, 12), pady=0)
        left.configure(width=340)

        right = ttk.Frame(main, style="Card.TFrame")
        right.pack(side="right", fill="both", expand=True)

        self._build_controls(left)
        self._build_plot(right)

        self._refresh_plot()

    # ---------- Controls ----------
    def _build_controls(self, parent: ttk.Frame):
        pad = {"padx": 14, "pady": 10}

        header = ttk.Label(parent, text="Налаштування", style="H1.TLabel")
        header.pack(anchor="w", **pad)

        # Room temp
        self.room_var = tk.DoubleVar(value=self.state.room)
        self._card_slider(parent, "Кімнатна температура (°C)", self.room_var, 15, 24, 0.1, self._on_change)

        # Outdoor temp
        self.tout_var = tk.DoubleVar(value=self.state.tout)
        self._card_slider(parent, "Зовнішня температура (°C)", self.tout_var, -20, 20, 1.0, self._on_change)

        # Slope
        self.slope_var = tk.DoubleVar(value=self.state.slope)
        slope_frame = self._card_slider(parent, "Опалювальна крива (s)", self.slope_var, SLOPE_MIN, SLOPE_MAX, 0.1, self._on_change)
        hint = ttk.Label(slope_frame, text="0.2…4.0 (Vaillant)", style="Card.TLabel")
        hint.pack(anchor="w", padx=8, pady=(0, 8))

        # Tmin / Tmax
        self.tmin_var = tk.DoubleVar(value=self.state.tmin)
        self.tmax_var = tk.DoubleVar(value=self.state.tmax)
        self._card_slider(parent, "Мін. подача, Tmin (°C)", self.tmin_var, 15, 40, 1.0, self._on_change)
        self._card_slider(parent, "Макс. подача, Tmax (°C)", self.tmax_var, 40, 90, 1.0, self._on_change)

        # Switches
        switches = ttk.Frame(parent, style="Card.TFrame")
        switches.pack(fill="x", **pad)

        self.show_all_var = tk.BooleanVar(value=self.state.show_all)
        self.show_grid_var = tk.BooleanVar(value=self.state.show_grid)
        self.show_182022_var = tk.BooleanVar(value=self.state.highlight_182022)

        ttk.Checkbutton(switches, text="Показати всі криві", variable=self.show_all_var, command=self._refresh_plot).pack(anchor="w", pady=(0,4))
        ttk.Checkbutton(switches, text="Сітка", variable=self.show_grid_var, command=self._refresh_plot).pack(anchor="w", pady=(0,4))
        ttk.Checkbutton(switches, text="Лінії 18/20/22 °C", variable=self.show_182022_var, command=self._refresh_plot).pack(anchor="w", pady=(0,4))

        # Current result card
        self.result_card = ttk.Frame(parent, style="Card.TFrame")
        self.result_card.pack(fill="x", padx=14, pady=10)
        ttk.Label(self.result_card, text="Розрахунок", style="Title.TLabel").pack(anchor="w", padx=8, pady=(8,0))
        self.result_lbl = ttk.Label(self.result_card, text="", style="Card.TLabel", font=("Segoe UI Semibold", 12))
        self.result_lbl.pack(anchor="w", padx=8, pady=(2,10))

        # Buttons
        actions = ttk.Frame(parent, style="Card.TFrame")
        actions.pack(fill="x", padx=14, pady=(4,14))

        ttk.Button(actions, text="Зберегти графік (PNG)", command=self._save_png).pack(side="left", padx=(0,8))
        ttk.Button(actions, text="Скинути", command=self._reset).pack(side="left")

        footer = ttk.Label(parent, text="Підказка: для теплої підлоги поставте Tmin≈25–28 °C, Tmax≈40–45 °C. "
                                        "Для радіаторів Tmin≈20–25 °C, Tmax≤75–80 °C (залежно від системи).",
                           style="Card.TLabel", wraplength=300, foreground=MUTED)
        footer.pack(anchor="w", padx=14, pady=(6,14))

    def _card_slider(self, parent, title, var, vmin, vmax, step, on_change):
        card = ttk.Frame(parent, style="Card.TFrame")
        card.pack(fill="x", padx=14, pady=(10,8))

        ttk.Label(card, text=title, style="Title.TLabel").pack(anchor="w", padx=8, pady=(8,0))
        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x", padx=8, pady=(4,10))

        sv = tk.StringVar(value=f"{var.get():.1f}")
        ent = ttk.Entry(row, textvariable=sv, width=8)
        ent.pack(side="right", padx=(8,0))
        ent.bind("<Return>", lambda e: self._sync_entry_to_var(sv, var, vmin, vmax, step, on_change))

        s = ttk.Scale(row, from_=vmin, to=vmax, orient="horizontal", variable=var,
                      command=lambda _evt: self._sync_var_to_entry(var, sv, step, on_change))
        s.pack(side="left", fill="x", expand=True)
        return card

    def _sync_entry_to_var(self, sv, var, vmin, vmax, step, on_change):
        try:
            val = float(sv.get())
            val = min(max(val, vmin), vmax)
            # snap to step
            if step >= 1:
                val = round(val / step) * step
            else:
                val = round(val / step) * step
            var.set(val)
            self._on_change()
        except ValueError:
            sv.set(f"{var.get():.1f}")

    def _sync_var_to_entry(self, var, sv, step, on_change):
        val = float(var.get())
        if step >= 1:
            val = round(val / step) * step
        else:
            # nicer rounding for decimals
            val = round(val, 2)
        sv.set(f"{val:.1f}")
        on_change()

    # ---------- Plot ----------
    def _build_plot(self, parent: ttk.Frame):
        self.fig = Figure(figsize=(6, 4.5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor("#0b1224")
        self.fig.patch.set_facecolor(CARD_BG)

        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=12, pady=12)

    def _refresh_plot(self):
        room = float(self.room_var.get())
        tout = float(self.tout_var.get())
        slope = float(self.slope_var.get())
        tmin = float(self.tmin_var.get())
        tmax = float(self.tmax_var.get())

        # recompute current point
        tf = tflow(room, tout, slope, tmin, tmax)
        self.result_lbl.config(text=f"Подача: {tf:.1f} °C   (s={slope:.1f}, "
                                    f"Tкімн={room:.1f} °C, Tзовн={tout:.1f} °C, "
                                    f"Tmin={tmin:.0f} °C, Tmax={tmax:.0f} °C)")

        # redraw
        self.ax.clear()

        # grid & axes
        self.ax.set_xlabel("Зовнішня температура, °C", color=FG)
        self.ax.set_ylabel("Температура подачі, °C", color=FG)
        self.ax.set_xlim(20, -20)   # like the Vaillant chart: warm → cold to the right
        self.ax.set_ylim(20, 90)

        if self.show_grid_var.get():
            self.ax.grid(True, which="both", alpha=0.25)

        # room setpoint guide lines (18/20/22 °C)
        if self.show_182022_var.get():
            for rt in (18, 20, 22):
                x = np.linspace(20, -20, 200)
                # plot reference curve with "slope=1" look but in our model it's just room line for s=0 baseline
                y = np.clip(rt + hc_from_slope(1.0) * (rt - x), 20, 90)
                self.ax.plot(x, y, linestyle="--", linewidth=0.8, alpha=0.35)

        # all curves (0.2…4.0) for current room setpoint
        x = np.linspace(20, -20, 400)
        if self.show_all_var.get():
            for s in np.round(np.linspace(SLOPE_MIN, SLOPE_MAX, 16), 1):
                y = np.clip(room + hc_from_slope(float(s)) * (room - x), float(self.tmin_var.get()), float(self.tmax_var.get()))
                self.ax.plot(x, y, linewidth=1.0, alpha=0.35)
                # annotate a few
                if s in (0.2, 0.6, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0):
                    # place label at x≈-18
                    xi = -18
                    yi = float(room + hc_from_slope(float(s)) * (room - xi))
                    yi = max(min(yi, float(self.tmax_var.get())), float(self.tmin_var.get()))
                    self.ax.text(xi, yi, f"{s:.1f}", fontsize=8, color=FG, alpha=0.7)

        # highlight selected slope
        y_sel = np.clip(room + hc_from_slope(slope) * (room - x), tmin, tmax)
        self.ax.plot(x, y_sel, linewidth=2.6, alpha=0.95)

        # current operating point
        self.ax.scatter([tout], [tf], s=60, zorder=5)

        # styling
        self.ax.tick_params(colors=FG)
        for spine in self.ax.spines.values():
            spine.set_color(MUTED)

        self.canvas.draw_idle()

    # ---------- Buttons ----------
    def _reset(self):
        self.room_var.set(20.0)
        self.tout_var.set(0.0)
        self.slope_var.set(1.0)
        self.tmin_var.set(25.0)
        self.tmax_var.set(90.0)
        self.show_all_var.set(True)
        self.show_grid_var.set(True)
        self.show_182022_var.set(True)
        self._refresh_plot()

    def _save_png(self):
        fpath = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG image", "*.png")],
            title="Зберегти графік як..."
        )
        if not fpath:
            return
        try:
            self.fig.savefig(fpath, dpi=150, bbox_inches="tight")
            messagebox.showinfo("Збережено", f"Графік збережено у файл:\n{fpath}")
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося зберегти файл:\n{e}")

    # ---------- Events ----------
    def _on_change(self, *_):
        self._refresh_plot()


if __name__ == "__main__":
    app = App()
    app.mainloop()
