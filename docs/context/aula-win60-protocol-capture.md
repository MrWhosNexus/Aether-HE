---
name: aula-win60-protocol-capture
description: How to reverse-engineer Aula Win60 HE config packets (used by the aula-win60-app project)
metadata: 
  node_type: memory
  type: project
  originSessionId: a316dee9-22cd-462e-a496-f64bf0e96200
---

Project `~/Projects/aula-win60-app` reverse-engineers the Aula Win60 HE keyboard's vendor HID protocol by capturing what the official **Aula WebHID driver** (a website running in Chrome) sends.

**Capture method (no root, no usbmon):** open the driver page in Chrome → DevTools Console → patch the HID send methods, then change one setting at a time and diff the logged packets:
```js
(() => {
  const hex = d => [...new Uint8Array(d.buffer ?? d)].map(b=>b.toString(16).padStart(2,'0')).join(' ');
  for (const fn of ['sendReport','sendFeatureReport']) {
    const orig = HIDDevice.prototype[fn];
    HIDDevice.prototype[fn] = function(id,data){ console.log(`${fn} id=0x${id.toString(16)} ${hex(data)}`); return orig.call(this,id,data); };
  }
})();
```
The driver also prints its own zh-CN debug strings (`颜色值: rgba(...)`, `light mode:N`) which label each packet.

**Why usbmon failed:** `CONFIG_USB_MON=m` but the running kernel's module dir was removed by a pending kernel upgrade (running 7.0.8, installed 7.0.9 + lts) — needs a reboot. The DevTools hook sidesteps it entirely.

**Confirmed so far:** vendor interface = iface 2 (usage page 0xFF1B, usage 0x91), Report ID `0x01`, 63-byte payloads. Commands are identified by the FIRST data byte (after the report-id): `0x01`=poll/keepalive (all-zero body), `0x07`=lighting, `0x17`=effect-select prelude, `0x21`(=33)=analog travel / actuation family.

Lighting cmd `0x07`: `[5]`=mode, `[6]`=brightness(inferred), `[8..10]`=RGB, `[14]`=direction. Encoded in `build_lighting()` in `aula_device.py`.

Analog travel reports (cmd `0x21`, streamed only when driver's **Travel Test** toggle is ON): subtype at data `[4]`. Subtype `5` = simple per-key travel: `[6],[7]`=key id, `[8],[9]`=depth 16-bit LE in **0.01mm units** (0..~400 = 0..4.00mm). Subtype `3` = detailed calibration (raw Hall ADC ~2535 rest .. ~1431 bottomed). Parsed by `parse_travel()`. STILL TBD: the Travel-Test *enable* command, and the key-id→name map (capture by toggling Travel Test + tapping keys individually). The `0x21 .. 18 02 ..` SEND is the actuation-write command (per-key trigger in 0.01mm).

See [[aula-win60-hidapi-usage-page-quirk]].
