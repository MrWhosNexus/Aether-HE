# Draft reply for hallbyte on issue #7

> Use `gh issue comment 7 --body "@paste-the-text-below"` to post.
> One issue: only post after the user explicitly OKs it.

---

Hey hallbyte — close, but the log you've got is from `edge://device-log`,
and **that surface only logs OS-level hardware events** (USB hotplug, HID
enumeration, display changes, errors). It deliberately does **not** echo
WebHID API calls — that's why no `sendReport`/`outputReport` lines appear
even though the keyboard is connected.

For the protocol decode I need to see the bytes AULA HUB (or `magnet`)
actually sends to the board. Two ways to get that, both work — pick whichever
is less friction:

### Option A — Wireshark + USBPcap (manual, ~10 min)
1. Install USBPcap (https://desowin.org/usbpcap/) and start a capture on the
   right USBPcap port.
2. Open AULA HUB (or `https://use-magnet.com` in Edge), set a solid color,
   stop the capture.
3. Save the `.pcapng`, attach it here. **One trace is enough to unblock your
   board AND #5 Win60 HE Max** (you share vendor `1CA2`).

### Option B — AetherHE v0.3.0 in-app capture (read-only, faster)
1. Update to v0.3.0: https://github.com/MrWhosNexus/Aether-HE/releases/tag/v0.3.0
2. Open **Settings → Submit your board** → pick "Aula WIN 68 HE MAX".
3. The app reads the key matrix for ~30 s and packages a full submission.
   Read-only — never writes to a board whose protocol we haven't decoded.

Either way: one capture moves this to *layout-only → driveable* (lighting +
actuation), and since you share `1CA2` with #5, your trace will probably
unblock both boards at once.

Thanks for hanging in — the screenshots + photos you posted earlier already
confirmed the layout is right. Just need the protocol bytes.
