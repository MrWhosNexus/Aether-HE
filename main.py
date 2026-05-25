import logging
import threading
import queue
import math
import time
from datetime import datetime
from tkinter import colorchooser

import customtkinter as ctk

import theme as T
from keyboard_widget import KeyboardDiagram, KB_ROWS
from aula_device import (
    AulaDevice, enumerate_interfaces, build_lighting, build_select,
    AULA_VID, AULA_PID,
)
from gamepad import VirtualGamepad, DEFAULT_DRIVING_MAP, MAX_TRAVEL_MM, EVDEV_AVAILABLE
import effects

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("aether.gui")
POLL_INTERVAL_S = 2.0

PROFILES = ["Profile Default", "Profile 1", "Profile 2", "Profile 3", "Profile 4"]
NAV = [("keymap", "⌨  Keymap"), ("lighting", "💡  Lighting"),
       ("actuation", "🎚  Actuation"), ("socd", "⚔  SOCD"), ("other", "⊞  Other")]
LIGHT_MODES = ["Wave", "Neon", "Radar", "Cross", "Breath", "Static", "Aurora", "Ripple",
               "Twinkle", "Reactive", "Striation", "Fireworks", "Auto Ripple", "Speed", "Custom"]
ACCENT_PRESETS = [("Violet", "#9d4edd"), ("Cyan", "#00f5ff"), ("Rose", "#ff3d6e"),
                  ("Green", "#39ff8a"), ("Amber", "#ffaa1f"), ("Blue", "#3b82f6")]


def parse_hex(text):
    cleaned = (text.replace(",", " ").replace("[", " ").replace("]", " ")
               .replace("0x", " ").replace("0X", " "))
    toks = cleaned.split()
    if len(toks) == 1 and len(toks[0]) > 2 and len(toks[0]) % 2 == 0:
        s = toks[0]; toks = [s[i:i + 2] for i in range(0, len(s), 2)]
    return [int(t, 16) for t in toks]


class AetherApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("AETHER HE // Keyboard Hub")
        self.geometry("1240x860")
        self.minsize(1120, 780)
        self.configure(fg_color=T.BG0)

        self.device = AulaDevice()
        self.connected = False
        self.stop_event = threading.Event()
        self.io_queue = queue.Queue()
        self._conn_buttons = []

        self.gamepad = None
        self.gp_thread = None
        self.gp_running = threading.Event()

        self.fx_engine = effects.EffectEngine(self._fx_send)
        self._fx_color = (0, 0, 0)

        self.section = "actuation"
        self.layer = "default"
        self.nav_buttons = {}
        self.panels = {}

        # lighting state
        self.palette = ["#9d4edd"]
        self.active_slot = 0
        self.bg_color = "#000000"
        self.per_key = {}
        self.pattern = "Static"
        self.brightness = ctk.IntVar(value=80)
        self.speed = ctk.IntVar(value=60)
        # actuation state
        self.actuation = ctk.DoubleVar(value=1.70)
        self.rt_enabled = ctk.BooleanVar(value=False)
        self.polling = ctk.IntVar(value=8)
        self.travel_test = ctk.BooleanVar(value=False)

        self._build_ui()
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.io_thread = threading.Thread(target=self._io_loop, daemon=True)
        self.monitor_thread.start(); self.io_thread.start()
        self._anim_tick()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # =============== shell ===============
    def _build_ui(self):
        self._build_topbar()
        self._build_nav()

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        # Hero card with keyboard
        hero = ctk.CTkFrame(scroll, fg_color=T.BG2, corner_radius=20,
                            border_width=1, border_color=T.BORDER)
        hero.pack(fill="x", pady=(8, 14))
        hb = ctk.CTkFrame(hero, fg_color="transparent")
        hb.pack(fill="x", padx=24, pady=(16, 0))
        self.breadcrumb = ctk.CTkLabel(hb, text="", text_color=T.S500,
                                       font=("JetBrains Mono", 10))
        self.breadcrumb.pack(side="left")
        self.badge_frame = ctk.CTkFrame(hb, fg_color="transparent")
        self.badge_frame.pack(side="right")

        body = ctk.CTkFrame(hero, fg_color="transparent")
        body.pack(fill="x", padx=24, pady=16)
        self.left_slot = ctk.CTkFrame(body, fg_color="transparent", width=120)
        self.left_slot.pack(side="left", anchor="n", padx=(0, 10))
        self.diagram = KeyboardDiagram(body, on_select=self._on_select)
        self.diagram.pack(side="left", expand=True)

        # Section content card
        self.section_card = ctk.CTkFrame(scroll, fg_color=T.BG2, corner_radius=20,
                                         border_width=1, border_color=T.BORDER)
        self.section_card.pack(fill="both", expand=True)
        self.panel_host = ctk.CTkFrame(self.section_card, fg_color="transparent")
        self.panel_host.pack(fill="both", expand=True, padx=22, pady=18)
        self._build_panels()
        self._switch("actuation")

    def _build_topbar(self):
        h = ctk.CTkFrame(self, fg_color=T.BG1, corner_radius=0, height=56)
        h.pack(fill="x"); h.pack_propagate(False)
        left = ctk.CTkFrame(h, fg_color="transparent"); left.pack(side="left", padx=20)
        ctk.CTkLabel(left, text="◆", width=30, height=30, corner_radius=8, fg_color=T.ACCENT,
                     text_color="#ffffff", font=("Arial", 15, "bold")).pack(side="left", padx=(0, 10))
        lk = ctk.CTkFrame(left, fg_color="transparent"); lk.pack(side="left")
        ctk.CTkLabel(lk, text="AETHER HE", font=("Rajdhani", 15, "bold"),
                     text_color="#ffffff").pack(anchor="w")
        ctk.CTkLabel(lk, text="KEYBOARD HUB", font=("JetBrains Mono", 8),
                     text_color=T.S500).pack(anchor="w")

        ctk.CTkLabel(left, text=" │ ", text_color=T.BORDER).pack(side="left", padx=8)
        self.profile_var = ctk.StringVar(value="Profile 1")
        ctk.CTkOptionMenu(left, values=PROFILES, variable=self.profile_var, width=160,
                          fg_color=T.SURFACE, button_color=T.SURFACE2, button_hover_color=T.BG3,
                          text_color=T.TEXT, font=("Rajdhani", 13),
                          command=lambda _: self._update_hero()).pack(side="left")

        right = ctk.CTkFrame(h, fg_color="transparent"); right.pack(side="right", padx=20)
        # status pill
        self.status_pill = ctk.CTkFrame(right, fg_color=T.SURFACE, corner_radius=18,
                                        border_width=1, border_color=T.BORDER)
        self.status_pill.pack(side="left", padx=(0, 8))
        self.status_dot = ctk.CTkLabel(self.status_pill, text="●", text_color=T.ROSE,
                                       font=("Arial", 11))
        self.status_dot.pack(side="left", padx=(10, 5), pady=4)
        ctk.CTkLabel(self.status_pill, text="WIN 60 HE", font=("Rajdhani", 12),
                     text_color=T.TEXT).pack(side="left")
        self.status_text = ctk.CTkLabel(self.status_pill, text="OFFLINE", font=("JetBrains Mono", 9),
                                        text_color=T.S500)
        self.status_text.pack(side="left", padx=(6, 12))

        ctk.CTkButton(right, text="◐ Theme", width=84, fg_color=T.SURFACE, hover_color=T.SURFACE2,
                      text_color=T.S300, border_width=1, border_color=T.BORDER,
                      font=("Rajdhani", 12), command=self._open_theme).pack(side="left", padx=4)
        self.pair_btn = ctk.CTkButton(right, text="⏻ Offline", width=110, fg_color=T.ACCENT_DIM,
                                      hover_color=T.SURFACE2, text_color=T.ACCENT,
                                      border_width=1, border_color=T.ACCENT,
                                      font=("Rajdhani", 12))
        self.pair_btn.pack(side="left", padx=4)

    def _build_nav(self):
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.pack(pady=14)
        seg = ctk.CTkFrame(wrap, fg_color=T.SURFACE, corner_radius=16,
                           border_width=1, border_color=T.BORDER)
        seg.pack()
        for sid, label in NAV:
            b = ctk.CTkButton(seg, text=label, width=120, height=34, corner_radius=11,
                              fg_color="transparent", hover_color=T.SURFACE2, text_color=T.S400,
                              font=("Rajdhani", 12, "bold"), command=lambda s=sid: self._switch(s))
            b.pack(side="left", padx=3, pady=3)
            self.nav_buttons[sid] = b

    def _on_select(self, keys):
        self._update_hero()

    def _switch(self, sid):
        self.section = sid
        for k, b in self.nav_buttons.items():
            if k == sid:
                b.configure(fg_color=T.ACCENT_DIM, text_color="#ffffff")
            else:
                b.configure(fg_color="transparent", text_color=T.S400)
        for k, p in self.panels.items():
            p.pack_forget()
        self.panels[sid].pack(fill="both", expand=True)
        mode = sid if sid in ("lighting", "actuation", "socd") else "keymap"
        self.diagram.set_mode(mode)
        self._rebuild_left_slot()
        if sid == "lighting":
            self._repaint_leds()
        self._update_hero()

    def _rebuild_left_slot(self):
        for w in self.left_slot.winfo_children():
            w.destroy()
        if self.section == "actuation":
            for label, cmd, primary in (
                ("Select All", self.diagram.select_all, False),
                ("Select Invert", self.diagram.invert, False),
                ("Deselect All", self.diagram.select_none, False),
                ("Reset Trigger", self._reset_trigger, True)):
                ctk.CTkButton(self.left_slot, text=label, width=112, height=30, corner_radius=6,
                              fg_color=(T.ACCENT_DIM if primary else T.SURFACE),
                              hover_color=T.SURFACE2,
                              text_color=(T.ACCENT if primary else T.S300),
                              border_width=1, border_color=(T.ACCENT if primary else T.BORDER),
                              font=("Rajdhani", 11), command=cmd).pack(pady=2)

    def _reset_trigger(self):
        self.actuation.set(1.70)
        self.diagram.set_actuation(1.70)
        if hasattr(self, "act_lbl"):
            self.act_lbl.configure(text="1.70")

    def _update_hero(self):
        prof = self.profile_var.get()
        sec = dict(NAV).get(self.section, "").split("  ")[-1]
        self.breadcrumb.configure(text=f"{prof}  ·  {sec}".upper())
        for w in self.badge_frame.winfo_children():
            w.destroy()
        if self.section == "actuation":
            stats = [("Actuation", f"{self.actuation.get():.2f}mm"),
                     ("Polling", f"{self.polling.get()}KHz"),
                     ("Selected", str(len(self.diagram.selected())))]
        elif self.section == "lighting":
            stats = [("Mode", self.pattern), ("Bright", f"{self.brightness.get()}%"),
                     ("Colors", str(len(self.palette)))]
        elif self.section == "socd":
            stats = [("Hotkey", "Fn+R-Shift")]
        else:
            stats = [("Keys", str(len(self.diagram.selected())))]
        for lab, val in stats:
            chip = ctk.CTkFrame(self.badge_frame, fg_color=T.SURFACE, corner_radius=8,
                                border_width=1, border_color=T.BORDER)
            chip.pack(side="left", padx=3)
            ctk.CTkLabel(chip, text=lab.upper(), font=("JetBrains Mono", 8),
                         text_color=T.S500).pack(side="left", padx=(8, 4), pady=3)
            ctk.CTkLabel(chip, text=val, font=("JetBrains Mono", 11),
                         text_color=T.TEXT).pack(side="left", padx=(0, 8))

    # =============== panels ===============
    def _build_panels(self):
        for sid, builder in (("keymap", self._panel_keymap), ("lighting", self._panel_lighting),
                             ("actuation", self._panel_actuation), ("socd", self._panel_socd),
                             ("other", self._panel_other)):
            f = ctk.CTkFrame(self.panel_host, fg_color="transparent")
            self.panels[sid] = f
            builder(f)

    def _h(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=("Rajdhani", 15, "bold"),
                     text_color=T.TEXT).pack(anchor="w")

    def _muted(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=("Inter", 11), text_color=T.S400,
                     wraplength=900, justify="left").pack(anchor="w", pady=(2, 10))

    def _slider_row(self, parent, label, var, frm, to, steps, unit="", cb=None):
        row = ctk.CTkFrame(parent, fg_color="transparent"); row.pack(fill="x", pady=4)
        head = ctk.CTkFrame(row, fg_color="transparent"); head.pack(fill="x")
        ctk.CTkLabel(head, text=label.upper(), font=("Rajdhani", 12, "bold"),
                     text_color=T.S300).pack(side="left")
        val = ctk.CTkLabel(head, text="", font=("JetBrains Mono", 13), text_color=T.ACCENT)
        val.pack(side="right")

        def on(v):
            val.configure(text=f"{float(v):.2f}{unit}" if steps < 200 and isinstance(var, ctk.DoubleVar)
                          else f"{int(float(v))}{unit}")
            if cb:
                cb(v)
        s = ctk.CTkSlider(row, from_=frm, to=to, number_of_steps=steps, variable=var,
                          button_color=T.ACCENT, progress_color=T.ACCENT_SOFT, command=on)
        s.pack(fill="x", pady=(4, 0)); on(var.get())
        return s

    # ---- Keymap ----
    def _panel_keymap(self, parent):
        self._sub_tabs(parent, ["Remap Key", "Key Combination", "Macro", "Advanced"])
        body = ctk.CTkFrame(parent, fg_color="transparent"); body.pack(fill="both", expand=True, pady=(4, 0))
        left = ctk.CTkFrame(body, fg_color="transparent", width=280); left.pack(side="left", anchor="n", padx=(0, 16))
        for i, t in enumerate(["Click a key on the keyboard above.",
                               "Pick the new mapping at right.",
                               "Or type it into the input below.",
                               "Hit Apply to flash."]):
            ctk.CTkLabel(left, text=f"0{i+1}.  {t}", font=("JetBrains Mono", 11),
                         text_color=T.S400, wraplength=260, justify="left").pack(anchor="w", pady=2)
        self.remap_target = ctk.StringVar(value="—")
        sel = ctk.CTkFrame(left, fg_color="transparent"); sel.pack(fill="x", pady=10)
        ctk.CTkLabel(sel, text="→", text_color=T.S500).pack(side="left", padx=6)
        ctk.CTkLabel(sel, textvariable=self.remap_target, font=("JetBrains Mono", 13),
                     text_color=T.ACCENT).pack(side="left")
        bb = ctk.CTkFrame(left, fg_color="transparent"); bb.pack(fill="x")
        ctk.CTkButton(bb, text="Default", fg_color=T.SURFACE, hover_color=T.SURFACE2,
                      text_color=T.S300, border_width=1, border_color=T.BORDER,
                      font=("Rajdhani", 11)).pack(side="left", expand=True, fill="x", padx=(0, 4))
        self._conn_btn(bb, text="Apply", fg_color=T.ACCENT_DIM, hover_color=T.SURFACE2,
                       text_color=T.ACCENT, border_width=1, border_color=T.ACCENT,
                       font=("Rajdhani", 11),
                       command=lambda: self._log(f"Remap → {self.remap_target.get()} (pending capture)")
                       ).pack(side="left", expand=True, fill="x", padx=(4, 0))

        grids = ctk.CTkScrollableFrame(body, fg_color="transparent", height=240)
        grids.pack(side="left", fill="both", expand=True)
        self._key_grid(grids, "Basic Keys", list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") +
                       ["1!", "2@", "3#", "$4", "5%", "6^", "7&", "8*", "9(", "0)"])
        self._key_grid(grids, "Extended Keys", ["Esc", "Tab", "Caps", "Back", "Enter", "Space",
                       "L-Ctrl", "R-Ctrl", "L-Shift", "R-Shift", "L-Alt", "R-Alt", "Menu",
                       "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12"])

    def _key_grid(self, parent, title, keys):
        ctk.CTkLabel(parent, text=title.upper(), font=("Rajdhani", 12, "bold"),
                     text_color=T.S300).pack(anchor="w", pady=(8, 4))
        grid = ctk.CTkFrame(parent, fg_color="transparent"); grid.pack(fill="x")
        cols = 12
        for c in range(cols):
            grid.grid_columnconfigure(c, weight=1)
        for i, k in enumerate(keys):
            ctk.CTkButton(grid, text=k, height=30, corner_radius=6, fg_color=T.SURFACE,
                          hover_color=T.SURFACE2, text_color=T.S300, border_width=1,
                          border_color=T.BORDER, font=("JetBrains Mono", 11),
                          command=lambda kk=k: self.remap_target.set(kk)
                          ).grid(row=i // cols, column=i % cols, sticky="ew", padx=2, pady=2)

    # ---- Actuation ----
    def _panel_actuation(self, parent):
        self._sub_tabs(parent, ["Travel", "Dead Band", "Switch", "Polling Rate", "Calibration"])
        body = ctk.CTkFrame(parent, fg_color="transparent"); body.pack(fill="both", expand=True, pady=(4, 0))
        # left switch/travel-test card
        lc = ctk.CTkFrame(body, fg_color=T.SURFACE, corner_radius=12, border_width=1,
                          border_color=T.BORDER, width=240)
        lc.pack(side="left", anchor="n", padx=(0, 16)); lc.pack_propagate(False)
        tt = ctk.CTkFrame(lc, fg_color="transparent"); tt.pack(fill="x", padx=14, pady=12)
        ctk.CTkLabel(tt, text="TRAVEL TEST", font=("Rajdhani", 11, "bold"),
                     text_color=T.S300).pack(side="left")
        ctk.CTkSwitch(tt, text="", variable=self.travel_test, width=40,
                      progress_color=T.ACCENT, command=self._update_hero).pack(side="right")
        ctk.CTkLabel(lc, text="◇\n\nmagnetic switch\n0–4.0mm travel", font=("JetBrains Mono", 11),
                     text_color=T.S500, justify="center").pack(pady=20)

        right = ctk.CTkFrame(body, fg_color=T.SURFACE, corner_radius=12, border_width=1,
                             border_color=T.BORDER)
        right.pack(side="left", fill="both", expand=True)
        inner = ctk.CTkFrame(right, fg_color="transparent"); inner.pack(fill="x", padx=18, pady=16)
        self._muted(inner, "Select keys on the keyboard above, then adjust their actuation point.")

        def act_cb(v):
            self.diagram.set_actuation(float(v)); self._update_hero()
        self._slider_row(inner, "Key Trigger Travel", self.actuation, 0.1, 4.0, 78, "mm", act_cb)

        rt = ctk.CTkCheckBox(inner, text="Rapid Trigger", variable=self.rt_enabled, fg_color=T.ACCENT,
                             font=("Rajdhani", 12, "bold"), text_color=T.TEXT)
        rt.pack(anchor="w", pady=(12, 4))
        self.rt_press = ctk.DoubleVar(value=0.05); self.rt_release = ctk.DoubleVar(value=0.05)
        rtbox = ctk.CTkFrame(inner, fg_color=T.BG1, corner_radius=8); rtbox.pack(fill="x", pady=4)
        self._slider_row(rtbox, "Press Sensitivity", self.rt_press, 0.05, 2.0, 39, "mm")
        self._slider_row(rtbox, "Release Sensitivity", self.rt_release, 0.05, 2.0, 39, "mm")

        ctk.CTkLabel(inner, text="POLLING RATE", font=("Rajdhani", 11, "bold"),
                     text_color=T.S300).pack(anchor="w", pady=(12, 4))
        pr = ctk.CTkFrame(inner, fg_color="transparent"); pr.pack(anchor="w")
        self.poll_btns = {}
        for p in (1, 2, 4, 8):
            b = ctk.CTkButton(pr, text=f"{p}KHz", width=70, height=32, corner_radius=6,
                              fg_color=T.SURFACE, hover_color=T.SURFACE2, text_color=T.S300,
                              border_width=1, border_color=T.BORDER, font=("Rajdhani", 12),
                              command=lambda pp=p: self._set_polling(pp))
            b.pack(side="left", padx=3); self.poll_btns[p] = b
        self._set_polling(8)

    def _set_polling(self, p):
        self.polling.set(p)
        for pp, b in self.poll_btns.items():
            if pp == p:
                b.configure(fg_color=T.ACCENT, text_color="#ffffff", border_color=T.ACCENT)
            else:
                b.configure(fg_color=T.SURFACE, text_color=T.S300, border_color=T.BORDER)
        self._update_hero()

    # ---- Lighting ----
    def _panel_lighting(self, parent):
        head = ctk.CTkFrame(parent, fg_color="transparent"); head.pack(fill="x")
        self._h(head, "Lighting")
        ctk.CTkLabel(head, text="RGB ENGINE · PER-KEY", font=("JetBrains Mono", 10),
                     text_color=T.S500).pack(side="left", padx=10)

        body = ctk.CTkFrame(parent, fg_color="transparent"); body.pack(fill="both", expand=True, pady=(8, 0))
        # LEFT: modes + sliders + bg
        left = ctk.CTkFrame(body, fg_color="transparent"); left.pack(side="left", fill="both", expand=True, padx=(0, 16))
        ctk.CTkLabel(left, text="LIGHT MODE", font=("Rajdhani", 11, "bold"),
                     text_color=T.S400).pack(anchor="w")
        mg = ctk.CTkFrame(left, fg_color="transparent"); mg.pack(fill="x", pady=(4, 8))
        for c in range(5):
            mg.grid_columnconfigure(c, weight=1)
        self.mode_btns = {}
        for i, m in enumerate(LIGHT_MODES):
            b = ctk.CTkButton(mg, text=m, height=30, corner_radius=8, fg_color=T.SURFACE,
                              hover_color=T.SURFACE2, text_color=T.S300, border_width=1,
                              border_color=T.BORDER, font=("Rajdhani", 11),
                              command=lambda mm=m: self._set_pattern(mm))
            b.grid(row=i // 5, column=i % 5, sticky="ew", padx=2, pady=2)
            self.mode_btns[m] = b
        self._set_pattern("Static")

        sl = ctk.CTkFrame(left, fg_color="transparent"); sl.pack(fill="x", pady=6)
        self._slider_row(sl, "Brightness", self.brightness, 0, 100, 100, "%",
                         lambda v: self._update_hero())
        self._slider_row(sl, "Speed", self.speed, 0, 100, 100, "%")

        bg = ctk.CTkFrame(left, fg_color=T.SURFACE, corner_radius=12, border_width=1, border_color=T.BORDER)
        bg.pack(fill="x", pady=6)
        bgr = ctk.CTkFrame(bg, fg_color="transparent"); bgr.pack(fill="x", padx=12, pady=10)
        ctk.CTkLabel(bgr, text="BACKGROUND COLOR", font=("Rajdhani", 11, "bold"),
                     text_color=T.S300).pack(side="left")
        self.bg_swatch = ctk.CTkButton(bgr, text="", width=44, height=24, corner_radius=6,
                                       fg_color=self.bg_color, hover_color=self.bg_color,
                                       command=self._pick_bg)
        self.bg_swatch.pack(side="right")

        # RIGHT: palette + per-key
        right = ctk.CTkFrame(body, fg_color="transparent"); right.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(right, text="EFFECT COLORS", font=("Rajdhani", 11, "bold"),
                     text_color=T.S300).pack(anchor="w")
        self.palette_row = ctk.CTkFrame(right, fg_color="transparent"); self.palette_row.pack(fill="x", pady=(4, 8))
        self._rebuild_palette()

        pk = ctk.CTkFrame(right, fg_color=T.SURFACE, corner_radius=12, border_width=1, border_color=T.BORDER)
        pk.pack(fill="x", pady=4)
        pki = ctk.CTkFrame(pk, fg_color="transparent"); pki.pack(fill="x", padx=12, pady=10)
        ctk.CTkLabel(pki, text="PER-KEY COLORS", font=("Rajdhani", 12, "bold"),
                     text_color=T.TEXT).pack(anchor="w")
        prow = ctk.CTkFrame(pki, fg_color="transparent"); prow.pack(fill="x", pady=6)
        ctk.CTkButton(prow, text="Select All", width=90, height=28, fg_color=T.SURFACE2,
                      hover_color=T.BG3, text_color=T.S300, font=("Rajdhani", 11),
                      command=self.diagram.select_all).pack(side="left", padx=(0, 4))
        ctk.CTkButton(prow, text="Clear", width=70, height=28, fg_color=T.SURFACE2,
                      hover_color=T.BG3, text_color=T.S300, font=("Rajdhani", 11),
                      command=self.diagram.select_none).pack(side="left")
        ab = ctk.CTkFrame(pki, fg_color="transparent"); ab.pack(fill="x", pady=(4, 0))
        self._conn_btn(ab, text="Paint Selected", fg_color=T.ACCENT, hover_color=T.ACCENT_SOFT,
                       text_color="#ffffff", font=("Rajdhani", 12, "bold"),
                       command=self._paint_selected).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ctk.CTkButton(ab, text="Reset", width=70, fg_color=T.SURFACE2, hover_color=T.BG3,
                      text_color=T.S300, font=("Rajdhani", 11),
                      command=self._reset_per_key).pack(side="left")
        # apply to hardware (global)
        self._conn_btn(right, text="⚡ Apply to Keyboard", fg_color=T.ACCENT_DIM,
                       hover_color=T.SURFACE2, text_color=T.ACCENT, border_width=1,
                       border_color=T.ACCENT, font=("Rajdhani", 12, "bold"),
                       command=self._apply_lighting).pack(fill="x", pady=(10, 0))

    def _set_pattern(self, m):
        self.pattern = m
        for mm, b in self.mode_btns.items():
            if mm == m:
                b.configure(fg_color=T.ACCENT, text_color="#ffffff", border_color=T.ACCENT)
            else:
                b.configure(fg_color=T.SURFACE, text_color=T.S300, border_color=T.BORDER)
        self._repaint_leds(); self._update_hero()

    def _rebuild_palette(self):
        for w in self.palette_row.winfo_children():
            w.destroy()
        for i, c in enumerate(self.palette):
            ring = T.ACCENT if i == self.active_slot else T.BORDER
            sw = ctk.CTkButton(self.palette_row, text=c.upper(), width=80, height=46, corner_radius=10,
                               fg_color=c, hover_color=c, text_color="#ffffff",
                               border_width=2, border_color=ring, font=("JetBrains Mono", 9),
                               command=lambda idx=i: self._set_slot(idx))
            sw.pack(side="left", padx=3)
            sw.bind("<Button-3>", lambda e, idx=i: self._edit_slot(idx))
        if len(self.palette) < 4:
            ctk.CTkButton(self.palette_row, text="+ Add", width=70, height=46, corner_radius=10,
                          fg_color="transparent", hover_color=T.SURFACE, text_color=T.S400,
                          border_width=2, border_color=T.BORDER, font=("Rajdhani", 11),
                          command=self._add_slot).pack(side="left", padx=3)

    def _set_slot(self, i):
        self.active_slot = i; self._rebuild_palette()

    def _edit_slot(self, i):
        rgb, hx = colorchooser.askcolor(color=self.palette[i], title="Effect color")
        if hx:
            self.palette[i] = hx; self._rebuild_palette(); self._repaint_leds()

    def _add_slot(self):
        seeds = ["#9d4edd", "#00f5ff", "#ff3d6e", "#ffaa1f"]
        self.palette.append(seeds[len(self.palette) % 4])
        self.active_slot = len(self.palette) - 1
        self._rebuild_palette(); self._update_hero()

    def _pick_bg(self):
        rgb, hx = colorchooser.askcolor(color=self.bg_color, title="Background color")
        if hx:
            self.bg_color = hx; self.bg_swatch.configure(fg_color=hx, hover_color=hx); self._repaint_leds()

    def _repaint_leds(self):
        if self.section != "lighting":
            return
        codes = [k for row in KB_ROWS for (_, _, k, _) in row]
        for idx, code in enumerate(codes):
            if code in self.per_key:
                self.diagram.set_key_color(code, self.per_key[code])
            elif self.pattern == "Static":
                self.diagram.set_key_color(code, self.palette[0])
            else:
                hit = (idx % 6 == 0) or len(self.palette) == 1
                self.diagram.set_key_color(code, self.palette[idx % len(self.palette)] if hit else self.bg_color)

    def _paint_selected(self):
        c = self.palette[self.active_slot]
        for code in self.diagram.selected():
            self.per_key[code] = c
        self._repaint_leds()
        self._log(f"Per-key paint {c} → {len(self.diagram.selected())} keys (preview; HW is global)")

    def _reset_per_key(self):
        for code in self.diagram.selected():
            self.per_key.pop(code, None)
        self._repaint_leds()

    def _apply_lighting(self):
        c = self.palette[0].lstrip("#")
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        bri = round(self.brightness.get() / 100 * 4)
        mode = 0 if self.pattern == "Static" else 1
        if mode:
            self.io_queue.put(("write", build_select(), None))
        self.io_queue.put(("write", build_lighting(r, g, b, mode=mode, brightness=bri,
                                                    speed=round(self.speed.get() / 100 * 10)), None))
        self._log(f"Lighting → RGB=({r},{g},{b}) mode={self.pattern} bright={bri}")

    # ---- SOCD ----
    def _panel_socd(self, parent):
        top = ctk.CTkFrame(parent, fg_color="transparent"); top.pack(fill="x")
        ctk.CTkLabel(top, text="SWITCH", font=("Rajdhani", 11, "bold"), text_color=T.S300).pack(side="left")
        ctk.CTkSwitch(top, text="", width=40, progress_color=T.ACCENT).pack(side="left", padx=6)
        ctk.CTkLabel(top, text="Hotkey: Fn + R-Shift", font=("JetBrains Mono", 11),
                     text_color=T.S400).pack(side="left", padx=10)
        self._conn_btn(top, text="Apply", width=90, fg_color=T.ACCENT, hover_color=T.ACCENT_SOFT,
                       text_color="#ffffff", font=("Rajdhani", 12, "bold"),
                       command=lambda: self._log(f"SOCD apply (pending capture)")).pack(side="right")

        body = ctk.CTkFrame(parent, fg_color="transparent"); body.pack(fill="both", expand=True, pady=12)
        center = ctk.CTkFrame(body, fg_color=T.SURFACE, corner_radius=12, border_width=1, border_color=T.BORDER)
        center.pack(side="left", fill="x", padx=(0, 16))
        ci = ctk.CTkFrame(center, fg_color="transparent"); ci.pack(padx=16, pady=14)
        pair = ctk.CTkFrame(ci, fg_color="transparent"); pair.pack()
        self.socd_k1 = ctk.CTkEntry(pair, width=70, justify="center", fg_color=T.BG1)
        self.socd_k1.insert(0, "A"); self.socd_k1.pack(side="left", padx=6)
        ctk.CTkLabel(pair, text="↔", text_color=T.S500).pack(side="left", padx=6)
        self.socd_k2 = ctk.CTkEntry(pair, width=70, justify="center", fg_color=T.BG1)
        self.socd_k2.insert(0, "D"); self.socd_k2.pack(side="left", padx=6)
        self.socd_mode = ctk.IntVar(value=1)
        mg = ctk.CTkFrame(ci, fg_color="transparent"); mg.pack(pady=10)
        for c in range(2):
            mg.grid_columnconfigure(c, weight=1)
        for m in (1, 2, 3, 4):
            ctk.CTkRadioButton(mg, text=f"Model {m}", variable=self.socd_mode, value=m,
                               fg_color=T.ACCENT, text_color=T.S300, font=("JetBrains Mono", 11)
                               ).grid(row=(m - 1) // 2, column=(m - 1) % 2, sticky="w", padx=8, pady=4)
        desc = ctk.CTkFrame(ci, fg_color=T.BG1, corner_radius=8); desc.pack(fill="x")
        for line in ("Model 1 · First press wins; second interrupted.",
                     "Model 2 · Key1 interrupts Key2.",
                     "Model 3 · Key2 interrupts Key1.",
                     "Model 4 · Later key wins (Snap Tap)."):
            ctk.CTkLabel(desc, text=line, font=("JetBrains Mono", 10), text_color=T.S400,
                         anchor="w").pack(fill="x", padx=10, pady=1)

    # ---- Other ----
    def _panel_other(self, parent):
        wrap = ctk.CTkFrame(parent, fg_color="transparent"); wrap.pack(fill="both", expand=True)
        col1 = ctk.CTkFrame(wrap, fg_color="transparent"); col1.pack(side="left", fill="both", expand=True, padx=(0, 12))
        self._h(col1, "Win Lock")
        for lab in ("Disable Windows key", "Disable Shift+Tab", "Disable Alt+Tab", "Disable Alt+F4"):
            ctk.CTkCheckBox(col1, text=lab, fg_color=T.ACCENT, text_color=T.S300,
                            font=("Inter", 12)).pack(anchor="w", pady=4)

        # Gamepad (our feature)
        self._h(col1, "Analog Gamepad")
        gst = "✅ uinput ready" if EVDEV_AVAILABLE else "❌ evdev missing"
        if EVDEV_AVAILABLE:
            try:
                VirtualGamepad().open().close()
            except Exception as ex:
                gst = f"⚠ {ex}"
        ctk.CTkLabel(col1, text=gst, font=("JetBrains Mono", 10), text_color=T.S400,
                     wraplength=420, justify="left").pack(anchor="w", pady=(0, 6))
        gr = ctk.CTkFrame(col1, fg_color="transparent"); gr.pack(anchor="w")
        self.gp_btn = ctk.CTkButton(gr, text="▶ Start Gamepad", fg_color=T.ACCENT_DIM,
                                    hover_color=T.SURFACE2, text_color=T.ACCENT, border_width=1,
                                    border_color=T.ACCENT, font=("Rajdhani", 12, "bold"),
                                    command=self._toggle_gamepad)
        self.gp_btn.pack(side="left", padx=(0, 8))
        self.gp_demo = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(gr, text="Demo", variable=self.gp_demo, progress_color=T.ACCENT).pack(side="left")

        # System / debug
        col2 = ctk.CTkFrame(wrap, fg_color="transparent"); col2.pack(side="left", fill="both", expand=True)
        self._h(col2, "System")
        ctk.CTkButton(col2, text="Re-scan interfaces", fg_color=T.SURFACE, hover_color=T.SURFACE2,
                      text_color=T.S300, font=("Rajdhani", 11),
                      command=self._refresh_interface_listing).pack(anchor="w", pady=4)
        self.hex_entry = ctk.CTkEntry(col2, fg_color=T.BG1, font=("JetBrains Mono", 11))
        self.hex_entry.insert(0, "01 07 00 00 00 0e 00 04 04 ff 00 00 ff 55")
        self.hex_entry.pack(fill="x", pady=4)
        self._conn_btn(col2, text="Send Raw", fg_color=T.ACCENT_DIM, hover_color=T.SURFACE2,
                       text_color=T.ACCENT, border_width=1, border_color=T.ACCENT,
                       font=("Rajdhani", 11), command=self._send_raw).pack(anchor="w")
        ctk.CTkLabel(col2, text="LOG", font=("Rajdhani", 11, "bold"), text_color=T.S300).pack(anchor="w", pady=(8, 2))
        self.log_box = ctk.CTkTextbox(col2, height=160, fg_color=T.BG1, font=("JetBrains Mono", 10))
        self.log_box.pack(fill="both", expand=True)
        self.iface_box = ctk.CTkTextbox(col2, height=70, fg_color=T.BG1, font=("JetBrains Mono", 10))
        self.iface_box.pack(fill="x", pady=(6, 0))
        self._refresh_interface_listing()

    # ---- shared ----
    def _sub_tabs(self, parent, tabs):
        bar = ctk.CTkFrame(parent, fg_color="transparent"); bar.pack(fill="x", pady=(0, 8))
        for i, t in enumerate(tabs):
            ctk.CTkLabel(bar, text=t.upper(), font=("Rajdhani", 12, "bold"),
                         text_color=(T.ACCENT if i == 0 else T.S400)).pack(side="left", padx=(0, 18))

    def _conn_btn(self, parent, **kw):
        b = ctk.CTkButton(parent, **kw)
        b.configure(state="disabled")
        self._conn_buttons.append(b)
        return b

    def _open_theme(self):
        win = ctk.CTkToplevel(self); win.title("Theme"); win.geometry("280x180")
        win.configure(fg_color=T.BG1)
        ctk.CTkLabel(win, text="ACCENT", font=("Rajdhani", 13, "bold"), text_color=T.TEXT).pack(pady=(14, 6))
        grid = ctk.CTkFrame(win, fg_color="transparent"); grid.pack()
        for name, hx in ACCENT_PRESETS:
            ctk.CTkButton(grid, text="", width=36, height=36, corner_radius=10, fg_color=hx,
                          hover_color=hx, command=lambda h=hx: self._apply_accent(h)).pack(side="left", padx=4)
        ctk.CTkButton(win, text="Custom…", fg_color=T.SURFACE, hover_color=T.SURFACE2,
                      command=self._accent_custom).pack(pady=12)

    def _accent_custom(self):
        rgb, hx = colorchooser.askcolor(color=T.ACCENT, title="Accent")
        if hx:
            self._apply_accent(hx)

    def _apply_accent(self, hx):
        T.ACCENT = hx
        T.ACCENT_SOFT = T.blend(hx, "#ffffff", 0.25)
        T.ACCENT_DIM = T.blend(T.BG0, hx, 0.22)
        # restyle the most visible accent surfaces
        self._switch(self.section)
        self._log(f"Accent → {hx}")

    # =============== device backend ===============
    def _set_status(self, connected, info=None):
        self.connected = connected
        if connected:
            self.after(0, lambda: self.status_dot.configure(text_color=T.EMERALD))
            self.after(0, lambda: self.status_text.configure(text="LINKED", text_color=T.EMERALD))
            self.after(0, lambda: self.pair_btn.configure(text="⏻ Connected", fg_color="#10341f",
                                                          text_color=T.EMERALD, border_color=T.EMERALD))
            self._set_buttons("normal")
        else:
            self.after(0, lambda: self.status_dot.configure(text_color=T.ROSE))
            self.after(0, lambda: self.status_text.configure(text="OFFLINE", text_color=T.S500))
            self.after(0, lambda: self.pair_btn.configure(text="⏻ Offline", fg_color=T.ACCENT_DIM,
                                                          text_color=T.ACCENT, border_color=T.ACCENT))
            self._set_buttons("disabled")

    def _set_buttons(self, state):
        for b in self._conn_buttons:
            self.after(0, lambda b=b: b.configure(state=state))

    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        if hasattr(self, "log_box"):
            self.after(0, lambda: (self.log_box.insert("end", f"[{ts}] {msg}\n"), self.log_box.see("end")))
        else:
            log.info(msg)

    def _refresh_interface_listing(self):
        if not hasattr(self, "iface_box"):
            return
        try:
            ifaces = enumerate_interfaces()
        except Exception as e:
            ifaces = []; self._log(f"enumerate failed: {e}")
        self.iface_box.delete("1.0", "end")
        if not ifaces:
            self.iface_box.insert("end", "No WIN60 HE interfaces.\n"); return
        for m in ifaces:
            self.iface_box.insert("end", f"iface {m.get('interface_number')}  "
                                  f"up=0x{m.get('usage_page', 0):04X}\n")

    def _monitor_loop(self):
        while not self.stop_event.is_set():
            try:
                if not self.device.is_open():
                    info = self.device.open()
                    self._log(f"Opened iface={info['interface_number']}")
                    self._set_status(True, info)
                    self.after(0, self._refresh_interface_listing)
            except Exception as e:
                if self.connected:
                    self._log(f"Lost device: {e}")
                self._set_status(False); self.device.close()
            self.stop_event.wait(POLL_INTERVAL_S)

    def _io_loop(self):
        while not self.stop_event.is_set():
            try:
                job = self.io_queue.get(timeout=0.25)
            except queue.Empty:
                continue
            kind, payload, _ = job
            try:
                if kind == "write":
                    self.device.write(payload)
            except Exception as e:
                self._log(f"I/O error: {e}"); self.device.close(); self._set_status(False)

    def _send_raw(self):
        try:
            p = parse_hex(self.hex_entry.get().strip())
            if len(p) < 64:
                p = p + [0] * (64 - len(p))
        except ValueError as e:
            self._log(f"parse error: {e}"); return
        self.io_queue.put(("write", p, None))
        self._log("Sent raw packet")

    # ---- gamepad ----
    def _toggle_gamepad(self):
        if self.gp_running.is_set():
            self.gp_running.clear()
            if self.gp_thread:
                self.gp_thread.join(timeout=1)
            if self.gamepad:
                self.gamepad.close(); self.gamepad = None
            self.gp_btn.configure(text="▶ Start Gamepad"); self._log("Gamepad stopped"); return
        try:
            self.gamepad = VirtualGamepad().open()
        except Exception as ex:
            self._log(f"Gamepad failed: {ex}"); return
        self.gp_running.set(); self.gp_btn.configure(text="■ Stop Gamepad")
        self._log("Gamepad started")
        self.gp_thread = threading.Thread(target=self._gamepad_loop, daemon=True); self.gp_thread.start()

    def _gamepad_loop(self):
        t0 = time.time()
        while self.gp_running.is_set() and not self.stop_event.is_set():
            t = time.time() - t0
            if self.gp_demo.get():
                depths = {"W": (math.sin(t * 1.5) * 0.5 + 0.5) * MAX_TRAVEL_MM,
                          "A": max(0.0, -math.sin(t)) * MAX_TRAVEL_MM,
                          "D": max(0.0, math.sin(t)) * MAX_TRAVEL_MM}
            else:
                depths = {}
            try:
                self.gamepad.update(depths)
            except Exception as ex:
                self._log(f"Gamepad error: {ex}"); break
            time.sleep(1 / 60)

    # ---- travel-test animation on the diagram ----
    def _anim_tick(self):
        if self.section == "actuation" and self.travel_test.get():
            t = time.time()
            for code in ("W", "A", "S", "D"):
                d = max(0.0, math.sin(t * 2 + hash(code) % 5)) * 3.2
                self.diagram.set_key_depth(code, d)
        self.after(80, self._anim_tick)

    def _on_close(self):
        self.stop_event.set(); self.gp_running.clear()
        if self.gp_thread:
            self.gp_thread.join(timeout=1)
        if self.gamepad:
            self.gamepad.close()
        self.monitor_thread.join(timeout=2); self.io_thread.join(timeout=2)
        self.device.close(); self.destroy()


if __name__ == "__main__":
    AetherApp().mainloop()
