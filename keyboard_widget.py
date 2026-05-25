"""WIN60 HE keyboard diagram — AETHER design translation.

60-column proportional grid (key widths in 0.25u increments, per the handoff's
keyboard.jsx). Supports modes: keymap / lighting / actuation / socd, fn-layer
labels, per-key selection, live travel depth, and per-key LED colors.
"""
import customtkinter as ctk

import theme as T

# [label, units(0.25u), code, fnLabel]
KB_ROWS = [
    [["Esc", 4, "Escape", "`~"], ["1!", 4, "1", "F1"], ["2@", 4, "2", "F2"], ["3#", 4, "3", "F3"],
     ["$4", 4, "4", "F4"], ["5%", 4, "5", "F5"], ["6^", 4, "6", "F6"], ["7&", 4, "7", "F7"],
     ["8*", 4, "8", "F8"], ["9(", 4, "9", "F9"], ["0)", 4, "0", "F10"], ["-_", 4, "Minus", "F11"],
     ["=+", 4, "Equal", "F12"], ["Back", 8, "Backspace", "Del"]],
    [["Tab", 6, "Tab", ""], ["Q", 4, "Q", "PrtSc"], ["W", 4, "W", "↑"], ["E", 4, "E", "End"],
     ["R", 4, "R", "PgUp"], ["T", 4, "T", "Home"], ["Y", 4, "Y", ""], ["U", 4, "U", ""],
     ["I", 4, "I", "Ins"], ["O", 4, "O", ""], ["P", 4, "P", "Pause"], ["{[", 4, "Lbr", "Prev"],
     ["}]", 4, "Rbr", "Next"], ["\\|", 6, "Bsl", "Play"]],
    [["Caps", 7, "Caps", ""], ["A", 4, "A", "←"], ["S", 4, "S", "↓"], ["D", 4, "D", "→"],
     ["F", 4, "F", ""], ["G", 4, "G", ""], ["H", 4, "H", ""], ["J", 4, "J", ""],
     ["K", 4, "K", "Vol−"], ["L", 4, "L", "Vol+"], [";:", 4, "Semi", "Mute"], ["'\"", 4, "Quot", ""],
     ["Enter", 9, "Enter", ""]],
    [["L-Shift", 9, "LShift", ""], ["Z", 4, "Z", ""], ["X", 4, "X", ""], ["C", 4, "C", "Calc"],
     ["V", 4, "V", ""], ["B", 4, "B", ""], ["N", 4, "N", ""], ["M", 4, "M", ""],
     [",<", 4, "Comma", "Brt−"], [".>", 4, "Dot", "Brt+"], ["/?", 4, "Slash", ""],
     ["R-Shift", 11, "RShift", ""]],
    [["L-Ctrl", 5, "LCtrl", ""], ["L-Win", 5, "LWin", "WinLk"], ["L-Alt", 5, "LAlt", ""],
     ["Space", 25, "Space", ""], ["R-Alt", 5, "RAlt", ""], ["Menu", 5, "Menu", ""],
     ["R-Ctrl", 5, "RCtrl", ""], ["Fn", 5, "Fn", "Fn"]],
]

# Map our gamepad/key names -> design codes for live-depth tinting.
ROW_H = 46


class KeyboardDiagram(ctk.CTkFrame):
    def __init__(self, master, on_select=None, **kw):
        super().__init__(master, fg_color=T.BG1, corner_radius=16,
                         border_width=1, border_color=T.BORDER, **kw)
        self._on_select = on_select
        self._mode = "keymap"
        self._layer = "default"
        self._buttons = {}     # code -> CTkButton
        self._meta = {}        # code -> (label, fn)
        self._selected = set()
        self._led = {}         # code -> hex or None
        self._depth = {}       # code -> mm
        self._actuation = 1.70
        self._build()

    def _build(self):
        board = ctk.CTkFrame(self, fg_color="transparent")
        board.pack(padx=16, pady=16)
        for ri, row in enumerate(KB_ROWS):
            rf = ctk.CTkFrame(board, fg_color="transparent")
            rf.pack(fill="x", pady=2)
            for c in range(60):
                rf.grid_columnconfigure(c, weight=1, uniform="kb")
            col = 0
            for label, units, code, fn in row:
                btn = ctk.CTkButton(
                    rf, text=label, height=ROW_H, corner_radius=6,
                    fg_color=T.SURFACE, hover_color=T.SURFACE2,
                    text_color=T.S300, border_width=1, border_color=T.BORDER,
                    font=("Inter", 11), command=lambda k=code: self._toggle(k),
                )
                btn.grid(row=0, column=col, columnspan=units, sticky="ew", padx=1)
                self._buttons[code] = btn
                self._meta[code] = (label, fn)
                self._led[code] = None
                self._depth[code] = 0.0
                col += units

    # ---- mode / layer ----
    def set_mode(self, mode):
        self._mode = mode
        for code in self._buttons:
            self._refresh(code)

    def set_layer(self, layer):
        self._layer = layer
        for code in self._buttons:
            self._refresh(code)

    def set_actuation(self, mm):
        self._actuation = mm
        if self._mode == "actuation":
            for code in self._buttons:
                self._refresh(code)

    # ---- selection ----
    def _toggle(self, code):
        if code in self._selected:
            self._selected.discard(code)
        else:
            self._selected.add(code)
        self._refresh(code)
        if self._on_select:
            self._on_select(self.selected())

    def selected(self):
        return set(self._selected)

    def select_all(self):
        self._selected = set(self._buttons)
        self._refresh_all_selection()

    def select_none(self):
        self._selected.clear()
        self._refresh_all_selection()

    def invert(self):
        self._selected = set(self._buttons) - self._selected
        self._refresh_all_selection()

    def _refresh_all_selection(self):
        for code in self._buttons:
            self._refresh(code)
        if self._on_select:
            self._on_select(self.selected())

    # ---- live state ----
    def set_key_color(self, code, hex_color):
        if code in self._buttons:
            self._led[code] = hex_color
            self._refresh(code)

    def set_all_color(self, hex_color):
        for code in self._buttons:
            self._led[code] = hex_color
        for code in self._buttons:
            self._refresh(code)

    def set_key_depth(self, code, mm):
        if code in self._buttons:
            self._depth[code] = mm
            self._refresh(code)

    # ---- rendering ----
    def _refresh(self, code):
        btn = self._buttons[code]
        label, fn = self._meta[code]
        selected = code in self._selected

        # label / text
        if self._layer == "fn" and fn:
            text, tcol = fn, T.ACCENT
        elif self._mode == "actuation":
            text, tcol = f"{label}\n{self._actuation:.2f}", T.S300
        else:
            text, tcol = label, T.S300

        # fill
        fill = T.SURFACE
        if self._mode == "lighting" and self._led.get(code):
            fill = self._led[code]
            tcol = T.TEXT if T.blend("#000000", fill, 1) else T.S300
        elif self._mode in ("actuation", "socd") and self._depth.get(code, 0) > 0.05:
            fill = T.blend(T.SURFACE, T.ACCENT, min(1.0, self._depth[code] / 4.0))

        # border (selection wins)
        if selected:
            border, bw = T.ACCENT, 2
        elif self._mode in ("actuation",) and self._depth.get(code, 0) >= self._actuation > 0:
            border, bw = T.ACCENT_SOFT, 2
        else:
            border, bw = T.BORDER, 1

        btn.configure(text=text, text_color=tcol, fg_color=fill,
                      border_color=border, border_width=bw)
