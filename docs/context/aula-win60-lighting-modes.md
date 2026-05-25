---
name: aula-win60-lighting-modes
description: Definitive mapping of AULA WIN60 HE firmware lighting modes to physical/protocol bytes
metadata:
  type: reference
---

# Aula Win60 HE Verified Lighting Mode Mapping

The AULA WIN60 HE keyboard's built-in firmware supports exactly 14 active lighting modes. These are controlled via the `0x07` lighting Output packet, where the mode byte is sent at index 5.

### Verified Byte-to-Mode Mapping

- **`0`**: **Static** (Steady on, foreground color only)
- **`1`**: **Breath** (Breathing effect)
- **`2`**: **Wave** (Moving spectrum wave)
- **`3`**: **Neon** (Slow spectrum color-cycle)
- **`4`**: **Radar** (Circular radar sweep)
- **`6`**: **Reactive** (Lights up keys on press)
- **`7`**: **Aurora** (Flowing aurora light pattern)
- **`8`**: **Ripple** (Ripple outward from pressed key)
- **`9`**: **Twinkle** (Starlight twinkle)
- **`10`**: **Custom** (Per-key custom LED layout)
- **`11`**: **Cross** (Reactive cross-lines on press)
- **`12`**: **Speed Respond** (Lighting rate responsive to typing speed)
- **`14`**: **Auto Ripple** (Autonomous flowing ripples)
- **`15`**: **Striation** (Horizontal/vertical line sweeps)
- **`16`**: **Fireworks** (Spark/burst effects on press)
- **`100`**: **Musical Rhythm** (Sound-responsive lighting)

**Why:** The placeholder map in the prototype UI used incorrect placeholder byte indexes for modes (e.g., matching Breath to 5 and Reactive to 9, which caused buttons to set incorrect modes or fail entirely).

**How to apply:** Update the `MODE` dictionary in `app_web.py` to match this definitive list, ensuring the exact design buttons correctly map to the hardware firmware bytes. See [[aula-win60-webview-ui]].
