# Phase 7: Aether's Own Music Visualizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new host lighting effect `"music"`: Windows WASAPI loopback capture of the default audio output, FFT into 14 log-spaced bands (40 Hz-16 kHz) drawn as 14 column bars across the keyboard's 5 rows in the effect palette, with a background pulse on beats; a clear "unavailable" / "no audio device" state; < 60 ms audio-to-LED and < 5 % of one core at 60 fps.

**Architecture:** New module `music.py` holds everything audio: pure DSP and mapping functions over plain lists (testable with no numpy/soundcard), a `MusicSource` that owns ONE capture thread, and two small adapters (`NumpySpectrum`, `SoundcardBackend`) that import numpy/soundcard lazily, on the capture thread only. The effect engine (`effects.py`) gets a `music` attribute (the source), starts/stops it with the zones (so capture runs only while a `"music"` zone runs), and a `_g_music` generator that reads the source's lock-free snapshot each frame. `Api` owns the single `MusicSource`, hands it to every engine it builds, and adds a read-only `music_status()` bridge. The Lighting UI offers "Music" everywhere other effects are listed and shows availability/the device from `music_status()`.

**Tech Stack:** Python 3.12 stdlib (`math`, `threading`, `importlib.util`, `ctypes` for COM), numpy (FFT) and soundcard (WASAPI loopback) — both Windows-only, lazily imported; pytest; the existing React/Tailwind UI precompiled by `ui/runtime_src/build_runtime.py`.

**Spec:** `docs/superpowers/specs/2026-11-04-win60-roadmap-design.md` (section "Phase 7" and "Global constraints"). Also read `docs/superpowers/roadmap-status.md` (Phase 2: `HOST_FX_IDS`/`HOST_FX_FAST` guard tests; Phase 6: overlays compose over any host effect, the carrier and `_light_src`) and `CLAUDE.md`.

## Global Constraints

- Windows is the shipping target; nothing may break Linux (guard Windows-only code by `sys.platform`, degrade to "unavailable" elsewhere). On Linux the music effect reports "needs Windows" and idles.
- **No HID writes during development or tests. NEVER write to the keyboard, open HID, or run the app against it.** Fakes only. **Never open a real audio device in tests** (fake backend + fake spectrum only).
- **numpy and soundcard are NOT installed in the dev venv and there is NO NETWORK: never run `pip install`.** Everything must pass without them; the 3 numpy-only tests use `pytest.importorskip("numpy")` and SKIP tonight. With the deps absent the app shows Music as unavailable with a reason (no crash, other effects untouched).
- No push, merge into other branches, tag, release, or install. No network.
- Python: `C:\Users\yygbu\Aether-HE\venv-web\Scripts\python.exe` (written `<py>` below). Full suite: `<py> -m pytest -q -p no:cacheprovider` (1107 passed, 14 skipped at the start of this phase); must stay green at every commit.
- JSX changes need `<py> ui\runtime_src\build_runtime.py`; commit `ui/index_runtime.html` + only the `ui/runtime_src/build/*.js` files with real diffs (`git diff --ignore-cr-at-eol --stat`; `git checkout --` every build file that shows only in plain `git diff --stat`). `node --check` every touched build file.
- UI: edit `ui/runtime_src/src/*.jsx` / `ui/runtime_src/workspaces/*.jsx`, never `vendor/`. No raw-HTML sinks (`dangerouslySetInnerHTML`, `innerHTML`). Every `/*` must close (`tests/test_ui_sources.py`). Match the existing look (Tailwind classes, CSS vars `--text`, `--accent`, `--line`, `--ink`).
- New dependencies: `numpy>=1.26` and `soundcard>=0.4.3`, both `sys_platform == "win32"` (the only phase that adds any). Do NOT touch the Pillow line.
- **Privacy anti-goal:** Aether must never become a keylogger; never store/transmit key sequences, text, or per-keystroke timestamps. **Audio is processed in memory only, block by block; never recorded, saved, logged or sent.** `music_status()` reports state and the output device's name only.
- Bridge methods return `{"ok": bool, ...}` and never raise to JS (follow `Api._fail`).
- Do NOT touch `service/server.py`, `updater.py`, `Api.open_submission_url`, `.github/workflows/board-bot.yml`, or the Pillow pin.
- `git add` only the files you changed (other agents leave untracked files here). Never `git stash`. Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Working-tree sources are CRLF. If the Edit tool cannot match a multi-line `old_string`, apply the same replacement with a short Python snippet (`open(p, newline="")`, replace on `\n`-normalised text, convert back to `\r\n` if the file had them). New files may be LF.
- The user is asleep: "If it doesn't require my intervention write the code save items that require me for later." Queue user items; don't stop to ask.
- Context limit: if your context approaches ~400k tokens, stop: commit only what is green, append a status entry to `docs/superpowers/roadmap-status.md` saying exactly where you stopped, and return.

## Design decisions (resolved; do not re-decide)

