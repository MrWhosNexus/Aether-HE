// Paste into the Aula web-driver Console (refresh the page first to clear old hooks).
// Then, on the Actuation -> Travel page:
//   1. Toggle "Travel Test" OFF then ON  -> note the SEND line(s) = enable command.
//   2. Tap W, A, S, D, Space ONE AT A TIME -> note each "KEY (a,b)" id.
// Paste back the SEND lines and the KEY lines.
(async () => {
  const hex = d => [...new Uint8Array(d.buffer ?? d)]
    .map(b => b.toString(16).padStart(2, '0')).join(' ');
  const orig = HIDDevice.prototype.sendReport;
  HIDDevice.prototype.sendReport = function (id, data) {
    const a = new Uint8Array(data.buffer ?? data);
    if (a[0] !== 0x01) console.log('SEND', hex(data));   // skip the 0x01 keep-alive poll
    return orig.call(this, id, data);
  };
  for (const dev of await navigator.hid.getDevices()) {
    dev.addEventListener('inputreport', ev => {
      const a = new Uint8Array(ev.data.buffer);
      if (a[0] === 0x21 && a[4] === 5) {                 // subtype-5 per-key travel
        const depth = (a[8] | (a[9] << 8)) / 100;
        if (depth > 0.4) console.log(`KEY (${a[6]},${a[7]}) ${depth.toFixed(2)}mm`);
      }
    });
  }
  console.log('✅ logger armed: toggle Travel Test, then tap W A S D Space one at a time');
})();
