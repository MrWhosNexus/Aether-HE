(() => {
/* ============================================================
   AdvancedKeys — MINI 60 HE PRO advanced key types + plain remap.

   ADDITIVE ONLY. Nothing in this file runs on the Aula Win60 HE:
   `advancedKeysGate()` returns show:false for that board (and for the
   no-board / plain-browser fail-open path), so socd.jsx renders its
   original widgets byte-for-byte unchanged.

   WHAT THIS SURFACES
   ------------------
   The MINI 60 HE PRO keeps EVERY key binding — plain remap and all five
   advanced key types — in one 512-byte key table (GET 0x12 / SET 0x22,
   126 x 4-byte records indexed by MATRIX position). The Fn layer is a
   second, identically formatted table (0x16 / 0x26). A record is
   [pageType, p1, p2, p3]:

     pageType  2  REMAP  [02, modmask, hidUsage, 00]
     pageType  8  DKS    [08, dksSlot,  00, 00]  + 1024-byte travel table (0x18/0x28)
     pageType  9  MT     [09, tapHid, holdHid, delayRaw]
     pageType 10  TGL    [0A, hidUsage, 00, 00]
     pageType 11  SOCD   [0B, mode, hidA, hidB]   written to BOTH keys of the pair
     pageType 12  RS     [0C, 00,   hidA, hidB]   written to BOTH keys of the pair

   PROVENANCE (docs/context/issue-6-mini60-pro-raw/)
     CAPTURED  = byte-matched against a real frame in the 2.4GHz / wired
                 WebHID captures (FULL_APP_CAPTURE_NOTES.md §3,
                 analyze_advkeys.py output).
     SOURCE    = read from the vendor's own bundle (HFD_SDK_DECODE.md §5)
                 and NEVER seen on the wire. Shown, never trusted.

   WRITE PATH: app_web.py now exposes the bridge — set_key_remap,
   set_advanced_socd / _rs / _mt / _tgl, clear_advanced_key and
   read_key_records — each resolving design codes to firmware key indices
   through the active board's keymap and refusing loudly if that resolution
   fails (an unbound record reads back all-zero, so a table cannot be searched
   for "the key that sends 0x04"; writing to a guessed slot is not an option).
   The driver underneath does strict read-modify-write and aborts before any
   write if the read fails.

   WRITE_PATH_EXISTS below is the single switch. It is ON. What is still
   disabled is disabled on evidence, not plumbing: DKS (its action slots are
   authored by physically pressing keys in the vendor app and the encoding is
   undecoded) and the three SOCD modes never observed on the wire.

   Exposes window.AetherAdvancedKeys = {
     advancedKeysGate, AdvancedKeyEditor, AdvancedKeyStatus,
     AdvancedKeyBindings, CompetitiveWarning, ADV_TYPES, HID_KEYS
   }.
   ============================================================ */

const { useState, useEffect } = React;

/* ---- the one switch: is there a backend that can write the key table? ---- */
const WRITE_PATH_EXISTS = true;    // app_web.py Api: set_key_remap / set_advanced_* / clear_advanced_key

/* Boards whose advanced keys are decoded from a real capture but whose
   registry entry does not (yet) carry an `advancedKeys` flag. The registry is
   owned elsewhere; when it declares the flag, the flag wins and this list is
   never consulted. Matching a slug here yields "wip" — surfaced, never driven. */
const CAPTURED_ADV_SLUGS = /^aula-mini60he-pro(-24g)?$/;

/* ============================================================
   Capability gate
   ============================================================ */
function advancedKeysGate(board) {
  const b = board || {};
  const raw = typeof b.cap === "function" ? b.cap("advancedKeys") : undefined;
  const slug = (b.board && b.board.slug) || "";
  let state, source;

  if (raw !== undefined) {
    state = b.capState("advancedKeys");            // "yes" | "wip" | "no"
    source = "registry";
  } else if (CAPTURED_ADV_SLUGS.test(slug)) {
    state = "wip";                                 // decoded on the wire, not wired up
    source = "capture";
  } else {
    // Flag absent AND board unknown to us -> behave exactly like today.
    state = b.capabilities ? "no" : "unknown";
    source = "registry";
  }

  return {
    state,
    source,
    show: state === "yes" || state === "wip",
    drivable: state === "yes" && !!b.drivable && WRITE_PATH_EXISTS,
    reason: !WRITE_PATH_EXISTS
      ? "No write path yet: the driver can build these records, but no bridge method exposes it to the UI — nothing on this panel is sent to the keyboard."
      : state === "wip"
        ? "Capability is marked work-in-progress in the board registry — read-only."
        : "",
  };
}

/* ============================================================
   HID usage codes (USB HID Keyboard/Keypad page 0x07)
   Cross-checked against the capture: SOCD pair wrote 04/07 (A/D),
   RS pair wrote 14/08 (Q/E).
   ============================================================ */
const HID_KEYS = [];
"ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("").forEach((c, i) => HID_KEYS.push([c, 0x04 + i]));
[["1", 0x1e], ["2", 0x1f], ["3", 0x20], ["4", 0x21], ["5", 0x22], ["6", 0x23],
 ["7", 0x24], ["8", 0x25], ["9", 0x26], ["0", 0x27],
 ["Enter", 0x28], ["Esc", 0x29], ["Back", 0x2a], ["Tab", 0x2b], ["Space", 0x2c],
 ["-_", 0x2d], ["=+", 0x2e], ["[{", 0x2f], ["]}", 0x30], ["\\|", 0x31],
 [";:", 0x33], ["'\"", 0x34], ["`~", 0x35], [",<", 0x36], [".>", 0x37], ["/?", 0x38],
 ["Caps", 0x39],
 ["F1", 0x3a], ["F2", 0x3b], ["F3", 0x3c], ["F4", 0x3d], ["F5", 0x3e], ["F6", 0x3f],
 ["F7", 0x40], ["F8", 0x41], ["F9", 0x42], ["F10", 0x43], ["F11", 0x44], ["F12", 0x45],
 ["PrtSc", 0x46], ["ScrLk", 0x47], ["Pause", 0x48], ["Ins", 0x49], ["Home", 0x4a],
 ["PgUp", 0x4b], ["Del", 0x4c], ["End", 0x4d], ["PgDn", 0x4e],
 ["Right", 0x4f], ["Left", 0x50], ["Down", 0x51], ["Up", 0x52],
 ["L-Ctrl", 0xe0], ["L-Shift", 0xe1], ["L-Alt", 0xe2], ["L-Win", 0xe3],
 ["R-Ctrl", 0xe4], ["R-Shift", 0xe5], ["R-Alt", 0xe6], ["R-Win", 0xe7],
].forEach(p => HID_KEYS.push(p));

const HID_BY_CODE = {};
HID_KEYS.forEach(([label, code]) => { HID_BY_CODE[code] = label; });
const hidLabel = (code) => (code ? (HID_BY_CODE[code] || "?") : "—");
const hex2 = (n) => (n & 0xff).toString(16).toUpperCase().padStart(2, "0");

/* ============================================================
   SOCD behaviour modes.
   The vendor's own SOCDOptions list carries FOUR values (3, 1, 2, 4) whose
   labels are i18n keys that are not present in the unpacked bundle. Exactly
   ONE of them — 0x03 — was ever seen on the wire. The other three are listed
   so the user knows they exist, and are NOT selectable.
   ============================================================ */
const SOCD_MODES = [
  { v: 0x03, label: "Key 1 priority", verified: true,
    note: "The one mode proven on the wire: the vendor's \"Key 1 Priority\" wrote 0B 03 04 07 into BOTH keys of the pair (indices 49 and 51)." },
  { v: 0x01, label: "Undecoded mode", verified: false,
    note: "The vendor's list holds four values (3, 1, 2, 4) and its UI shows four labels (last input / key 1 priority / key 2 priority / neutralize). Only the 0x03 pairing was captured; which label 0x01 carries is not decoded." },
  { v: 0x02, label: "Undecoded mode", verified: false,
    note: "A separate wired session did write 0x02 for a pair the vendor UI called \"absolute button 2 priority\", but that single unlabelled-in-code observation is not enough to publish a behaviour, so Aether does not offer it." },
  { v: 0x04, label: "Undecoded mode", verified: false,
    note: "Present in the vendor's value list, never captured, behaviour not decoded." },
];

const ADV_TYPES = [
  { id: "remap", page: 2,  name: "Remap",  blurb: "Plain key remap — one HID usage code." },
  { id: "socd",  page: 11, name: "SOCD",   blurb: "Two keys + behaviour mode. Same record written to BOTH keys." },
  { id: "rs",    page: 12, name: "RS",     blurb: "Rapid SOCD / snap keys — two keys, deeper press wins." },
  { id: "mt",    page: 9,  name: "MT",     blurb: "Mod-tap: hold vs tap on one key, plus a trigger-delay byte." },
  { id: "tgl",   page: 10, name: "TGL",    blurb: "Toggle on/off on one key. No parameters." },
  { id: "dks",   page: 8,  name: "DKS",    blurb: "Up to 4 actions on one key by press depth + a travel table." },
];

/* ============================================================
   Local (host-side) binding store — shared by the three widgets, which are
   independent widget frames and cannot share App state (app.jsx is owned
   elsewhere). Nothing here is persisted or transmitted.
   ============================================================ */
const store = { bindings: [], sel: null, listeners: new Set(), seq: 1 };
const emit = () => store.listeners.forEach(fn => { try { fn(); } catch (e) {} });
const useStore = () => {
  const [, force] = useState(0);
  useEffect(() => {
    const fn = () => force(n => n + 1);
    store.listeners.add(fn);
    return () => store.listeners.delete(fn);
  }, []);
  return store;
};
const addBinding = (b) => {
  b.id = "B" + (store.seq++);
  store.bindings = store.bindings.concat([b]);
  store.sel = b.id;
  emit();
};
const removeBinding = (id) => {
  store.bindings = store.bindings.filter(b => b.id !== id);
  if (store.sel === id) store.sel = store.bindings.length ? store.bindings[0].id : null;
  emit();
};
const selectBinding = (id) => { store.sel = id; emit(); };

/* Compose the 4-byte key-table record for a draft binding. */
function recordFor(d) {
  switch (d.type) {
    case "remap": return [0x02, d.mod & 0xff, d.hidA & 0xff, 0x00];
    case "dks":   return [0x08, d.slot & 0xff, 0x00, 0x00];
    case "mt":    return [0x09, 0x00, 0x00, d.delayRaw & 0xff];
    case "tgl":   return [0x0a, 0x00, 0x00, 0x00];
    case "socd":  return [0x0b, d.mode & 0xff, d.hidA & 0xff, d.hidB & 0xff];
    case "rs":    return [0x0c, 0x00, d.hidA & 0xff, d.hidB & 0xff];
    default:      return [0, 0, 0, 0];
  }
}
const recordHex = (d) => recordFor(d).map(hex2).join(" ");

/* ============================================================
   Small presentational helpers
   ============================================================ */
const Label = ({ children }) => (
  <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--text-faint)] mb-1">{children}</div>
);

