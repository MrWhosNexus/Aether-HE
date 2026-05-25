---
name: aula-win60-hidapi-usage-page-quirk
description: On this CachyOS box hidapi reports usage_page=0x0 for all Aula Win60 HE interfaces
metadata: 
  node_type: memory
  type: project
  originSessionId: a316dee9-22cd-462e-a496-f64bf0e96200
---

On the user's CachyOS machine, `hid.enumerate(0x2E3C, 0xC365)` returns `usage_page=0x0` and `usage=0x0` for all three Aula Win60 HE interfaces (a Linux hidraw/libusb quirk), even though the real report descriptor declares iface 2 as usage page `0xFF1B` / usage `0x91`.

Consequence: `find_vendor_interface()` in `aula_device.py` never matches the `0xFF1B` branch and falls back to `max(interface_number)` — which happens to be iface 2, the correct vendor interface. So it works, but detection-by-usage-page is effectively dead on this system; don't rely on it. Part of the [[aula-win60-protocol-capture]] work.