1. **Capture.** `soundcard` WASAPI **loopback** of the Windows **default output** (`default_speaker()` -> `get_microphone(id, include_loopback=True)`), requested at **48 kHz**, read in **480-frame (10 ms) blocks**, channels averaged to mono. One daemon thread `aether-music`, owned by `music.MusicSource`. It runs ONLY between `MusicSource.start()` and `stop()`, and the engine calls those only around zones whose mode is `"music"` (decision 8). Every 1 s (`DEVICE_CHECK_S`) the thread re-reads the default output and re-opens when its id changed (headphones plugged, user switched output). No device / open failure / read error -> state `no_device`, close the stream, retry every 2 s (`RETRY_S`). soundcard and COM are touched ONLY on that thread: `SoundcardBackend.enter()` calls `CoInitializeEx(NULL, COINIT_MULTITHREADED)` then `import soundcard` (pywebview's UI thread is STA; soundcard needs MTA), `leave()` balances it. `music.availability()` uses `importlib.util.find_spec` only, so the UI thread never imports either package.
2. **FFT.** `N_FFT = 1024` (21.3 ms window, 46.9 Hz bins) over the newest 1024 mono samples (a ring buffer fed by every 480-frame block, so a fresh spectrum every 10 ms), Hann window, `rfft`, power `|X|^2 * (2 / sum(window))^2` (a full-scale sine's peak bin = 1 = 0 dBFS). Chosen over 2048 for latency: the window's centre of mass is ~10.7 ms behind the newest sample instead of ~21.3 ms; 1024 still gives every band at least one bin (validated below).
3. **Bands.** 14 geometric bands, edges `40 * 400 ** (k / 14)` Hz, k = 0..14 (ratio 1.534: 40, 61, 94, 144, 222, 340, 521, 800, 1227, 1882, 2887, 4429, 6795, 10424, 16000). A band takes the bins whose centre lies in `[f_lo, f_hi)`; a band narrower than a bin takes the bin nearest its geometric centre (never empty). Band power = `weight * sum(bin powers)` with `weight = band width / (bins * bin width)`, i.e. density times real bandwidth, so the 1-bin bass bands are not over-counted and pink-ish music reads roughly flat. At 1024/48k the bins are `(1,2) (2,3) (3,4) (4,5) (5,8) (8,12) (12,18) (18,27) (27,41) (41,62) (62,95) (95,146) (146,223) (223,342)`.
4. **Levels and auto-gain** (`BandAnalyzer`, per block). dB = `10*log10(p)` (p <= 1e-12, NaN or negative -> -120). Reference `ref = max(REF_FLOOR_DB (-45), loudest band now, ref - 4 dB/s * dt)`: jumps up instantly, falls 4 dB/s, never amplifies quieter than -45 dBFS. Level = `clamp((dB - (ref - 40)) / 40, 0, 1)` (40 dB shown). So the loudest band is 1.0, 20 dB under it 0.5; quiet music is lifted to full scale within seconds; -88 dBFS hiss stays dark. `dt` = samples / rate (not wall clock), so tests are deterministic.
5. **Beats** (energy flux, same per-block call). Flux = sum over the 6 lowest bands (40-521 Hz: kick/bass/snare body) of the positive dB rises since the previous block, on ABSOLUTE dB clamped at the display floor `ref - 40` (not on the auto-gained levels: the first kick also raises `ref`, which would hide it; the clamp keeps hiss/silence at zero flux). Beat when `flux >= 6 dB` AND `flux > mean + 1.5 * mad` (exponential running mean and mean absolute deviation, time constant 1 s, updated after the decision) AND >= 0.25 s since the last beat (<= 240 BPM). Each beat increments `beat_seq` in the snapshot.
6. **Hand-off to the engine (thread safety).** The capture thread publishes `self._pub = (levels tuple, beat_seq, monotonic time)` with one attribute assignment (atomic under the GIL); `MusicSource.snapshot()` reads it once and returns `MusicSnapshot(levels, beat_seq, live)` (namedtuple). No lock on the frame path. `live` = state is `listening`; levels are zeros when not live or older than `STALE_S = 0.25 s` (a stalled loopback, e.g. an older soundcard blocking in `record()` while nothing plays, makes the bars fall instead of freeze). `start()`/`stop()` are serialised by `MusicSource._life` and idempotent; each run has its own `threading.Event` (the engine's pattern), so a thread that outlives `stop()`'s 0.5 s join can never publish into or change the state of the next run.
7. **Generator `_g_music` (engine thread, per frame).** Targets = snapshot levels when live, else zeros. Per band: **instant attack**; release `level += (target - level) * (1 - exp(-dt / tau))`, `tau = 0.30 s` at speed 0 down to `0.08 s` at speed 1 (the speed slider; frame-rate independent), snapped to 0 below 0.004 so the tail ends. Mapping (`music.grid_layout`, built once per engine from KeyMap x/y): rows = distinct y values, `row` counted from the BOTTOM (space row 0, number row 4); keys have no width in the keymap, so a key spans from its x to the next key's x in its row, the row's last key to the board's right edge (largest x + median key pitch); the board width is cut into 14 equal columns and a key takes every column whose centre is in its span (Space averages 5), else the column under its centre. On the WIN60 the number and QWERTY rows cover all 14 columns left to right. Key fill `f = clamp(mean(level of its columns) * rows - row, 0, 1)`; colour `_scale(_lerp(bg_now, gradient(row / (rows - 1)), f), bright)` with the palette as a NON-looping bottom-to-top gradient. Beat pulse: a changed `beat_seq` (not the first one seen) sets pulse = 1, decaying `exp(-dt / 0.15 s)`; `bg_now = lerp(bg, palette[0], 0.45 * pulse)`. **No audio** (no source, deps missing, no device, error): the bottom row breathes `0.15 * palette[0]` over 3 s, everything else is the background — the "graceful no audio device" state; the UI text says why.
8. **Lifecycle lives in the engine**, because every path that stops lighting goes through it (`stop_multicolor`, `disconnect`, link loss, `select_board`, the Phase 6 carrier, a firmware mode): `start_zones` calls the new `_halt()` (old `stop()` body) then `_music_power(any zone mode == "music")`; `stop()` = `_halt()` + `_music_power(False)`; a send failure that ends the current run also powers music off. So a palette/speed edit (UI restarts the effect) keeps the capture open; switching to any other effect or stopping closes it. `_music_power` swallows exceptions (audio trouble never breaks lighting).
9. **Not press-reactive.** `"music"` is NOT added to `effects.PRESS_REACTIVE` (no LiveReader is attached for it; `_ensure_reactive(["music"])` releases owner "reactive" like any ambient effect). Therefore it is NOT in `HOST_FX_FAST` either: `tests/test_pressure_ui_sources.py` pins `HOST_FX_FAST == PRESS_REACTIVE`. It IS in `HOST_FX_IDS` (pinned `== engine generators`) and must be registered in `_gens` in the same commit as that JSX change (Task 6).
10. **Overlays (Phase 6).** Nothing to wire: `engine.overlay.apply(frame, now)` runs after the generators, so CPU/RAM/GPU/Pomodoro rows draw over the bars; `_overlay_sync` sees the engine running and starts no carrier. Expected look: an overlay row replaces the bars on that row.
11. **Availability + UI.** `music.availability()` -> `(False, "Music visualizer needs Windows (WASAPI loopback capture).")` off Windows, `(False, "Music visualizer needs the numpy and soundcard packages (not installed).")` (or the one missing package) on Windows without the deps, else `(True, None)`. Bridge `Api.music_status()` -> `{ok, available, reason, state, device}`, state `off|starting|listening|no_device|error|unavailable`, reason `"No audio output device found."` for no_device and `"Audio capture failed: <error>"` for error. The effect is still startable when unavailable (tray/dashboard grids may pick it) and simply idles. Lighting > Mode Picker: Music tile disabled (opacity 0.4, `title` = reason) when `available === false`; when Music is selected, one text line `data-music-note` under the grid: the reason, "Listening to <device>. Audio is analysed in memory only, never recorded.", "Starting audio capture…", or "Follows this PC's default audio output while the keyboard is connected." `music_status` is polled once on mount and every 2 s only while Music is selected. Tray (`modeGridFor` via `tray_sync`) and Dashboard quick switch derive from `LIGHT_MODES`: no change there. Preview kind `"wave"`; icon `♫`.
12. **Latency budget (< 60 ms audio->LED).** WASAPI shared-mode loopback packet ~10 ms + block 10 ms + window centre of mass 10.7 ms + engine frame wait <= 16.7 ms (avg 8.3) + one diff-sent cmd-9 frame ~5-8 ms ≈ 45-55 ms worst case, ~35-40 ms typical. Instant attack adds nothing. Measured on the user's PC in the hardware checks.
13. **CPU budget (< 5 % of one core).** Measured during planning (dev PC): `NumpySpectrum` + `BandAnalyzer` = 0.03 ms per 10 ms block (0.3 % of a core, numpy run from the system Python since the venv has none); `_g_music` on the 61-key WIN60 = 0.055 ms per frame (0.33 % at 60 fps); soundcard's per-block cffi copy is small. The frame streaming itself is the same as any host effect. Tests pin generous ceilings (< 1 ms per analyzer block, < 4 ms per frame).

## Review Focus

- **Nothing is playing** (WASAPI loopback delivers no packets; soundcard either returns zero blocks or blocks in `record()`): bars must fall to dark, nothing freezes lit, `stop()` returns promptly. Tests: Task 3 `test_snapshot_goes_dark_when_capture_stalls`, `test_stop_returns_promptly_and_the_thread_ends`; Task 4 `test_attack_is_instant_and_release_follows_the_speed_slider` (dark within 2 s).
- **Default output changes or disappears mid-song** (headphones plugged, USB DAC unplugged, output disabled): re-acquire within ~1 s, report `no_device`, recover when a device returns. Tests: Task 3 `test_a_changed_default_output_is_re_acquired`, `test_a_read_error_closes_the_stream_and_retries`, `test_no_output_device_is_reported_and_picked_up_when_one_appears`.
- **numpy/soundcard missing, or Linux**: no crash, no thread, the tile says why, the effect idles if chosen from the tray, other effects unaffected. Tests: Task 2 availability tests; Task 3 `test_missing_dependencies_mean_no_thread_and_a_reason`, `test_a_failing_backend_reports_an_error_and_never_raises`; Task 4 `test_no_audio_breathes_the_bottom_row_only`; Task 5 `test_missing_dependencies_still_run_the_effect_and_say_why`; Task 6 `test_mode_picker_shows_music_availability_without_hiding_it`.
- **Capture must never run unless Music is on** (privacy + CPU): other effects, a switch away, a dead stream, stop. Tests: Task 4 lifecycle tests; Task 5 `test_other_effects_never_open_the_audio_device`, `test_switching_from_music_to_another_effect_stops_listening`.
- **Palette/speed edits while Music runs** (the UI restarts the effect on every change): the device must not be re-opened each time. Test: Task 4 `test_restarting_music_keeps_the_capture_running`.

## File Structure

- Create `music.py`: constants; `band_edges`, `band_bins`, `band_powers`, `BandAnalyzer` (Task 1); `grid_layout`, `availability` (Task 2); `NumpySpectrum`, `SoundcardBackend`, `MusicSnapshot`, `ZERO_LEVELS`, `MusicSource` (Task 3).
- Modify `effects.py`: `import music`; `MUSIC_*` constants, `_gradient`; engine `music`, `_music_lay`, `_halt`, `_music_power`, `_music_map`, `_g_music` (Task 4); `_gens["music"]` (Task 6).
- Modify `app_web.py`: `import music`; `Api._music`, `_music_attach`, `music_status` (Task 5).
- Modify `requirements.txt`, `AetherHE.spec` (Task 3); `flatpak/io.github.mrwhosnexus.AetherHE.yml` cp list (Task 4).
- Modify `ui/runtime_src/workspaces/lighting.jsx`, `ui/runtime_src/src/sections.jsx`; regenerated `ui/index_runtime.html`, `ui/runtime_src/build/ws_lighting.js`, `ui/runtime_src/build/sections.js` (Task 6).
- Modify `CLAUDE.md` (Task 7).
- Tests (all new): `tests/test_music_dsp.py` (12), `tests/test_music_layout.py` (11), `tests/test_music_source.py` (10 + 3 skipped without numpy), `tests/test_music_packaging.py` (4), `tests/test_music_effect.py` (18), `tests/test_music_api.py` (8), `tests/test_music_ui_sources.py` (5). Total **68 passed + 3 skipped -> expect 1175 passed, 17 skipped.** (All code and tests below were prototyped against this tree: full suite 1175 passed / 17 skipped, `node --check` ok; the 3 numpy tests' assertions were checked with numpy from the system Python 3.12; then everything was reverted.)

---

### Task 1: `music.py` band maths and the analyzer

**Files:**
- Create: `music.py`
- Test: `tests/test_music_dsp.py` (create)

**Interfaces:**
- Produces: constants `N_BANDS = 14`, `F_LO = 40.0`, `F_HI = 16000.0`, `RATE = 48000`, `HOP = 480`, `N_FFT = 1024`, `RANGE_DB = 40.0`, `REF_FLOOR_DB = -45.0`, `REF_RELEASE_DB_S = 4.0`, `EPS = 1e-12`, `BEAT_BANDS = 6`, `BEAT_K = 1.5`, `BEAT_MIN_FLUX_DB = 6.0`, `BEAT_MIN_INTERVAL_S = 0.25`, `BEAT_STATS_TAU_S = 1.0`, `STALE_S = 0.25`, `DEVICE_CHECK_S = 1.0`, `RETRY_S = 2.0`, `MSG_NO_DEVICE`; `band_edges(n=14, lo=40.0, hi=16000.0) -> list[float]` (n+1 edges); `band_bins(n_fft: int, rate: int, edges) -> list[tuple[int, int, float]]` (`(lo, hi, weight)`, bins `lo..hi-1`); `band_powers(power: Sequence[float], bins) -> list[float]`; `BandAnalyzer(n_bands=14).feed(powers: Sequence[float], dt: float) -> tuple[list[float], bool]` (levels 0..1, beat).

- [ ] **Step 1: Write the failing tests** — `tests/test_music_dsp.py`:

```python
"""Phase 7 music visualizer, pure DSP: band edges/bins, band powers, the
BandAnalyzer (dB, auto-gain, energy-flux beats). Plain lists only: no numpy,
no soundcard, no audio device."""
import math
import random

import pytest

import music


def _p(db):
    """dBFS -> power."""
    return 10.0 ** (db / 10.0)


# ------------------------------------------------------------ band edges ----
def test_fourteen_log_spaced_bands_from_40_hz_to_16_khz():
    e = music.band_edges()
    assert len(e) == 15
    assert e[0] == pytest.approx(40.0) and e[-1] == pytest.approx(16000.0)
    ratios = [b / a for a, b in zip(e, e[1:])]
    assert all(r == pytest.approx(ratios[0]) for r in ratios)
    assert ratios[0] == pytest.approx(400.0 ** (1 / 14))


def test_bins_cover_every_band_at_the_shipping_fft_size():
    bins = music.band_bins(music.N_FFT, music.RATE, music.band_edges())
    assert len(bins) == 14
    assert bins[0][:2] == (1, 2)                  # 46.9 Hz bin is the 40-61 Hz band
    for lo, hi, w in bins:
        assert 1 <= lo < hi <= music.N_FFT // 2 + 1
        assert w > 0
    assert [b[0] for b in bins] == sorted(b[0] for b in bins)


def test_a_band_narrower_than_a_bin_gets_the_nearest_bin():
    bins = music.band_bins(256, 48000, music.band_edges())   # 187.5 Hz bins
    for lo, hi, _ in bins:
        assert hi - lo >= 1 and lo >= 1
    assert bins[0][:2] == (1, 2)


def test_band_powers_weight_the_bin_sum():
    power = [0.0, 1.0, 2.0, 3.0, 4.0]
    assert music.band_powers(power, [(1, 3, 0.5), (3, 5, 2.0)]) == [1.5, 14.0]


# ------------------------------------------------------------- analyzer ----
def test_levels_are_db_under_the_loudest_band():
    an = music.BandAnalyzer(3)
    lv, _ = an.feed([_p(-10), _p(-30), _p(-50)], 0.01)
    assert lv[0] == pytest.approx(1.0)
    assert lv[1] == pytest.approx(0.5)
    assert lv[2] == pytest.approx(0.0)


def test_silence_and_garbage_powers_are_zero_not_nan():
    an = music.BandAnalyzer(4)
    for _ in range(50):
        lv, beat = an.feed([0.0, -1.0, float("nan"), 0.0], 0.01)
        assert lv == [0.0, 0.0, 0.0, 0.0] and beat is False
    assert an.ref == music.REF_FLOOR_DB


def test_auto_gain_lifts_quiet_music_to_full_scale():
    loud = [_p(-10), _p(-25), _p(-40)]
    quiet = [_p(-40), _p(-55), _p(-70)]          # same shape, 30 dB down
    an = music.BandAnalyzer(3)
    for _ in range(100):
        an.feed(loud, 0.01)
    lv, _ = an.feed(quiet, 0.01)
    assert lv[0] < 0.3                           # right after the drop: dim
    for _ in range(800):                         # 8 s at the 4 dB/s release
        lv, _ = an.feed(quiet, 0.01)
    assert lv[0] == pytest.approx(1.0)
    assert lv[1] == pytest.approx(0.625)


def test_auto_gain_never_amplifies_below_the_floor():
    an = music.BandAnalyzer(2)
    for _ in range(2000):
        lv, _ = an.feed([_p(-88), _p(-95)], 0.01)
    assert an.ref == music.REF_FLOOR_DB
    assert lv == [0.0, 0.0]                      # -88 dBFS hiss stays dark


def _kick_track(kicks, blocks=300, n=14):
    """Steady -30 dBFS on every band; a kick lifts the low six to -10 dBFS and
    decays 4 dB per 10 ms block."""
    out = []
    since = None
    for k in range(blocks):
        if k in kicks:
            since = 0
        db = [-30.0] * n
        if since is not None:
            low = max(-30.0, -10.0 - 4.0 * since)
            for b in range(6):
                db[b] = low
            since += 1
        out.append([_p(d) for d in db])
    return out


def test_every_kick_at_120_bpm_is_a_beat():
    kicks = {25, 75, 125, 175, 225, 275}
    an = music.BandAnalyzer()
    beats = [k for k, pw in enumerate(_kick_track(kicks)) if an.feed(pw, 0.01)[1]]
    assert beats == sorted(kicks)


def test_steady_or_slightly_noisy_music_has_no_beats():
    rng = random.Random(7)
    an = music.BandAnalyzer()
    for _ in range(500):
        db = [-30.0 + rng.uniform(-0.5, 0.5) for _ in range(14)]
        assert an.feed([_p(d) for d in db], 0.01)[1] is False


def test_beats_are_at_most_one_per_quarter_second():
    kicks = set(range(10, 300, 10))              # a kick every 100 ms
    an = music.BandAnalyzer()
    beats = [k for k, pw in enumerate(_kick_track(kicks)) if an.feed(pw, 0.01)[1]]
    assert beats and all(b - a >= 25 for a, b in zip(beats, beats[1:]))


def test_analyzer_cost_is_tiny():
    import time
    an = music.BandAnalyzer()
    track = _kick_track({25, 75}, blocks=100)
    t0 = time.perf_counter()
    for pw in track:
        an.feed(pw, 0.01)
    per_block = (time.perf_counter() - t0) / len(track)
    assert per_block < 0.001                     # 100 blocks/s -> < 10 % of a core worst case
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_music_dsp.py -q -p no:cacheprovider`
Expected: collection ERROR `ModuleNotFoundError: No module named 'music'`.

- [ ] **Step 3: Create `music.py`** with this header, band maths and analyzer (the module's later sections are added by Tasks 2 and 3; the full import block goes in now):

```python
"""Phase 7 music visualizer: system audio -> 14 band levels + beats.

Pipeline (all on one capture thread, only while the "music" effect runs):
  WASAPI loopback of the default output (soundcard) -> 480-frame blocks at
  48 kHz -> 1024-point Hann FFT (numpy) -> 14 log-spaced band powers
  (40 Hz-16 kHz) -> BandAnalyzer (dB, auto-gain, energy-flux beats) ->
  an immutable snapshot the effect engine reads lock-free each frame.

The DSP and keyboard-mapping maths are pure functions over plain sequences so
they are testable without numpy or soundcard. Both packages are imported
lazily, inside the capture thread only, and only on Windows; without them the
effect reports itself unavailable. PRIVACY: audio is processed in memory only,
block by block; nothing is recorded, stored or sent anywhere.
"""
import importlib.util
import logging
import math
import sys
import threading
import time
from collections import namedtuple

log = logging.getLogger("aether.music")

N_BANDS = 14
F_LO, F_HI = 40.0, 16000.0
RATE = 48000                 # requested loopback rate (WASAPI converts)
HOP = 480                    # 10 ms capture blocks
N_FFT = 1024                 # 21.3 ms window, 46.9 Hz bins
RANGE_DB = 40.0              # dynamic range shown on the bars
REF_FLOOR_DB = -45.0         # auto-gain never amplifies past this (dBFS)
REF_RELEASE_DB_S = 4.0       # auto-gain reference falls this fast
EPS = 1e-12
BEAT_BANDS = 6               # energy flux over 40-520 Hz (kick/snare body)
BEAT_K = 1.5                 # threshold = mean + K * mean abs deviation
BEAT_MIN_FLUX_DB = 6.0
BEAT_MIN_INTERVAL_S = 0.25   # <= 240 BPM
BEAT_STATS_TAU_S = 1.0
STALE_S = 0.25               # snapshot older than this -> bars fall
DEVICE_CHECK_S = 1.0         # default-output change poll
RETRY_S = 2.0                # retry after no device / a failed open

MSG_NO_DEVICE = "No audio output device found."


# ------------------------------------------------------------ band maths ----
def band_edges(n=N_BANDS, lo=F_LO, hi=F_HI):
    """n + 1 geometric (log-spaced) band edges in Hz from lo to hi."""
    return [lo * (hi / lo) ** (k / n) for k in range(n + 1)]


def band_bins(n_fft, rate, edges):
    """[(lo, hi, weight)] per band: rfft bins lo..hi-1 whose centre frequency
    falls in [f_lo, f_hi). A band narrower than one bin gets the bin nearest
    its geometric centre. weight = band width / covered width, so a band's
    power is a density times its real bandwidth (single-bin bass bands are not
    over-counted)."""
    df = rate / float(n_fft)
    top = n_fft // 2
    out = []
    for f_lo, f_hi in zip(edges, edges[1:]):
        lo = max(1, min(top, int(math.ceil(f_lo / df))))
        hi = max(1, min(top + 1, int(math.ceil(f_hi / df))))
        if hi <= lo:
            lo = max(1, min(top, int(round(math.sqrt(f_lo * f_hi) / df))))
            hi = lo + 1
        out.append((lo, hi, (f_hi - f_lo) / (df * (hi - lo))))
    return out


def band_powers(power, bins):
    """Pure reference of what NumpySpectrum computes: weight * sum of the
    power spectrum over each band's bins."""
    return [w * sum(power[lo:hi]) for lo, hi, w in bins]


def _db(p):
    if not p > EPS:              # 0, negative, NaN, denormal hiss
        return 10.0 * math.log10(EPS)
    return 10.0 * math.log10(p)


class BandAnalyzer:
    """Band powers -> (levels 0..1, beat). Levels are dB under an auto-gain
    reference that jumps up to the loudest band instantly and falls
    REF_RELEASE_DB_S, never below REF_FLOOR_DB, showing RANGE_DB of range.
    A beat is a jump in the low-band energy flux (sum of dB rises over the
    BEAT_BANDS lowest bands) above an adaptive threshold (running mean +
    BEAT_K * mean absolute deviation, time constant BEAT_STATS_TAU_S), at
    least BEAT_MIN_FLUX_DB, at most one per BEAT_MIN_INTERVAL_S."""

    def __init__(self, n_bands=N_BANDS):
        self.n = n_bands
        self.ref = REF_FLOOR_DB
        self.prev = None
        self.mean = 0.0
        self.dev = 0.0
        self.since_beat = 1e9

    def feed(self, powers, dt):
        db = [_db(p) for p in powers]
        dt = max(0.0, float(dt))
        self.ref = max(REF_FLOOR_DB, max(db), self.ref - REF_RELEASE_DB_S * dt)
        lo = self.ref - RANGE_DB
        levels = [min(1.0, max(0.0, (d - lo) / RANGE_DB)) for d in db]
        # Flux on ABSOLUTE dB (not the auto-gained levels: a gain jump on the
        # first kick would hide it), clamped at the display floor so hiss and
        # silence never count.
        low = [max(d, lo) for d in db[:BEAT_BANDS]]
        prev = self.prev
        self.prev = low
        flux = 0.0
        if prev is not None:
            for d, q in zip(low, prev):
                if d > q:
                    flux += d - q
        self.since_beat += dt
        beat = (flux >= BEAT_MIN_FLUX_DB and flux > self.mean + BEAT_K * self.dev
                and self.since_beat >= BEAT_MIN_INTERVAL_S)
        if beat:
            self.since_beat = 0.0
        a = 1.0 - math.exp(-dt / BEAT_STATS_TAU_S) if dt > 0 else 0.0
        self.mean += a * (flux - self.mean)
        self.dev += a * (abs(flux - self.mean) - self.dev)
        return levels, beat
```

- [ ] **Step 4: Run the tests**

Run: `<py> -m pytest tests/test_music_dsp.py -q -p no:cacheprovider`
Expected: `12 passed`.

- [ ] **Step 5: Commit**

```bash
git add music.py tests/test_music_dsp.py
git commit -m "feat(music): log-spaced bands, auto-gain levels and energy-flux beats" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Keyboard grid mapping and availability

**Files:**
- Modify: `music.py` (append after `BandAnalyzer`)
- Test: `tests/test_music_layout.py` (create)

**Interfaces:**
- Consumes: `N_BANDS` (Task 1).
- Produces: `grid_layout(pos: dict[int, tuple[float, float]], n_bands=14) -> dict[int, tuple[tuple[int, ...], int, int]]` (`{idx: (bands, row_from_bottom, n_rows)}`; `{}` for no keys); `availability(platform: str | None = None, find_spec=None) -> tuple[bool, str | None]` (exact reason strings in Design decision 11; never imports the packages).

- [ ] **Step 1: Write the failing tests** — `tests/test_music_layout.py`:

```python
"""Phase 7: 14 bands -> keyboard columns (KeyMap x/y), and the dependency /
platform availability check. Pure: no numpy, no soundcard, no device."""
import device_state
import music


def _layout():
    km = device_state.KeyMap()
    pos = {i: (e["x"], e["y"]) for i, e in km.by_index.items()}
    return km, music.grid_layout(pos)


def _at(km, lay, code):
    return lay[km.index_of_code[code]]


def test_every_win60_key_is_mapped_onto_five_rows():
    km, lay = _layout()
    assert set(lay) == set(km.by_index)
    assert {m[2] for m in lay.values()} == {5}
    assert {m[1] for m in lay.values()} == {0, 1, 2, 3, 4}
    for bands, row, _ in lay.values():
        assert bands and all(0 <= b < 14 for b in bands)


def test_rows_count_from_the_bottom():
    km, lay = _layout()
    assert _at(km, lay, "Space")[1] == 0
    assert _at(km, lay, "Escape")[1] == 4
    assert _at(km, lay, "Q")[1] == 3


def test_number_and_qwerty_rows_cover_all_fourteen_columns_left_to_right():
    km, lay = _layout()
    for first, last in (("Escape", "Backspace"), ("Tab", "Bsl")):
        row = _at(km, lay, first)[1]
        keys = sorted((km.by_index[i]["x"], lay[i][0]) for i in lay if lay[i][1] == row)
        covered = set(b for _, bands in keys for b in bands)
        assert covered == set(range(14)), (first, covered)
        flat = [b for _, bands in keys for b in bands]
        assert flat == sorted(flat)
    assert _at(km, lay, "Escape")[0] == (0,)
    assert _at(km, lay, "Tab")[0] == (0,)
    assert 13 in _at(km, lay, "Backspace")[0]
    assert _at(km, lay, "Bsl")[0] == (13,)


def test_space_bar_averages_several_columns():
    km, lay = _layout()
    assert len(_at(km, lay, "Space")[0]) >= 4


def test_layout_is_generic_for_other_grids():
    pos = {i: (float(i % 8), float(i // 8)) for i in range(16)}   # 2 x 8 grid
    lay = music.grid_layout(pos)
    assert {m[2] for m in lay.values()} == {2}
    assert lay[0][1] == 1 and lay[8][1] == 0
    assert set(b for m in lay.values() if m[1] == 1 for b in m[0]) == set(range(14))
    assert music.grid_layout({}) == {}


def test_single_key_board_does_not_divide_by_zero():
    lay = music.grid_layout({5: (10.0, 3.0)})
    assert lay[5][1] == 0 and lay[5][2] == 1 and lay[5][0]


# ---------------------------------------------------------- availability ----
def _spec(present):
    return lambda name: object() if name in present else None


def test_available_on_windows_with_both_packages():
    assert music.availability("win32", _spec({"numpy", "soundcard"})) == (True, None)


def test_unavailable_off_windows_with_a_clear_reason():
    ok, why = music.availability("linux", _spec({"numpy", "soundcard"}))
    assert ok is False and "Windows" in why


def test_unavailable_names_the_missing_packages():
    assert music.availability("win32", _spec({"numpy"})) == (
        False, "Music visualizer needs the soundcard package (not installed).")
    assert music.availability("win32", _spec(set())) == (
        False, "Music visualizer needs the numpy and soundcard packages (not installed).")


def test_availability_never_imports_the_packages():
    import sys
    before = {m for m in ("numpy", "soundcard") if m in sys.modules}
    music.availability("win32")              # real importlib.util.find_spec
    after = {m for m in ("numpy", "soundcard") if m in sys.modules}
    assert after == before


def test_a_broken_find_spec_counts_as_missing():
    def boom(name):
        raise ValueError("bad spec")
    ok, why = music.availability("win32", boom)
    assert ok is False and "numpy and soundcard" in why
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_music_layout.py -q -p no:cacheprovider`
Expected: 11 FAIL with `AttributeError: module 'music' has no attribute 'grid_layout'` / `'availability'`.

- [ ] **Step 3: Append to `music.py`**

```python
# ------------------------------------------------------- keyboard layout ----
def grid_layout(pos, n_bands=N_BANDS):
    """{idx: (x_left, y)} -> {idx: (bands, row, n_rows)}.

    Rows are the distinct y values (top first); `row` counts from the BOTTOM
    (0 = space-bar row). Key widths are not in the keymap, so a key spans from
    its x to the next key's x in its row; the last key of a row ends at the
    board's right edge (largest x + the median key pitch). The board width is
    cut into n_bands equal columns; a key takes every column whose centre lies
    in its span (wide keys average several), else the column under its own
    centre."""
    if not pos:
        return {}
    ys = sorted({y for _, y in pos.values()})
    n_rows = len(ys)
    rows = {y: sorted((x, i) for i, (x, yy) in pos.items() if yy == y) for y in ys}
    gaps = sorted(b[0] - a[0] for r in rows.values() for a, b in zip(r, r[1:])
                  if b[0] > a[0])
    pitch = gaps[len(gaps) // 2] if gaps else 1.0
    x0 = min(x for x, _ in pos.values())
    x1 = max(x for x, _ in pos.values()) + pitch
    col_w = (x1 - x0) / n_bands
    centres = [x0 + (b + 0.5) * col_w for b in range(n_bands)]
    out = {}
    for rank, y in enumerate(ys):
        row = n_rows - 1 - rank
        keys = rows[y]
        for k, (x, idx) in enumerate(keys):
            end = keys[k + 1][0] if k + 1 < len(keys) else x1
            bands = tuple(b for b, c in enumerate(centres) if x <= c < end)
            if not bands:
                mid = (x + end) / 2.0
                bands = (max(0, min(n_bands - 1, int((mid - x0) / col_w))),)
            out[idx] = (bands, row, n_rows)
    return out


# ----------------------------------------------------------- availability ----
def availability(platform=None, find_spec=None):
    """(available, reason|None). Never imports numpy/soundcard (find_spec
    only), so it is safe on the UI thread."""
    platform = sys.platform if platform is None else platform
    find_spec = find_spec or importlib.util.find_spec
    if platform != "win32":
        return False, "Music visualizer needs Windows (WASAPI loopback capture)."
    missing = []
    for mod in ("numpy", "soundcard"):
        try:
            if find_spec(mod) is None:
                missing.append(mod)
        except (ImportError, ValueError):
            missing.append(mod)
    if missing:
        return False, ("Music visualizer needs the %s package%s (not installed)."
                       % (" and ".join(missing), "s" if len(missing) > 1 else ""))
    return True, None
```

- [ ] **Step 4: Run the tests**

Run: `<py> -m pytest tests/test_music_layout.py tests/test_music_dsp.py -q -p no:cacheprovider`
Expected: `23 passed`.

- [ ] **Step 5: Commit**

```bash
git add music.py tests/test_music_layout.py
git commit -m "feat(music): map 14 bands onto keyboard columns; dependency availability" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `MusicSource` capture thread, the numpy/soundcard adapters, and packaging

**Files:**
- Modify: `music.py` (append), `requirements.txt`, `AetherHE.spec`
- Test: `tests/test_music_source.py`, `tests/test_music_packaging.py` (create)

**Interfaces:**
- Consumes: Task 1 (`band_bins`, `band_edges`, `BandAnalyzer`, constants), Task 2 (`availability`).
- Produces: `NumpySpectrum(n_fft, bins)` callable `block -> list[float]` band powers (keeps the newest `n_fft` samples); `SoundcardBackend()` with `enter()`, `leave()`, `default_device() -> (id, name) | None`, `open(dev_id, rate, frames) -> stream` (`stream.read() -> mono samples`, `stream.close()`); `MusicSnapshot = namedtuple("MusicSnapshot", "levels beat_seq live")`; `ZERO_LEVELS = (0.0,) * 14`; `MusicSource(backend_factory=None, spectrum_factory=None, clock=time.monotonic, available=None)` with `start()`, `stop()` (both idempotent, thread-safe), `running() -> bool`, `snapshot() -> MusicSnapshot` (lock-free), `status() -> {"available", "reason", "state", "device"}`, `availability()`. Test fakes `FakeBackend`, `_spectrum`, `_wait` in `tests/test_music_source.py` are reused by Task 5.

- [ ] **Step 1: Write the failing tests** — `tests/test_music_source.py`:

```python
"""Phase 7: MusicSource capture-thread lifecycle with a fake loopback backend
and a fake spectrum. Never opens a real audio device, never imports numpy or
soundcard (the numpy-only adapter tests at the bottom skip without numpy)."""
import threading
import time

import pytest

import music

LOUD3 = [1e-4] * 14
LOUD3[3] = 1e-1          # band 3 is 30 dB above the rest


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(music, "RETRY_S", 0.02)
    monkeypatch.setattr(music, "DEVICE_CHECK_S", 0.02)


class FakeStream:
    def __init__(self, backend, dev_id):
        self.backend, self.dev_id, self.closed = backend, dev_id, False

    def read(self):
        time.sleep(0.005)
        if self.backend.fail_reads:
            self.backend.fail_reads -= 1
            raise OSError("device unplugged")
        return [0.0] * music.HOP

    def close(self):
        self.closed = True


class FakeBackend:
    def __init__(self, devices=(("spk-a", "Speakers A"),)):
        self.devices = list(devices)       # default_device() pops until one left
        self.opened, self.streams = [], []
        self.entered = self.left = 0
        self.fail_reads = 0
        self.fail_enter = None

    def enter(self):
        if self.fail_enter:
            raise self.fail_enter
        self.entered += 1

    def leave(self):
        self.left += 1

    def default_device(self):
        if not self.devices:
            return None
        return self.devices[0]

    def open(self, dev_id, rate, frames):
        assert (rate, frames) == (music.RATE, music.HOP)
        self.opened.append(dev_id)
        s = FakeStream(self, dev_id)
        self.streams.append(s)
        return s


def _spectrum(powers=LOUD3):
    def factory(n_fft, bins):
        assert n_fft == music.N_FFT and len(bins) == 14
        return lambda block: list(powers)
    return factory


def _source(backend, powers=LOUD3, available=(True, None)):
    return music.MusicSource(backend_factory=lambda: backend,
                             spectrum_factory=_spectrum(powers),
                             available=available)


def _wait(pred, secs=2.0):
    end = time.time() + secs
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.005)
    return False


def test_start_listens_to_the_default_output_and_stop_releases_it():
    be = FakeBackend()
    src = _source(be)
    src.start()
    assert _wait(lambda: src.status()["state"] == "listening")
    assert src.status() == {"available": True, "reason": None,
                            "state": "listening", "device": "Speakers A"}
    assert _wait(lambda: src.snapshot().levels[3] == 1.0)
    snap = src.snapshot()
    assert snap.live is True and max(snap.levels[:3]) < 0.5
    src.stop()
    assert not src.running()
    assert be.streams[0].closed and be.left == 1
    assert src.status()["state"] == "off"
    assert src.snapshot() == music.MusicSnapshot(music.ZERO_LEVELS, src.snapshot().beat_seq, False)


def test_start_is_idempotent_and_stop_is_safe_twice():
    be = FakeBackend()
    src = _source(be)
    src.stop()                                    # never started
    src.start()
    src.start()
    assert _wait(lambda: src.status()["state"] == "listening")
    time.sleep(0.05)
    assert be.opened == ["spk-a"]
    src.stop()
    src.stop()
    assert not src.running()


def test_missing_dependencies_mean_no_thread_and_a_reason():
    be = FakeBackend()
    src = _source(be, available=(False, "Music visualizer needs the numpy package (not installed)."))
    src.start()
    assert not src.running() and be.entered == 0 and be.opened == []
    st = src.status()
    assert st["available"] is False and st["state"] == "unavailable"
    assert st["reason"] == "Music visualizer needs the numpy package (not installed)."
    assert src.snapshot().live is False


def test_no_output_device_is_reported_and_picked_up_when_one_appears():
    be = FakeBackend(devices=())
    src = _source(be)
    src.start()
    assert _wait(lambda: src.status()["state"] == "no_device")
    assert src.status()["reason"] == "No audio output device found."
    assert src.snapshot().live is False
    be.devices.append(("spk-b", "Headphones"))
    assert _wait(lambda: src.status()["state"] == "listening")
    assert src.status()["device"] == "Headphones"
    src.stop()


def test_a_changed_default_output_is_re_acquired():
    be = FakeBackend()
    src = _source(be)
    src.start()
    assert _wait(lambda: be.opened == ["spk-a"])
    be.devices.insert(0, ("spk-b", "USB DAC"))
    assert _wait(lambda: be.opened == ["spk-a", "spk-b"])
    assert be.streams[0].closed
    assert _wait(lambda: src.status()["device"] == "USB DAC")
    src.stop()


def test_a_read_error_closes_the_stream_and_retries():
    be = FakeBackend()
    be.fail_reads = 1
    src = _source(be)
    src.start()
    assert _wait(lambda: len(be.opened) >= 2)
    assert be.streams[0].closed
    assert _wait(lambda: src.status()["state"] == "listening")
    src.stop()


def test_a_failing_backend_reports_an_error_and_never_raises():
    be = FakeBackend()
    be.fail_enter = ImportError("No module named 'soundcard'")
    src = _source(be)
    src.start()
    assert _wait(lambda: not src.running())
    st = src.status()
    assert st["state"] == "error"
    assert st["reason"] == "Audio capture failed: No module named 'soundcard'"


def test_snapshot_goes_dark_when_capture_stalls():
    now = [100.0]
    src = music.MusicSource(backend_factory=FakeBackend, spectrum_factory=_spectrum(),
                            clock=lambda: now[0], available=(True, None))
    src._state = "listening"
    src._pub = ((0.5,) * 14, 3, 100.0)
    assert src.snapshot() == music.MusicSnapshot((0.5,) * 14, 3, True)
    now[0] = 100.0 + music.STALE_S + 0.01
    assert src.snapshot() == music.MusicSnapshot(music.ZERO_LEVELS, 3, True)


def test_beats_advance_the_sequence_number():
    seq = {"k": 0}
    quiet, kick = [1e-3] * 14, [1e-1] * 6 + [1e-3] * 8

    def factory(n_fft, bins):
        def spec(block):
            seq["k"] += 1
            return list(kick if seq["k"] % 40 == 0 else quiet)
        return spec
    src = music.MusicSource(backend_factory=FakeBackend, spectrum_factory=factory,
                            available=(True, None))
    src.start()
    assert _wait(lambda: src.snapshot().beat_seq >= 2, secs=3.0)
    src.stop()


def test_stop_returns_promptly_and_the_thread_ends():
    be = FakeBackend()
    src = _source(be)
    src.start()
    assert _wait(lambda: src.status()["state"] == "listening")
    th = src._thread
    t0 = time.perf_counter()
    src.stop()
    assert time.perf_counter() - t0 < 0.5
    assert _wait(lambda: not th.is_alive())
    assert not any(t.name == "aether-music" and t.is_alive() for t in threading.enumerate())


# --------------------------------------------- numpy adapter (skips without numpy) ----
def test_numpy_spectrum_matches_the_pure_band_powers():
    np = pytest.importorskip("numpy")
    bins = music.band_bins(music.N_FFT, music.RATE, music.band_edges())
    spec = music.NumpySpectrum(music.N_FFT, bins)
    rng = np.random.default_rng(1)
    x = rng.uniform(-0.5, 0.5, music.N_FFT)
    got = spec(x)
    w = np.hanning(music.N_FFT)
    X = np.fft.rfft(x * w)
    power = ((X.real ** 2 + X.imag ** 2) * (2.0 / w.sum()) ** 2).tolist()
    assert got == pytest.approx(music.band_powers(power, bins), rel=1e-9)


def test_numpy_spectrum_puts_a_1_khz_tone_in_its_band():
    np = pytest.importorskip("numpy")
    bins = music.band_bins(music.N_FFT, music.RATE, music.band_edges())
    spec = music.NumpySpectrum(music.N_FFT, bins)
    t = np.arange(music.N_FFT) / music.RATE
    got = spec(np.sin(2 * np.pi * 1000.0 * t))
    peak = max(range(14), key=lambda b: got[b])
    assert peak == 7                                   # 800-1227 Hz
    assert -3.0 < 10 * np.log10(got[7]) < 3.0          # full scale ~ 0 dBFS
    assert all(got[b] < got[7] * 1e-2 for b in range(14) if b != 7)


def test_numpy_spectrum_keeps_the_newest_window_across_blocks():
    np = pytest.importorskip("numpy")
    bins = music.band_bins(music.N_FFT, music.RATE, music.band_edges())
    a = music.NumpySpectrum(music.N_FFT, bins)
    b = music.NumpySpectrum(music.N_FFT, bins)
    x = np.random.default_rng(2).uniform(-1, 1, 3 * music.HOP)
    for k in range(3):
        last = a(x[k * music.HOP:(k + 1) * music.HOP])
    assert last == pytest.approx(b(x[-music.N_FFT:]))      # 1440 samples fed, last 1024 kept
```

and `tests/test_music_packaging.py`:

```python
"""Phase 7: the two new dependencies are declared for Windows only and
bundled by the PyInstaller spec. Text checks only: nothing is installed."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return fh.read()


def test_requirements_add_numpy_and_soundcard_for_windows_only():
    req = _read("requirements.txt")
    assert re.search(r'^numpy>=1\.26;\s+sys_platform == "win32"$', req, re.M)
    assert re.search(r'^soundcard>=0\.4\.3;\s+sys_platform == "win32"$', req, re.M)


def test_pillow_pin_is_untouched():
    assert re.search(r'^Pillow>=10;    sys_platform == "win32"$', _read("requirements.txt"), re.M)


def test_spec_bundles_soundcard_data_and_lazy_imports():
    spec = _read("AetherHE.spec")
    assert 'collect_data_files("soundcard")' in spec
    for mod in ("numpy", "soundcard", "soundcard.mediafoundation", "_cffi_backend"):
        assert '"%s"' % mod in spec, mod
    excludes = spec[spec.index("excludes=["):spec.index("],", spec.index("excludes=["))]
    assert "numpy" not in excludes and "soundcard" not in excludes


def test_music_module_imports_neither_dependency_at_top_level():
    import ast
    tree = ast.parse(_read("music.py"))
    top = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            top.add(node.module.split(".")[0])
    assert not top & {"numpy", "soundcard"}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_music_source.py tests/test_music_packaging.py -q -p no:cacheprovider`
Expected: the source tests FAIL with `AttributeError: module 'music' has no attribute 'MusicSource'` (the 3 numpy tests SKIP: "could not import 'numpy'"); packaging: 2 FAIL (`test_requirements_add_numpy_and_soundcard_for_windows_only`, `test_spec_bundles_soundcard_data_and_lazy_imports`), `test_pillow_pin_is_untouched` and `test_music_module_imports_neither_dependency_at_top_level` pass.

- [ ] **Step 3: Append to `music.py`**

```python
# ------------------------------------------------- numpy / soundcard adapters ----
class NumpySpectrum:
    """Block -> band powers. Keeps the newest n_fft mono samples, Hann window,
    rfft, |X|^2 scaled so a full-scale sine's peak bin is 1 (0 dBFS), summed
    per band via a cumulative sum (vectorised band_powers)."""

    def __init__(self, n_fft, bins):
        import numpy as np          # lazy: only on the capture thread
        self._np = np
        self._n = n_fft
        win = np.hanning(n_fft)
        self._win = win
        self._k = (2.0 / float(win.sum())) ** 2
        self._buf = np.zeros(n_fft)
        self._lo = np.array([lo for lo, _, _ in bins])
        self._hi = np.array([hi for _, hi, _ in bins])
        self._w = np.array([w for _, _, w in bins])

    def __call__(self, block):
        np = self._np
        x = np.asarray(block, dtype=float).ravel()
        k = x.size
        if k >= self._n:
            self._buf[:] = x[-self._n:]
        elif k:
            self._buf[:-k] = self._buf[k:]
            self._buf[-k:] = x
        spec = np.fft.rfft(self._buf * self._win)
        p = (spec.real * spec.real + spec.imag * spec.imag) * self._k
        c = np.concatenate(([0.0], np.cumsum(p)))
        return ((c[self._hi] - c[self._lo]) * self._w).tolist()


class SoundcardBackend:
    """WASAPI loopback of the default output through `soundcard`. Every call
    happens on the capture thread: COM is initialised per thread (MTA) here,
    and soundcard is imported here, never on the UI thread."""

    def __init__(self):
        self._sc = None
        self._com = False

    def enter(self):
        if sys.platform == "win32":
            import ctypes
            hr = ctypes.windll.ole32.CoInitializeEx(None, 0)   # COINIT_MULTITHREADED
            self._com = hr in (0, 1)                           # S_OK / S_FALSE
        import soundcard
        self._sc = soundcard

    def leave(self):
        if self._com:
            import ctypes
            ctypes.windll.ole32.CoUninitialize()
            self._com = False

    def default_device(self):
        spk = self._sc.default_speaker()
        return (str(spk.id), str(spk.name)) if spk is not None else None

    def open(self, dev_id, rate, frames):
        mic = self._sc.get_microphone(dev_id, include_loopback=True)
        rec = mic.recorder(samplerate=rate, blocksize=frames)
        rec.__enter__()
        return _SoundcardStream(rec, frames)


class _SoundcardStream:
    def __init__(self, rec, frames):
        self._rec = rec
        self._frames = frames

    def read(self):
        data = self._rec.record(numframes=self._frames)
        return data.mean(axis=1) if getattr(data, "ndim", 1) == 2 else data

    def close(self):
        self._rec.__exit__(None, None, None)


# ----------------------------------------------------------- the source ----
MusicSnapshot = namedtuple("MusicSnapshot", "levels beat_seq live")
ZERO_LEVELS = (0.0,) * N_BANDS


class MusicSource:
    """Owns the capture thread. start()/stop() are idempotent and thread-safe;
    snapshot() is lock-free (one tuple read) for the engine; status() feeds
    the music_status bridge. The thread runs only between start() and stop()."""

    def __init__(self, backend_factory=None, spectrum_factory=None,
                 clock=time.monotonic, available=None):
        self._backend_factory = backend_factory or SoundcardBackend
        self._spectrum_factory = spectrum_factory or NumpySpectrum
        self._clock = clock
        self._avail = available
        self._life = threading.Lock()
        self._thread = None
        self._ev = threading.Event()
        self._ev.set()
        self._pub = (ZERO_LEVELS, 0, -1e9)    # (levels, beat_seq, published at)
        self._beats = 0
        self._state = "off"
        self._device = None
        self._error = None

    def availability(self):
        return self._avail if self._avail is not None else availability()

    def running(self):
        th = self._thread
        return th is not None and th.is_alive()

    def start(self):
        with self._life:
            if self.running() and not self._ev.is_set():
                return
            ok, _ = self.availability()
            if not ok:
                self._state = "unavailable"
                return
            ev = threading.Event()
            self._ev = ev
            self._state, self._device, self._error = "starting", None, None
            th = threading.Thread(target=self._loop, args=(ev,),
                                  name="aether-music", daemon=True)
            self._thread = th
            th.start()

    def stop(self):
        with self._life:
            self._ev.set()
            th, self._thread = self._thread, None
            self._state, self._device = "off", None
            self._pub = (ZERO_LEVELS, self._beats, -1e9)
        if th is not None and th is not threading.current_thread():
            th.join(timeout=0.5)

    def snapshot(self):
        levels, seq, at = self._pub
        live = self._state == "listening"
        if not live or self._clock() - at > STALE_S:
            levels = ZERO_LEVELS
        return MusicSnapshot(levels, seq, live)

    def status(self):
        ok, reason = self.availability()
        state = self._state if ok else "unavailable"
        if state == "no_device":
            reason = MSG_NO_DEVICE
        elif state == "error":
            reason = "Audio capture failed: %s" % (self._error or "unknown error")
        return {"available": bool(ok), "reason": reason, "state": state,
                "device": self._device if state == "listening" else None}

    # -- capture thread --
    def _set(self, ev, state, device=None, error=None):
        with self._life:
            if ev is self._ev and not ev.is_set():
                self._state, self._device, self._error = state, device, error

    def _default(self, backend):
        try:
            return backend.default_device()
        except Exception:
            return None

    def _loop(self, ev):
        try:
            backend = self._backend_factory()
            backend.enter()
        except Exception as e:
            log.warning("music capture unavailable: %s", e)
            self._set(ev, "error", error=str(e))
            return
        try:
            bins = band_bins(N_FFT, RATE, band_edges())
            while not ev.is_set():
                dev = self._default(backend)
                if dev is None:
                    self._set(ev, "no_device")
                    ev.wait(RETRY_S)
                    continue
                dev_id, dev_name = dev
                try:
                    stream = backend.open(dev_id, RATE, HOP)
                except Exception as e:
                    log.warning("audio loopback open failed (%s): %s", dev_name, e)
                    self._set(ev, "no_device")
                    ev.wait(RETRY_S)
                    continue
                try:
                    self._capture(ev, backend, stream, dev, bins)
                except Exception as e:
                    log.warning("music capture stopped: %s", e)
                    self._set(ev, "no_device")
                    ev.wait(RETRY_S)
                finally:
                    try:
                        stream.close()
                    except Exception:
                        pass
        finally:
            try:
                backend.leave()
            except Exception:
                pass

    def _capture(self, ev, backend, stream, dev, bins):
        spectrum = self._spectrum_factory(N_FFT, bins)
        an = BandAnalyzer(len(bins))
        self._set(ev, "listening", dev[1])
        next_check = self._clock() + DEVICE_CHECK_S
        while not ev.is_set():
            block = stream.read()
            n = len(block)
            if n:
                levels, beat = an.feed(spectrum(block), n / float(RATE))
                if beat:
                    self._beats += 1
                if not ev.is_set():
                    self._pub = (tuple(levels), self._beats, self._clock())
            else:
                ev.wait(0.005)          # nothing captured: do not spin
            now = self._clock()
            if now >= next_check:
                next_check = now + DEVICE_CHECK_S
                cur = self._default(backend)
                if cur is None or cur[0] != dev[0]:
                    log.info("default audio output changed; re-acquiring")
                    return
```

- [ ] **Step 4: Declare the dependencies.** In `requirements.txt`, directly after the `Pillow>=10;    sys_platform == "win32"` line (leave that line byte-identical) and its following blank line, insert:

```
# Music visualizer (music.py): WASAPI loopback capture + FFT. Windows only;
# without them the "music" effect reports itself unavailable.
numpy>=1.26;      sys_platform == "win32"
soundcard>=0.4.3; sys_platform == "win32"

```

In `AetherHE.spec`: after `binaries = collect_dynamic_libs("vgamepad")` add

```python
# Music visualizer: soundcard loads its WASAPI cffi declarations
# (mediafoundation.py.h) from package data at import time. numpy is found by
# PyInstaller's own hook (it must NOT be in `excludes`). Both are imported
# lazily on the capture thread, so name them as hidden imports too.
datas += collect_data_files("soundcard")
```

and append to the `hidden` list, after the `"PIL.Image", ...` line:

```python
    # music.py imports these inside the capture thread only.
    "numpy", "soundcard", "soundcard.mediafoundation", "_cffi_backend",
```

(`collect_data_files` of a package that is not installed only logs a warning in PyInstaller, so the spec still builds before the user installs the deps — but the frozen app then reports Music unavailable.)

- [ ] **Step 5: Run the tests (three times: they use real threads)**

Run: `<py> -m pytest tests/test_music_source.py tests/test_music_packaging.py tests/test_music_dsp.py tests/test_music_layout.py -q -p no:cacheprovider`
Expected: `37 passed, 3 skipped` on each of 3 runs (the skips are the numpy adapter tests; they run once the user installs numpy).

- [ ] **Step 6: Commit**

```bash
git add music.py requirements.txt AetherHE.spec tests/test_music_source.py tests/test_music_packaging.py
git commit -m "feat(music): loopback capture thread with lazy numpy/soundcard adapters" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The `_g_music` generator and engine-owned capture lifecycle

**Files:**
- Modify: `effects.py`, `flatpak/io.github.mrwhosnexus.AetherHE.yml`
- Test: `tests/test_music_effect.py` (create)

**Interfaces:**
- Consumes: `music.grid_layout`, `music.N_BANDS`, `music.ZERO_LEVELS`, `music.MusicSnapshot`; a source object with `start()`, `stop()`, `snapshot()` (Task 3).
- Produces: module constants `MUSIC_RELEASE_SLOW_S = 0.30`, `MUSIC_RELEASE_FAST_S = 0.08`, `MUSIC_PULSE_S = 0.15`, `MUSIC_PULSE_MAX = 0.45`, `MUSIC_IDLE_PERIOD_S = 3.0`, `MUSIC_IDLE_MAX = 0.15`, `_gradient(pal, u)`; `PerKeyEffectEngine.music` (default `None`), `_halt()`, `_music_power(on: bool)`, `_music_map() -> dict`, `_g_music(z, t, frame)`. NOT yet in `_gens` (Task 6 registers it together with the UI's `HOST_FX_IDS`; until then a `"music"` zone animates as the default wave, which the lifecycle tests do not care about).

- [ ] **Step 1: Write the failing tests** — `tests/test_music_effect.py`:

```python
"""Phase 7 "music" host effect: band levels -> column bars, beat pulse on the
background, idle state without audio, and the engine owning the capture
lifecycle. The generator is called directly with a fake clock and a fake
MusicSource. No audio device, no HID, no keyboard."""
import math
import time

import pytest

import device_state
import effects
import music

BG = (0, 0, 0)
RED = (255, 0, 0)
BLUE = (0, 0, 255)


class FakeKM:
    """2 rows x 14 columns: row y=0 on top, y=1 at the bottom."""
    def __init__(self):
        self.by_index = {i: {"x": float(i % 14), "y": float(i // 14)} for i in range(28)}
        self.index_of_code = {}


class FakeSource:
    def __init__(self, levels=None, live=True, seq=0):
        self.levels = tuple(levels or (0.0,) * 14)
        self.live, self.seq = live, seq
        self.calls = []

    def snapshot(self):
        return music.MusicSnapshot(self.levels, self.seq, self.live)

    def start(self):
        self.calls.append("start")

    def stop(self):
        self.calls.append("stop")


def _engine(src=None, km=None):
    eng = effects.PerKeyEffectEngine(km or FakeKM(), lambda frame: None)
    eng.music = src
    return eng


def _zone(eng, palette=(RED,), bg=BG, bright=1.0, speed=0.5):
    return effects.Zone(list(eng.indices), "music", list(palette), bg, speed, bright, 0)


def _frame(eng, z, t):
    frame = {}
    eng._g_music(z, t, frame)
    return frame


TOP, BOTTOM = 0, 14          # first index of each FakeKM row


# ---------------------------------------------------------------- bars ----
def test_band_level_sets_the_bar_height():
    lv = [0.0] * 14
    lv[0], lv[1], lv[2] = 1.0, 0.5, 0.25
    eng = _engine(FakeSource(lv))
    z = _zone(eng, palette=(RED, BLUE))
    f = _frame(eng, z, 0.0)
    assert f[BOTTOM + 0] == RED and f[TOP + 0] == BLUE      # full bar, gradient bottom->top
    assert f[BOTTOM + 1] == RED and f[TOP + 1] == BG        # half = the bottom row only
    assert f[BOTTOM + 2] == (127, 0, 0) and f[TOP + 2] == BG
    assert f[BOTTOM + 3] == BG                              # silent band


def test_attack_is_instant_and_release_follows_the_speed_slider():
    src = FakeSource([1.0] * 14)
    slow, fast = _engine(src), _engine(src)
    zs, zf = _zone(slow, speed=0.0), _zone(fast, speed=1.0)
    assert _frame(slow, zs, 0.0)[TOP] == RED                # instant
    _frame(fast, zf, 0.0)
    src.levels = (0.0,) * 14
    s = _frame(slow, zs, 0.1)[TOP]
    f = _frame(fast, zf, 0.1)[TOP]
    assert f[0] < s[0]                                      # faster speed falls faster
    exp_slow = math.exp(-0.1 / effects.MUSIC_RELEASE_SLOW_S)
    assert abs(s[0] - 255 * (exp_slow * 2 - 1)) <= 1          # top row = 2 * level - 1
    for k in range(1, 120):
        last = _frame(slow, zs, 0.1 + k / 60)
    assert all(c == BG for c in last.values())              # dark within 2 s, no endless tail


def test_wide_key_averages_its_columns():
    km = device_state.KeyMap()
    eng = _engine(FakeSource(), km=km)
    lay = eng._music_map()
    space = km.index_of_code["Space"]
    bands = lay[space][0]
    lv = [0.0] * 14
    lv[bands[0]] = 0.5                                       # one of its columns half full
    eng.music.levels = tuple(lv)
    z = _zone(eng)
    f = _frame(eng, z, 0.0)
    assert f[space] == effects._lerp(BG, RED, 5 * 0.5 / len(bands))   # 5 rows * mean level


def test_real_win60_bottom_to_top():
    km = device_state.KeyMap()
    eng = _engine(FakeSource([0.6] * 14), km=km)            # 0.6 * 5 rows = 3 rows lit
    z = _zone(eng)
    f = _frame(eng, z, 0.0)
    code = km.index_of_code
    assert f[code["Space"]] == RED and f[code["Z"]] == RED and f[code["A"]] == RED
    assert f[code["Q"]] == BG and f[code["1"]] == BG


def test_brightness_scales_the_bars():
    eng = _engine(FakeSource([1.0] * 14))
    z = _zone(eng, bright=0.5)
    assert _frame(eng, z, 0.0)[TOP] == (127, 0, 0)


# ---------------------------------------------------------------- beats ----
def test_a_new_beat_pulses_the_background_then_fades():
    src = FakeSource(seq=4)
    eng = _engine(src)
    z = _zone(eng, palette=(RED,), bg=(0, 0, 0))
    assert _frame(eng, z, 0.0)[TOP] == BG                   # first look: no pulse
    src.seq = 5
    hit = _frame(eng, z, 1 / 60)[TOP]
    assert hit == effects._lerp(BG, RED, effects.MUSIC_PULSE_MAX)
    later = _frame(eng, z, 1.0)[TOP]
    assert later == BG


def test_unchanged_beat_sequence_never_pulses():
    eng = _engine(FakeSource(seq=9))
    z = _zone(eng)
    for k in range(30):
        assert _frame(eng, z, k / 60)[TOP] == BG


# ----------------------------------------------------------------- idle ----
@pytest.mark.parametrize("src", [None, FakeSource([1.0] * 14, live=False)])
def test_no_audio_breathes_the_bottom_row_only(src):
    eng = _engine(src)
    z = _zone(eng)
    peak = _frame(eng, z, effects.MUSIC_IDLE_PERIOD_S / 2)
    assert peak[BOTTOM] == effects._lerp(BG, RED, effects.MUSIC_IDLE_MAX)
    assert peak[TOP] == BG
    assert _frame(eng, z, effects.MUSIC_IDLE_PERIOD_S)[BOTTOM] == BG


def test_a_failing_source_is_treated_as_no_audio():
    class Boom(FakeSource):
        def snapshot(self):
            raise RuntimeError("capture hiccup")
    eng = _engine(Boom())
    z = _zone(eng)
    f = _frame(eng, z, 0.0)
    assert set(f) == set(eng.indices)


def test_all_channel_values_stay_in_byte_range():
    src = FakeSource([1.0, 0.0] * 7, seq=1)
    eng = _engine(src, km=device_state.KeyMap())
    z = _zone(eng, palette=((255, 255, 255), (255, 0, 0)), bg=(255, 255, 255))
    for k in range(120):
        src.seq += k % 7 == 0
        src.levels = tuple((math.sin(k / 5 + b) + 1) / 2 for b in range(14))
        for c in _frame(eng, z, k / 60).values():
            assert all(isinstance(v, int) and 0 <= v <= 255 for v in c)


def test_frame_cost_is_well_under_the_budget():
    eng = _engine(FakeSource([0.5] * 14), km=device_state.KeyMap())
    z = _zone(eng, palette=(RED, BLUE))
    _frame(eng, z, 0.0)
    t0 = time.perf_counter()
    for k in range(1, 61):
        _frame(eng, z, k / 60)
    assert (time.perf_counter() - t0) / 60 < 0.004          # < 4 ms per 61-key frame


# ------------------------------------------------------------ lifecycle ----
def test_the_engine_starts_capture_only_for_music_and_stops_it_with_the_effect():
    src = FakeSource()
    eng = _engine(src)
    eng.start("wave", [RED], BG, 0.5, 1.0)
    assert src.calls == ["stop"]                             # not music: kept off
    eng.start_zones([{"indices": eng.indices[:14], "mode": "music", "palette": [RED]},
                     {"indices": eng.indices[14:], "mode": "wave", "palette": [RED]}])
    assert src.calls[-1] == "start"
    eng.stop()
    assert src.calls[-1] == "stop" and not eng.is_running()


def test_restarting_music_keeps_the_capture_running():
    src = FakeSource()
    eng = _engine(src)
    eng.start("music", [RED], BG, 0.5, 1.0)
    eng.start("music", [BLUE], BG, 0.9, 1.0)                 # palette/speed edit
    assert src.calls == ["start", "start"]                   # no stop in between
    eng.stop()
    assert src.calls[-1] == "stop"


def test_switching_away_from_music_stops_the_capture():
    src = FakeSource()
    eng = _engine(src)
    eng.start("music", [RED], BG, 0.5, 1.0)
    eng.start("rain", [RED], BG, 0.5, 1.0)
    assert src.calls == ["start", "stop"]
    eng.stop()


def test_a_dead_stream_releases_the_capture():
    src = FakeSource()

    def broken(frame):
        raise OSError("device gone")
    eng = effects.PerKeyEffectEngine(FakeKM(), broken)
    eng.music = src
    eng.start("music", [RED], BG, 0.5, 1.0)
    end = time.time() + 2.0
    while eng.is_running() and time.time() < end:
        time.sleep(0.01)
    assert src.calls == ["start", "stop"]


def test_a_raising_source_never_breaks_start_or_stop():
    class Bad(FakeSource):
        def start(self):
            raise RuntimeError("no COM")
        stop = start
    eng = _engine(Bad())
    eng.start("music", [RED], BG, 0.5, 1.0)
    assert eng.is_running()
    eng.stop()
    assert not eng.is_running()


def test_engines_without_a_source_are_unchanged():
    eng = _engine(None)
    eng.start("music", [RED], BG, 0.5, 1.0)
    eng.stop()
    assert eng.music is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_music_effect.py -q -p no:cacheprovider`
Expected: FAIL with `AttributeError: 'PerKeyEffectEngine' object has no attribute '_g_music'` / `_music_map` / `module 'effects' has no attribute 'MUSIC_RELEASE_SLOW_S'`, and the lifecycle tests fail on `src.calls`.

- [ ] **Step 3: Implement in `effects.py`**

- After `import time` (top imports) add a blank line and `import music`.
- After `pressure_level(...)` (before `class Zone:`) add:

```python
# ---- "music" effect constants (Phase 7) ----
MUSIC_RELEASE_SLOW_S = 0.30      # bar fall time constant at speed 0
MUSIC_RELEASE_FAST_S = 0.08      # ... at speed 1 (attack is instant)
MUSIC_PULSE_S = 0.15             # beat pulse decay time constant
MUSIC_PULSE_MAX = 0.45           # background -> palette[0] blend at a beat
MUSIC_IDLE_PERIOD_S = 3.0        # no audio: bottom row breathes this slowly
MUSIC_IDLE_MAX = 0.15            # ... up to this much palette[0]


def _gradient(pal, u):
    """Non-looping palette gradient: first colour at u=0, last at u=1."""
    n = len(pal)
    if n == 1:
        return pal[0]
    p = min(max(u, 0.0), 1.0) * (n - 1)
    i = min(int(p), n - 2)
    return _lerp(pal[i], pal[i + 1], p - i)
```

- In `PerKeyEffectEngine.__init__`, after `self.overlay = None ...` add:

```python
        # optional music.MusicSource: started while any zone runs "music",
        # stopped with the engine (the capture never runs otherwise)
        self.music = None
        self._music_lay = None    # {idx: (bands, row, n_rows)}, built on first use
```

- `start_zones`: replace its first line `self.stop()` with `self._halt()`, and directly after `self._base_frame.update(self.base)` add:

```python
        # Audio capture follows the zones: kept running across a restart that
        # still has a music zone (palette/speed edits), stopped otherwise.
        self._music_power(any(z.mode == "music" for z in self.zones))
```

- Replace `stop()` with `stop()` + `_halt()` (the old body) + `_music_power()`:

```python
    def stop(self):
        self._halt()
        self._music_power(False)

    def _halt(self):
        """Stop the frame thread only (start_zones decides about the music capture)."""
        self._stop.set()
        th = self._thread
        if th is not None and th is not threading.current_thread():
            th.join(timeout=0.5)
        self._thread = None
        self.last_frame = {}

    def _music_power(self, on):
        src = self.music
        if src is None:
            return
        try:
            if on:
                src.start()
            else:
                src.stop()
        except Exception:
            pass                  # audio trouble must never break the lighting
```

- In `_run`, the `except Exception:` around `send(frame)` becomes:

```python
            try:
                send(frame)            # palette already gamma-corrected; bg left linear
            except Exception:
                if self._stop is stop_ev:          # still the current run
                    self._music_power(False)       # the stream died: release the audio too
                break
```

- After `_g_pressure` (end of the class, before `# Back-compat alias`) add:

```python
    def _music_map(self):
        lay = self._music_lay
        if lay is None:
            lay = self._music_lay = music.grid_layout(
                {i: (self.km.by_index[i]["x"], self.km.by_index[i]["y"]) for i in self.indices})
        return lay

    def _g_music(self, z, t, frame):
        # 14 audio bands -> 14 columns, bar height across the rows (row 0 =
        # bottom), palette as a bottom->top gradient, background pulsing toward
        # palette[0] on beats. Instant attack, speed-controlled release (time
        # based). No audio (no source / no device / deps missing): the bottom
        # row breathes faintly so the effect visibly waits.
        st = z.state
        lay = self._music_map()
        n_rows = max((m[2] for m in lay.values()), default=1)
        rowcol = st.get("rowcol")
        if rowcol is None:
            rowcol = st["rowcol"] = [_gradient(z.palette, r / (n_rows - 1) if n_rows > 1 else 0.0)
                                     for r in range(n_rows)]
        snap = None
        src = self.music
        if src is not None:
            try:
                snap = src.snapshot()
            except Exception:
                snap = None
        live = bool(snap is not None and snap.live)
        last_t = st.get("t")
        dt = 0.0 if last_t is None else max(0.0, t - last_t)
        st["t"] = t
        rel_s = MUSIC_RELEASE_SLOW_S - (MUSIC_RELEASE_SLOW_S - MUSIC_RELEASE_FAST_S) * z.speed
        k_rel = 1.0 - math.exp(-dt / rel_s) if dt > 0 else 0.0
        lv = st.get("lv")
        if lv is None:
            lv = st["lv"] = [0.0] * music.N_BANDS
        tg = snap.levels if live else music.ZERO_LEVELS
        for b in range(music.N_BANDS):
            v = tg[b] if b < len(tg) else 0.0
            cur = lv[b]
            cur = v if v >= cur else cur + (v - cur) * k_rel
            lv[b] = cur if cur >= 0.004 else 0.0      # exponential tail ends
        pulse = st.get("pulse", 0.0) * (math.exp(-dt / MUSIC_PULSE_S) if dt > 0 else 1.0)
        if snap is not None:
            seq = st.get("seq")
            if seq is not None and snap.beat_seq != seq:
                pulse = 1.0
            st["seq"] = snap.beat_seq
        st["pulse"] = pulse
        bgc = _lerp(z.bg, z.palette[0], MUSIC_PULSE_MAX * pulse) if pulse > 0.004 else z.bg
        idle = 0.0 if live else MUSIC_IDLE_MAX * (0.5 - 0.5 * math.cos(2 * math.pi * t / MUSIC_IDLE_PERIOD_S))
        bright = z.bright
        for idx in z.indices:
            m = lay.get(idx)
            if m is None:
                frame[idx] = _scale(bgc, bright)
                continue
            bands, row, rows = m
            if live:
                v = sum(lv[b] for b in bands) / len(bands)
                f = min(1.0, max(0.0, v * rows - row))
            else:
                f = idle if row == 0 else 0.0
            frame[idx] = _scale(_lerp(bgc, rowcol[min(row, n_rows - 1)], f), bright)
```

In `flatpak/io.github.mrwhosnexus.AetherHE.yml`, in the `cp -r ... /app/share/aether/` command, insert `music.py` after `overlays.py` (`tests/test_packaging.py::test_flatpak_packages_entire_import_closure` fails otherwise: `effects` now imports `music`).

- [ ] **Step 4: Run the tests and the engine suites**

Run: `<py> -m pytest tests/test_music_effect.py tests/test_pressure_effect.py tests/test_effects_stream.py tests/test_overlays_layer.py tests/test_overlays_carrier.py tests/test_packaging.py -q -p no:cacheprovider`
Expected: all pass (`18` in `test_music_effect.py`).

- [ ] **Step 5: Commit**

```bash
git add effects.py flatpak/io.github.mrwhosnexus.AetherHE.yml tests/test_music_effect.py
git commit -m "feat(effects): music bars generator; engine starts/stops audio capture with the zones" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Api ownership and the `music_status` bridge

**Files:**
- Modify: `app_web.py`
- Test: `tests/test_music_api.py` (create)

**Interfaces:**
- Consumes: `music.MusicSource`, `music.availability` (Task 3), `PerKeyEffectEngine.music` (Task 4); test fakes `FakeBackend`, `_spectrum`, `_wait` (`tests/test_music_source.py`) and `FakeDev`, `FakeDriver` (`tests/test_overlays_api.py`).
- Produces: `Api._music` (PRIVATE: pywebview walks public attributes), `Api._music_attach()`, bridge `Api.music_status() -> {"ok": True, "available": bool, "reason": str | None, "state": str, "device": str | None}` or `{"ok": False, "error": ...}`; never raises, never opens a device.

- [ ] **Step 1: Write the failing tests** — `tests/test_music_api.py`:

```python
"""Phase 7: Api wiring for the music visualizer — the music_status bridge and
the engine owning the capture through start_multicolor / stop_multicolor.
Fake driver, fake loopback backend: no HID, no keyboard, no audio device."""
import inspect
import threading
import time

import app_web
import boards
import device_state
import effects
import music
from test_music_source import FakeBackend, _spectrum, _wait
from test_overlays_api import FakeDev, FakeDriver

KEYS = {"ok", "available", "reason", "state", "device"}


def _api(backend=None, available=(True, None)):
    a = app_web.Api.__new__(app_web.Api)
    a._lock = threading.RLock()
    a.board = boards.load_registry().by_slug("aula-win60-he")
    a.km = device_state.KeyMap()
    a.dev = FakeDev()
    a.driver = FakeDriver()
    a.frames = []
    a.fx = effects.PerKeyEffectEngine(a.km, lambda f: a.frames.append(1))
    a.reader = a.calib_reader = None
    a._reader_users = set()
    a._carrier_on = False
    if backend is not None:
        a._music = music.MusicSource(backend_factory=lambda: backend,
                                     spectrum_factory=_spectrum(),
                                     available=available)
        a._music_attach()
    return a


def test_status_without_a_source_reports_availability(monkeypatch):
    monkeypatch.setattr(music, "availability",
                        lambda: (False, "Music visualizer needs the numpy package (not installed)."))
    r = _api().music_status()
    assert r == {"ok": True, "available": False, "state": "unavailable", "device": None,
                 "reason": "Music visualizer needs the numpy package (not installed)."}
    monkeypatch.setattr(music, "availability", lambda: (True, None))
    assert _api().music_status() == {"ok": True, "available": True, "reason": None,
                                     "state": "off", "device": None}


def test_music_effect_listens_while_running_and_releases_on_stop():
    be = FakeBackend()
    a = _api(be)
    assert a.fx.music is a._music
    assert a.music_status()["state"] == "off" and be.opened == []
    r = a.start_multicolor("music", [[255, 0, 0]], [0, 0, 0], 80, 50)
    assert r["ok"] is True
    assert _wait(lambda: a.music_status()["state"] == "listening")
    st = a.music_status()
    assert set(st) == KEYS and st["device"] == "Speakers A"
    assert a.stop_multicolor()["ok"] is True
    assert be.streams[0].closed and not a._music.running()
    assert a.music_status()["state"] == "off"


def test_other_effects_never_open_the_audio_device():
    be = FakeBackend()
    a = _api(be)
    for mode in ("wave", "reactive", "pressure", "rain"):
        a.start_multicolor(mode, [[255, 0, 0]])
    time.sleep(0.05)
    a.stop_multicolor()
    assert be.opened == [] and be.entered == 0


def test_switching_from_music_to_another_effect_stops_listening():
    be = FakeBackend()
    a = _api(be)
    a.start_multicolor("music", [[255, 0, 0]])
    assert _wait(lambda: be.opened == ["spk-a"])
    a.start_multicolor("wave", [[255, 0, 0]])
    assert not a._music.running() and be.streams[0].closed
    a.stop_multicolor()


def test_a_music_zone_listens_too():
    be = FakeBackend()
    a = _api(be)
    r = a.start_zones([{"codes": ["Q", "W"], "mode": "music", "colors": [[0, 255, 0]]},
                       {"codes": ["A"], "mode": "wave", "colors": [[0, 0, 255]]}])
    assert r["ok"] is True
    assert _wait(lambda: a.music_status()["state"] == "listening")
    a.stop_multicolor()
    assert not a._music.running()


def test_missing_dependencies_still_run_the_effect_and_say_why():
    be = FakeBackend()
    a = _api(be, available=(False, "Music visualizer needs the numpy and soundcard packages (not installed)."))
    assert a.start_multicolor("music", [[255, 0, 0]])["ok"] is True
    assert a.fx.is_running() and be.entered == 0
    st = a.music_status()
    assert st["available"] is False and "numpy and soundcard" in st["reason"]
    a.stop_multicolor()


def test_status_never_raises():
    a = _api(FakeBackend())

    class Boom:
        def status(self):
            raise RuntimeError("bad state")
    a._music = Boom()
    r = a.music_status()
    assert r["ok"] is False and "bad state" in r["error"]


def test_every_engine_gets_the_source():
    for fn in (app_web.Api.__init__, app_web.Api.select_board):
        assert "self._music_attach()" in inspect.getsource(fn), fn.__name__
    assert "self._music = music.MusicSource()" in inspect.getsource(app_web.Api.__init__)
    a = _api(FakeBackend())
    a.fx = effects.PerKeyEffectEngine(a.km, lambda f: None)
    a._music_attach()
    assert a.fx.music is a._music
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_music_api.py -q -p no:cacheprovider`
Expected: FAIL with `AttributeError: 'Api' object has no attribute '_music_attach'` / `'music_status'`.

- [ ] **Step 3: Implement in `app_web.py`** (no other behaviour changes):
- Imports: add `import music` after `import overlays`.
- `__init__`: directly after the existing `self._ov_attach()` line (just before `self._games = self._make_games()`) add:

```python
        # Music visualizer (music.py): one capture source for the app's
        # lifetime; the engine starts it only while a "music" zone runs.
        self._music = music.MusicSource()
        self._music_attach()
```

- `select_board`: directly after its `self._ov_attach()` add `self._music_attach()` (the new board's engine gets the source; the old engine was already stopped by the `stop_multicolor` teardown, which stopped the capture).
- New methods directly above `def get_overlays(self):`:

```python
    # ---- music visualizer (Phase 7) ----
    def _music_attach(self):
        """Hand the app's MusicSource to the current engine (a new engine is
        built per board)."""
        fx = getattr(self, "fx", None)
        if fx is not None:
            fx.music = getattr(self, "_music", None)

    def music_status(self):
        """{ok, available, reason, state, device} for the Lighting tab. Never
        opens an audio device (availability is a find_spec check); state is
        off | starting | listening | no_device | error | unavailable."""
        try:
            src = getattr(self, "_music", None)
            if src is None:
                ok, reason = music.availability()
                return {"ok": True, "available": ok, "reason": reason,
                        "state": "off" if ok else "unavailable", "device": None}
            return dict(src.status(), ok=True)
        except Exception as e:
            return self._fail(e)
```

- [ ] **Step 4: Run the tests and the Api suites**

Run: `<py> -m pytest tests/test_music_api.py tests/test_overlays_api.py tests/test_overlays_carrier.py tests/test_pressure_api.py tests/test_effects_stream.py -q -p no:cacheprovider`
Expected: all pass (`8` in `test_music_api.py`).

- [ ] **Step 5: Commit**

```bash
git add app_web.py tests/test_music_api.py
git commit -m "feat(api): music_status bridge; every engine gets the music source" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Register the effect and offer it in the UI

**Files:**
- Modify: `effects.py` (`_gens`), `ui/runtime_src/workspaces/lighting.jsx`, `ui/runtime_src/src/sections.jsx`
- Regenerated: `ui/index_runtime.html`, `ui/runtime_src/build/ws_lighting.js`, `ui/runtime_src/build/sections.js`
- Test: `tests/test_music_ui_sources.py` (create)

**Interfaces:**
- Consumes: `Api.music_status` (Task 5) through `ctx.apiCall`; the Phase 2 guard helpers `_list_ids`, `_read`, `_set_ids` (`tests/test_pressure_ui_sources.py`) and `_engine` (`tests/test_pressure_effect.py`).
- Produces: effect id `"music"` (label `Music`, icon `♫`) in the Lighting mode grid, Effect Zones, tray mini panel and Dashboard quick switch (both derive from `LIGHT_MODES`), dispatched as `start_multicolor("music", ...)`; `useMusicStatus(apiCall, active)` and `musicNoteOf(status)` in `lighting.jsx`.

- [ ] **Step 1: Write the failing tests** — `tests/test_music_ui_sources.py`:

```python
"""Phase 7 UI wiring guards for the "music" effect (JSX read as text). The
Phase 2 guards in test_pressure_ui_sources.py already pin HOST_FX_IDS to the
engine table and HOST_FX_FAST to PRESS_REACTIVE."""
import re

import effects
from test_pressure_effect import _engine
from test_pressure_ui_sources import _list_ids, _read, _set_ids


def _lighting():
    return _read("workspaces", "lighting.jsx")


def test_music_is_offered_in_every_effect_list():
    for rel in (("workspaces", "lighting.jsx"), ("src", "sections.jsx")):
        text = _read(*rel)
        assert "music" in _list_ids(text, "LIGHT_MODES"), rel
        assert "music" in _list_ids(text, "ZONE_MODES"), rel


def test_music_is_a_host_effect_but_not_press_reactive():
    assert "music" in _engine()._gens
    assert "music" in _set_ids(_lighting(), "HOST_FX_IDS")
    assert "music" not in effects.PRESS_REACTIVE
    assert "music" not in _set_ids(_lighting(), "HOST_FX_FAST")


def test_music_previews_as_a_wave():
    assert re.search(r'pattern === "music"\) return "wave"', _lighting())


def test_mode_picker_shows_music_availability_without_hiding_it():
    text = _lighting()
    assert 'apiCall("music_status")' in text
    assert "useMusicStatus(ctx.apiCall, pattern === \"music\")" in text
    assert "disabled={musicOff}" in text
    assert "title={musicOff ? musicSt.reason" in text
    assert "data-music-note" in text


def test_music_status_poll_is_cleaned_up():
    text = _lighting()
    body = text[text.index("function useMusicStatus"):text.index("const musicNoteOf")]
    assert "setInterval(load, MUSIC_POLL_MS)" in body and "clearInterval(id)" in body
    assert "alive = false" in body
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_music_ui_sources.py -q -p no:cacheprovider`
Expected: 5 FAIL.

- [ ] **Step 3: Register the generator.** In `effects.py` `_gens`, change `"autorip": self._g_autorip,` to `"autorip": self._g_autorip, "music": self._g_music,`. (This alone makes `tests/test_pressure_ui_sources.py::test_host_fx_ids_equal_the_engine_generators` fail until Step 4 adds `"music"` to `HOST_FX_IDS`: commit them together.)

- [ ] **Step 4: Edit the JSX** (CRLF files; use a Python replace script if the Edit tool cannot match).

`ui/runtime_src/src/sections.jsx` and `ui/runtime_src/workspaces/lighting.jsx`, both:
- `LIGHT_MODES`: after the `tide` entry insert `  { id: "music",    label: "Music",         icon: "♫" },` (before `custom`).
- `ZONE_MODES`: change the line `  { id: "tide", label: "Tide" },` to `  { id: "tide", label: "Tide" }, { id: "music", label: "Music" },`.

`ui/runtime_src/workspaces/lighting.jsx` only:
- In the block comment above `HOST_ENGINE_TARGET_FPS`, after the line `                     frenzy, comet, tide` add `     audio-reactive: music (system audio, not press-reactive: no ≈ marker)`.
- `HOST_FX_IDS`: change `  "pressure", "rain", "comet", "tide",` to `  "pressure", "rain", "comet", "tide", "music",`. Leave `HOST_FX_FAST` unchanged (Design decision 9).
- `previewKindFor`: the wave line ends `|| pattern === "comet" || pattern === "music") return "wave";`.
- Directly above `function ModePickerWidget(ctx) {` insert:

```jsx
/* Music visualizer availability (Phase 7). One music_status call on mount,
   then every 2 s while Music is the selected effect. null = no bridge or no
   answer yet: treated as available (a missing bridge never blocks a mode). */
const MUSIC_POLL_MS = 2000;
function useMusicStatus(apiCall, active) {
  const [st, setSt] = useState(null);
  useEffect(() => {
    if (!apiCall) return undefined;
    let alive = true;
    const load = () => apiCall("music_status").then(r => { if (alive) setSt(r && r.ok ? r : null); });
    load();
    const id = active ? setInterval(load, MUSIC_POLL_MS) : null;
    return () => { alive = false; if (id) clearInterval(id); };
  }, [apiCall, active]);
  return st;
}
/* The one line shown under the grid while Music is selected (text only). */
const musicNoteOf = (st) => {
  if (!st) return null;
  if (st.available === false || st.state === "no_device" || st.state === "error")
    return st.reason || "The music visualizer is unavailable.";
  if (st.state === "listening")
    return `Listening to ${st.device || "the default output"}. Audio is analysed in memory only, never recorded.`;
  if (st.state === "starting") return "Starting audio capture…";
  return "Follows this PC's default audio output while the keyboard is connected.";
};
```

- In `ModePickerWidget`, after `const fpsCap = !firmwareOnly ? hostFpsLimited(bl) : null;` add:

```jsx
  // Music visualizer: never hidden; disabled with the reason when it cannot run.
  const musicSt = useMusicStatus(ctx.apiCall, pattern === "music");
  const musicNote = pattern === "music" ? musicNoteOf(musicSt) : null;
```

- In the grid's `modeGrid.map`, after `const degraded = fpsCap != null && HOST_FX_FAST.has(m.id);` add `            const musicOff = m.id === "music" && !!musicSt && musicSt.available === false;`; the `<button` opening becomes `<button key={m.id} onClick={() => setPattern(m.id)} disabled={musicOff}`; its `title=` becomes ``title={musicOff ? musicSt.reason : degraded ? `Press-reactive — ${boardName} sustains ~${fpsCap} fps, so this effect will look choppy` : undefined}``; its `style=` becomes `style={ active ? { background: "var(--accent-gradient, var(--accent))" } : (musicOff ? { opacity: 0.4, cursor: "not-allowed" } : {}) }>`.
- Directly before `        {firmwareOnly && (` (just after the grid's closing `</div>`) insert:

```jsx
        {musicNote && (
          <div data-music-note className="mt-2 font-mono text-[10px] text-[var(--text-faint)] leading-relaxed">{musicNote}</div>
        )}
```

- [ ] **Step 5: Build and keep only real diffs**

Run: `<py> ui\runtime_src\build_runtime.py`
Expected: ends with `Wrote ...index_runtime.html  (NNNN KB)`, no Babel error.
Run: `git diff --ignore-cr-at-eol --stat` — expected: `effects.py`, the two `.jsx`, `ui/index_runtime.html`, `ui/runtime_src/build/sections.js`, `ui/runtime_src/build/ws_lighting.js`. Every other build file listed by plain `git diff --stat` is line-ending noise: `git checkout -- <file>`.
Run: `node --check ui/runtime_src/build/ws_lighting.js` and `node --check ui/runtime_src/build/sections.js` — no output.
Run: `git grep -n "dangerouslySetInnerHTML\|innerHTML" -- ui/runtime_src/workspaces/lighting.jsx ui/runtime_src/src/sections.jsx` — no output.

- [ ] **Step 6: Run the tests**

Run: `<py> -m pytest tests/test_music_ui_sources.py tests/test_pressure_ui_sources.py tests/test_ui_sources.py tests/test_tray.py tests/test_dashboard_ui_sources.py tests/test_music_effect.py -q -p no:cacheprovider`
Expected: all pass (`5` new).

- [ ] **Step 7: Commit**

```bash
git add effects.py ui/runtime_src/workspaces/lighting.jsx ui/runtime_src/src/sections.jsx ui/index_runtime.html ui/runtime_src/build/ws_lighting.js ui/runtime_src/build/sections.js tests/test_music_ui_sources.py
git commit -m "feat(ui): Music effect in every lighting list, with availability and device line" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Docs, full suite, status

**Files:**
- Modify: `CLAUDE.md`, `docs/superpowers/roadmap-status.md`

- [ ] **Step 1: CLAUDE.md.** Under `## Architecture` add a bullet after `effects.py`: "`music.py` — Phase 7 music visualizer: WASAPI loopback of the default output (soundcard) -> 1024-pt FFT (numpy) -> 14 log bands 40 Hz-16 kHz -> auto-gain levels + energy-flux beats. Windows only; numpy/soundcard are imported lazily on the capture thread; without them `music_status()` says why and the effect idles. The engine starts/stops `MusicSource` with the zones (capture runs only while a `music` zone runs). Audio is processed in memory only." In the `## Effects` paragraph add: "**Music** = 14 band columns, height over the rows, palette bottom->top, background pulse on beats (not press-reactive: not in `PRESS_REACTIVE`/`HOST_FX_FAST`)."

- [ ] **Step 2: Full suite**

Run: `<py> -m pytest -q -p no:cacheprovider`
Expected: `1175 passed, 17 skipped` (1107 + 68, 14 + 3).

- [ ] **Step 3: Commit docs**

```bash
git add CLAUDE.md
git commit -m "docs: record the Phase 7 music visualizer" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Status entry.** Insert your entry ABOVE `## Waiting on the user` in `docs/superpowers/roadmap-status.md` (<= 15 lines: commits, decisions, gotchas). The planner already queued the Phase 7 user bullets in that section; add only new ones. Commit `docs(status): phase 7 implemented`.

---

## Hardware and audio checks (for the user; orchestrator copies them to `docs/HARDWARE_TEST_CHECKLIST.md` under `## Roadmap 2026-11-04`)

Before: install the two deps into the build venv (no network overnight): `venv-web\Scripts\pip install "numpy>=1.26" "soundcard>=0.4.3"`, then `venv-web\Scripts\python -m pytest tests/test_music_source.py -q` — the 3 numpy tests now run and must pass (`13 passed`).

1. **Availability.** Launch Aether from source. Lighting > Mode Picker: the Music tile is enabled (before installing the deps it is dimmed and its tooltip says "Music visualizer needs the numpy and soundcard packages (not installed).").
2. **Bars.** Connect, play music, select Music: 14 columns follow the spectrum (bass on the left), height across the 5 rows, palette bottom->top; the note under the grid reads "Listening to <your output device>. …".
3. **Beat pulse.** With a track that has a clear kick, unlit keys flash toward the first palette colour on the beats and fade within ~0.3 s; a steady pad/sine produces no pulses.
4. **Latency (< 60 ms).** Play a metronome/click track (e.g. 120 BPM): the pulse should look locked to the clicks. Optional: film the keyboard + speaker in phone slow-motion (240 fps) and count frames between the click and the flash (<= 14 frames).
5. **CPU (< 5 % of one core).** Task Manager > Details > AetherHE.exe: compare CPU with Wave vs Music running (the difference is the music cost; Task Manager shows % of ALL logical processors, so on 16 threads 5 % of one core is ~0.3 %).
6. **Silence.** Pause playback: the bars fall to dark within ~1 s and nothing stays lit; resume: they come back.
7. **Output switch.** While Music runs, change the default output (plug headphones or pick another device in Windows sound settings): bars resume from the new device within ~2 s and the note shows its name.
8. **No device.** Disable every output device (Sound settings) while Music runs: note says "No audio output device found." and the bottom row breathes; re-enable one: bars return.
9. **Capture stops.** Switch to Wave, then to a firmware effect (e.g. Static): CPU drops back to the Wave/Static baseline (no capture thread left running). Disconnect while Music runs: same.
10. **Speed/palette edits.** Drag the speed slider and change colours while Music runs: no stall; higher speed makes bars fall faster.
11. **Overlays.** Turn on the CPU overlay (Phase 6) with Music running: the number row shows the CPU bar over the music bars; turning it off restores the bars.
12. **Tray + Dashboard.** Pick Music from the tray mini panel and from the Dashboard lighting tile: it starts the same way.
13. **Frozen build (Phase 8).** After installing the deps, build with PyInstaller: in the frozen app Music works. If the note says "Audio capture failed: …mediafoundation…", the soundcard data files were not bundled (`collect_data_files("soundcard")` in `AetherHE.spec`).
14. **Size (veto input).** Compare `dist\AetherHE` folder size and the Inno Setup installer before/after the deps (expect roughly +25-40 MB unpacked, mostly numpy's OpenBLAS, and +10-15 MB installer; estimate, not measured).