const Note = ({ tone = "dim", children }) => (
  <div className={`text-[10.5px] leading-relaxed ${
    tone === "warn" ? "text-amber-300/90" : tone === "bad" ? "text-rose-300/90" : "text-[var(--text-dim)]"}`}>
    {children}
  </div>
);

const Tag = ({ kind }) => {
  const map = {
    captured: ["Captured", "border-emerald-400/30 bg-emerald-500/10 text-emerald-300"],
    source:   ["Source only", "border-amber-400/30 bg-amber-500/10 text-amber-300"],
    unknown:  ["Not decoded", "border-rose-400/30 bg-rose-500/10 text-rose-300"],
  };
  const [text, cls] = map[kind] || map.unknown;
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono uppercase tracking-[0.18em] border ${cls}`}>
      {text}
    </span>
  );
};

/* The competitive-play warning the vendor's own UI carries. Real user-harm
   issue: shown wherever SOCD or RS is exposed. */
function CompetitiveWarning({ compact }) {
  return (
    <div className="rounded-md border border-rose-400/40 bg-rose-500/[0.07] p-3">
      <div className="font-display text-[10.5px] uppercase tracking-[0.18em] text-rose-300 mb-1">
        Competitive-play warning
      </div>
      <div className="text-[10.5px] leading-relaxed text-rose-200/90">
        SOCD / snap-tap style key resolution is <span className="font-semibold">restricted or banned</span> by
        some competitive games — the vendor's own driver names <span className="font-mono">CS2</span> explicitly
        and warns that using it can get your account banned.
        {!compact && " Aether repeats that warning rather than hiding it: enabling SOCD or RS is your call and your risk."}
      </div>
    </div>
  );
}

/* Compact HID key picker. */
const HidPicker = ({ title, value, onPick }) => {
  const [open, setOpen] = useState(false);
  const IChevronD = window.AetherIcons && window.AetherIcons.IChevronD;
  return (
    <div>
      <button onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 mb-1.5 text-[var(--text-dim)] hover:text-[var(--text)]">
        {IChevronD && <IChevronD size={12} className={open ? "" : "-rotate-90"}/>}
        <span className="font-display text-[11px] uppercase tracking-[0.18em]">{title}</span>
        <span className="font-mono text-[11px] text-[var(--accent)]">
          {hidLabel(value)}{value ? ` · 0x${hex2(value)}` : ""}
        </span>
      </button>
      {open && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(46px,1fr))] gap-1.5 mb-2">
          {HID_KEYS.map(([label, code]) => (
            <button key={label} onClick={() => { onPick(code); setOpen(false); }}
              className={`h-8 rounded-md border font-mono text-[10.5px] transition-all
                          ${value === code
                            ? "border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--accent)] shadow-[0_0_12px_var(--accent-glow)]"
                            : "border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] hover:text-[var(--text)]"}`}>
              {label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

/* ============================================================
   Editor widget body (replaces the Win60 pair editor ONLY on a board that
   declares the capability).
   ============================================================ */
function AdvancedKeyEditor({ ctx, gate }) {
  const [type, setType] = useState("socd");
  const [keyIndex, setKeyIndex] = useState(49);
  const [keyIndexB, setKeyIndexB] = useState(51);
  const [hidA, setHidA] = useState(0x04);
  const [hidB, setHidB] = useState(0x07);
  const [mode, setMode] = useState(0x03);
  const [delayRaw, setDelayRaw] = useState(40);
  const [slot, setSlot] = useState(0);
  useStore();

  const draft = { type, keyIndex, keyIndexB, hidA, hidB, mode, delayRaw, slot };
  const def = ADV_TYPES.find(t => t.id === type) || ADV_TYPES[0];
  const isPair = type === "socd" || type === "rs";

  const stage = () => addBinding(Object.assign({}, draft, { rec: recordFor(draft) }));

  return (
    <div className="flex flex-col gap-3.5 h-full overflow-y-auto">
      {/* capability header */}
      <div className="rounded-md border border-amber-400/35 bg-amber-500/[0.06] p-3">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-display text-[10.5px] uppercase tracking-[0.18em] text-amber-300">
            Advanced keys · unverified
          </span>
          <Tag kind={gate.state === "yes" ? "captured" : "source"}/>
        </div>
        <Note tone="warn">
          {(ctx && ctx.board && ctx.board.name) || "This board"} exposes its key bindings through one
          512-byte key table (GET <span className="font-mono">0x12</span> / SET <span className="font-mono">0x22</span>,
          126 records of 4 bytes, indexed by matrix position; the Fn layer is a second table on
          <span className="font-mono"> 0x16/0x26</span>). Every type below rides that table.
          <div className="mt-1.5 text-rose-300/90">{gate.reason}</div>
        </Note>
      </div>

      {/* type selector */}
      <div className="grid grid-cols-3 gap-1.5">
        {ADV_TYPES.map(t => (
          <button key={t.id} onClick={() => setType(t.id)}
            className={`flex flex-col items-start px-2.5 py-1.5 rounded-md border transition-all
                        ${type === t.id
                          ? "border-[var(--accent)]/50 bg-[var(--accent)]/10 text-[var(--accent)] shadow-[0_0_10px_var(--accent-glow)]"
                          : "border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"}`}>
            <span className="font-display text-[11px] uppercase tracking-[0.16em]">{t.name}</span>
            <span className="font-mono text-[9px] text-[var(--text-faint)]">page {t.page}</span>
          </button>
        ))}
      </div>
      <Note>{def.blurb}</Note>

      {/* target key index(es) — the record is addressed by MATRIX index */}
      <div className="flex items-end gap-3">
        <div className="flex-1">
          <Label>{isPair ? "Key 1 · table index" : "Key · table index"}</Label>
          <input type="number" min={0} max={125} value={keyIndex}
            onChange={e => setKeyIndex(Math.max(0, Math.min(125, +e.target.value || 0)))}
            className="w-full h-9 px-2 rounded-md border border-[var(--line)] bg-white/[0.02] font-mono text-[13px] text-[var(--text)]"/>
        </div>
        {isPair && (
          <div className="flex-1">
            <Label>Key 2 · table index</Label>
            <input type="number" min={0} max={125} value={keyIndexB}
              onChange={e => setKeyIndexB(Math.max(0, Math.min(125, +e.target.value || 0)))}
              className="w-full h-9 px-2 rounded-md border border-[var(--line)] bg-white/[0.02] font-mono text-[13px] text-[var(--text)]"/>
          </div>
        )}
      </div>
      <Note>
        Records are indexed by <span className="text-[var(--text)]">matrix</span> position, not by on-screen key
        order (16-column stride; row bases 0/16/32/48/64/80). The index is entered directly here because
        Aether's key picker for this board maps design codes, not matrix slots.
      </Note>

      {/* ---- per-type parameters ---- */}
      {type === "remap" && (
        <div className="p-3 rounded-md border border-[var(--line)] bg-[rgba(5,11,14,0.5)] flex flex-col gap-2">
          <HidPicker title="HID usage" value={hidA} onPick={setHidA}/>
          <Note>
            Byte 1 of a remap record is a modifier bitmask (a modifier-only entry
            <span className="font-mono"> 02 40 00 00</span> exists in the stock Fn table). Aether composes it as
            <span className="font-mono"> 0x00</span> here — the mask bit order was never exercised in the capture.
            <Tag kind="captured"/> record shape · <Tag kind="source"/> modifier bit order
          </Note>
        </div>
      )}

      {(type === "socd" || type === "rs") && (
        <div className="p-3 rounded-md border border-[var(--line)] bg-[rgba(5,11,14,0.5)] flex flex-col gap-2.5">
          <HidPicker title="Key 1 HID" value={hidA} onPick={setHidA}/>
          <HidPicker title="Key 2 HID" value={hidB} onPick={setHidB}/>
          <Note>
            The pair is stored as HID usage codes inside the record, and the identical record is written into
            <span className="text-[var(--text)]"> both</span> keys' slots. <Tag kind="captured"/>
          </Note>

          {type === "socd" && (
            <div className="flex flex-col gap-1.5">
              <Label>Behaviour mode</Label>
              {SOCD_MODES.map(m => {
                const sel = mode === m.v;
                return (
                  <button key={m.v} disabled={!m.verified}
                    onClick={() => m.verified && setMode(m.v)}
                    className={`text-left px-3 py-2 rounded-md border transition-all
                                ${!m.verified
                                  ? "border-[var(--line)] bg-white/[0.01] opacity-60 cursor-not-allowed"
                                  : sel
                                    ? "border-[var(--accent)]/50 bg-[var(--accent)]/10 shadow-[0_0_10px_var(--accent-glow)]"
                                    : "border-[var(--line)] bg-white/[0.02] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"}`}>
                    <div className="flex items-center gap-2">
                      <span className={`font-mono text-[11px] ${m.verified ? "text-[var(--accent)]" : "text-[var(--text-faint)]"}`}>
                        0x{hex2(m.v)}
                      </span>
                      <span className={`font-display text-[11px] uppercase tracking-[0.14em] ${m.verified ? "text-[var(--text)]" : "text-[var(--text-faint)]"}`}>
                        {m.label}
                      </span>
                      <Tag kind={m.verified ? "captured" : "unknown"}/>
                    </div>
                    <div className="mt-1 text-[10px] leading-relaxed text-[var(--text-dim)]">{m.note}</div>
                  </button>
                );
              })}
              <Note tone="warn">
                The vendor UI offers four modes. Aether offers the one that was actually observed. The other
                three are shown greyed out and are deliberately not selectable — presenting them as working
                would be a guess, and a wrong guess here silently changes which key wins in-game.
              </Note>
            </div>
          )}

          {type === "rs" && (
            <Note>
              RS carries no mode byte at all — byte 1 was <span className="font-mono">0x00</span> in every captured
              frame. Resolution is "deeper press wins", decided by the firmware. <Tag kind="captured"/>
            </Note>
          )}

          <CompetitiveWarning/>
        </div>
      )}

      {type === "mt" && (
        <div className="p-3 rounded-md border border-[var(--line)] bg-[rgba(5,11,14,0.5)] flex flex-col gap-2.5">
          <div>
            <Label>Trigger delay · raw byte</Label>
            <div className="flex items-center gap-3">
              <input type="range" min={0} max={255} value={delayRaw}
                onChange={e => setDelayRaw(+e.target.value)} className="flex-1"/>
              <span className="font-mono text-[13px] text-[var(--accent)] w-20 text-right">
                {delayRaw} · 0x{hex2(delayRaw)}
              </span>
            </div>
          </div>
          <Note tone="warn">
            Shown as the <span className="text-[var(--text)]">raw byte</span> on purpose. The only value ever
            captured on this board was <span className="font-mono">0x28</span> (40) — which is also the vendor's
            factory default, so it proves nothing about the unit. The vendor's own bundle describes the field as
            <span className="font-mono"> sliderValue / 10</span> (i.e. 10 ms per count, 40 → 400 ms), but that
            reading is <Tag kind="source"/> and was never confirmed against a value we chose. Aether will not
            print a millisecond figure it cannot stand behind.
          </Note>
          <Note>
            Bytes 1 and 2 are the tap and hold actions. They were <span className="font-mono">00 00</span> in every
            captured frame because the vendor UI fills them only after you physically press the key on the board.
            Aether therefore writes them as zero and does not offer an action picker. <Tag kind="unknown"/>
          </Note>
        </div>
      )}

      {type === "tgl" && (
        <div className="p-3 rounded-md border border-[var(--line)] bg-[rgba(5,11,14,0.5)]">
          <Note>
            Toggle takes no parameters: the captured record was exactly
            <span className="font-mono"> 0A 00 00 00</span>. <Tag kind="captured"/> The vendor bundle claims byte 1
            can hold a HID usage (<span className="font-mono">[10, hidUsage, 0, 0]</span>); that was never observed,
            so Aether composes the captured all-zero form. <Tag kind="source"/>
          </Note>
        </div>
      )}

      {type === "dks" && (
        <div className="p-3 rounded-md border border-[var(--line)] bg-[rgba(5,11,14,0.5)] flex flex-col gap-2.5">
          <div>
            <Label>DKS slot (byte 1)</Label>
            <input type="number" min={0} max={15} value={slot}
              onChange={e => setSlot(Math.max(0, Math.min(15, +e.target.value || 0)))}
              className="w-28 h-9 px-2 rounded-md border border-[var(--line)] bg-white/[0.02] font-mono text-[13px] text-[var(--text)]"/>
          </div>
          <div className="rounded-md border border-rose-400/40 bg-rose-500/[0.07] p-3">
            <div className="font-display text-[10.5px] uppercase tracking-[0.18em] text-rose-300 mb-1">
              DKS cannot be authored in Aether
            </div>
            <div className="text-[10.5px] leading-relaxed text-rose-200/90">
              DKS assigns up to four actions by how deep the key is pressed. In the vendor app those four action
              slots are filled by <span className="font-semibold">physically pressing the key on the keyboard</span>
              {" "}— the UI literally waits for the press. Aether has no such capture flow, and because the vendor
              capture never filled the slots, their encoding is undecoded. So Aether can show the record shape and
              the travel points, and nothing more: it will not ship a control that cannot produce a working DKS key.
            </div>
          </div>
          <Note>
            The companion travel table is a separate 1024-byte table
            (<span className="font-mono">0x18</span> / <span className="font-mono">0x28</span>), four points in
            0.1 mm units — press / bottom-out / release / reset. The one captured entry was
            <span className="font-mono"> 10 1E 1E 10</span> = 1.6 / 3.0 / 3.0 / 1.6 mm, written at offset 0, with
            byte 1 of the key record acting as the slot index into it. One entry is consistent with that reading
            but does not prove it. <Tag kind="captured"/> values · <Tag kind="source"/> slot indexing
          </Note>
        </div>
      )}

      {/* record preview */}
      <div className="rounded-md border border-[var(--line)] bg-[rgba(5,11,14,0.5)] p-3">
        <Label>Record that would be written</Label>
        <div className="font-mono text-[13px] text-[var(--accent)]">{recordHex(draft)}</div>
        <div className="mt-1 font-mono text-[10px] text-[var(--text-faint)]">
          key table 0x22 · index {keyIndex} (byte offset {keyIndex * 4})
          {isPair && <> + index {keyIndexB} (byte offset {keyIndexB * 4}) — same record</>}
        </div>
      </div>

      {/* staging (host-side only) */}
      <div className="flex gap-2">
        <button onClick={stage}
          className="flex-1 h-8 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] font-display text-[11px] uppercase tracking-[0.16em]">
          Stage binding
        </button>
        <button disabled title={gate.reason}
          className="flex-1 h-8 rounded-md border border-[var(--line)] bg-white/[0.01] text-[var(--text-faint)] opacity-60 cursor-not-allowed font-display text-[11px] uppercase tracking-[0.16em]">
          Write · unavailable
        </button>
      </div>
      <Note tone="bad">{gate.reason} Staged bindings live in this window only.</Note>
    </div>
  );
}

/* ============================================================
   Status widget body (replaces the Win60 hotkey widget on capable boards).
   ============================================================ */
function AdvancedKeyStatus({ ctx, gate }) {
  const board = (ctx && ctx.board) || null;
  return (
    <div className="flex flex-col gap-3 h-full overflow-y-auto">
      <div>
        <Label>Board</Label>
        <div className="font-mono text-[12px] text-[var(--text)]">{(board && board.name) || "—"}</div>
        <div className="font-mono text-[10px] text-[var(--text-faint)]">{(board && board.vidPid) || ""}</div>
      </div>

      <div className="rounded-md border border-[var(--line)] bg-[rgba(5,11,14,0.5)] p-3">
        <Label>Capability</Label>
        <div className="flex items-center gap-2">
          <span className="font-display text-[11px] uppercase tracking-[0.16em] text-[var(--text)]">
            advancedKeys
          </span>
          <Tag kind={gate.state === "yes" ? "captured" : "source"}/>
          <span className="font-mono text-[10px] text-[var(--text-faint)]">
            {gate.state} · from {gate.source}
          </span>
        </div>
        <div className="mt-2"><Note tone="bad">{gate.reason}</Note></div>
      </div>

      <CompetitiveWarning compact/>

      <div className="rounded-md border border-[var(--line)] bg-[rgba(5,11,14,0.5)] p-3">
        <Label>Transport</Label>
        <div className="font-mono text-[10.5px] text-[var(--text-dim)] leading-relaxed">
          key table GET 0x12 / SET 0x22 · 512 B · 126 x 4<br/>
          Fn layer GET 0x16 / SET 0x26 · same format<br/>
          DKS travel GET 0x18 / SET 0x28 · 1024 B<br/>
          writes are whole-table (read, patch, write back)
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   Staged-bindings widget body (replaces the Win60 active-pairs widget).
   ============================================================ */
function AdvancedKeyBindings({ ctx, gate }) {
  const s = useStore();
  const ITrash = window.AetherIcons && window.AetherIcons.ITrash;

  return (
    <div className="flex flex-col gap-3 h-full">
      <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--text-faint)]">
        {s.bindings.length} staged · 0 written
      </div>

      <div className="flex flex-col gap-1.5 flex-1 overflow-y-auto">
        {!s.bindings.length && (
          <Note>Nothing staged. Bindings composed here are held in this window and never sent to the keyboard.</Note>
        )}
        {s.bindings.map(b => {
          const def = ADV_TYPES.find(t => t.id === b.type) || ADV_TYPES[0];
          const pair = b.type === "socd" || b.type === "rs";
          return (
            <div key={b.id}
              onClick={() => selectBinding(b.id)}
              className={`px-3 py-2 rounded-md border cursor-pointer transition-all
                          ${s.sel === b.id
                            ? "border-[var(--accent)]/50 bg-[var(--accent)]/10 shadow-[0_0_10px_var(--accent-glow)]"
                            : "border-[var(--line)] bg-white/[0.02] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"}`}>
              <div className="flex items-center justify-between">
                <span className="font-display text-[11px] uppercase tracking-[0.16em] text-[var(--text)]">
                  {def.name} <span className="text-[var(--text-faint)]">· page {def.page}</span>
                </span>
                <button onClick={(e) => { e.stopPropagation(); removeBinding(b.id); }}
                  className="text-[var(--text-faint)] hover:text-rose-300" aria-label="Remove">
                  {ITrash ? <ITrash size={12}/> : "x"}
                </button>
              </div>
              <div className="mt-1 font-mono text-[10px] text-[var(--text-faint)]">
                idx {b.keyIndex}{pair ? ` + ${b.keyIndexB}` : ""}
                {pair ? ` · ${hidLabel(b.hidA)} / ${hidLabel(b.hidB)}` : ""}
                {b.type === "remap" ? ` · ${hidLabel(b.hidA)}` : ""}
                {b.type === "mt" ? ` · delay raw ${b.delayRaw}` : ""}
              </div>
              <div className="mt-0.5 font-mono text-[11px] text-[var(--accent)]">{recordHex(b)}</div>
            </div>
          );
        })}
      </div>

      <Note tone="bad">{gate.reason}</Note>
    </div>
  );
}

window.AetherAdvancedKeys = {
  advancedKeysGate, AdvancedKeyEditor, AdvancedKeyStatus, AdvancedKeyBindings,
  CompetitiveWarning, ADV_TYPES, HID_KEYS,
};
})();
