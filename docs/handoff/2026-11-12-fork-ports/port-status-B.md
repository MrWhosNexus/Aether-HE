# Port status, Agent B (stopped on request, 2026-11-12)

Worktree `ah-forkB`, branch `port/f75-sayo`, base `f38e69a`. Nothing pushed. Tree is clean.

## Commits

| Hash | Subject | State |
|---|---|---|
| `9a85149` | chore: remove session transcripts from the repo root | green |
| `0943199` | feat(f75): real 80-key AULA F75 HE layout and contributor read-back fixtures | green |
| `34aa94e` | feat(mini60): parse battery, work mode and firmware from the 0x10 reply | green |
| `f506cff` | feat(f75): drive the AULA F75 HE over cable and 2.4 GHz dongle | green |
| `2ebce23` | wip(f75): offer WIN 68 HE Max; udev, checklist, Sayo decode not done | **1 red test** |

## Test counts

Full suite at `2ebce23`, in the sandbox: **1641 passed, 26 skipped, 3 failed**.
Baseline `f38e69a`, same sandbox: 1575 passed, 26 skipped, 2 failed.

Failing:
- `tests/test_service_guard.py` (2 tests): sandbox port bind, expected, also fail on the baseline.
- `tests/test_magnet_driver.py::test_registry_dispatches_the_magnet_driver_and_withholds_it_from_the_picker`:
  **caused by `2ebce23`**. It asserts `p.offered is False` for `aula-win68he-max`. Agent A owns
  that file. Fix: line 53, change to `p.offered is True` and rename the test.

The full suite was run on the final tree content before it was split into commits. After the
split I re-ran only the seven affected test files at `f506cff` (465 passed, green) and at
`2ebce23` (464 passed, the one failure above). The commits `0943199` and `34aa94e` were not run
in isolation.

## Items

| Item | State | Notes |
|---|---|---|
| 3.5 session transcripts deleted | done | No references remained. |
| 3.1 layout | done | `ui/layouts/aula-f75he.json`. Checked key by key against the fixture key table: no index or usage mismatch, so no key was changed. Pinned in `tests/test_f75.py`. |
| 3.2 fixtures | done | `tests/fixtures/f75/`, with a provenance header. |
| 3.3 battery / work-mode parse | done (library + driver) | `pm.parse_device_status`, `Mini60Driver.device_status()` (dongle only, `None` wired). **Not exposed to the UI**: needs the `app_web.py` change below. |
| 3.4 F75 drivable, wired + dongle | done, per the owner override | Both offered, `status: bringup`, "COMMUNITY-TESTED (xpLayA read-backs)". Dead zone and macros gated behind `f75`. |
| 3.4 `f75` flag wiring | **in progress** | Driver side done and tested. `app_web.py` does not set it yet, so the flag cannot be turned on. |
| 3.4 `docs/HARDWARE_TEST_CHECKLIST.md` section | not started | |
| README F75 / Sayo prose | not started | Only the generated boards table is updated. |
| udev rules (`38a6:2729`, `0c45:fefe`) | **not started** | Linux users cannot open the F75 without them. |
| WIN 68 HE Max offered | in progress (`2ebce23`) | Registry, `boards.json`, README table done. Agent A's test must change. `port-status-A.md` did not exist when I stopped, so any field needs Agent A has are unapplied. |
| Sayo B1 + B2 (cmd-0x1C decode) | **not started** | Board stays NOT drivable: NullDriver, `actuation: false`, not offered. Only the registry `_note` wording was updated (in `f506cff`), and it already describes `build_key_analog` as existing. **That note is ahead of the code until B1 lands.** |
| Tri-Mode placeholder layout | checked, kept | `ui/layouts/aula-f75.json` is still referenced by `aula-f75-tri-mode` (a different board). |

## `app_web.py` changes needed

**1. Required: the `f75` flag.** In `_apply_experimental_flags` (line 3414), after the magnet lines:

```python
    import drivers.mini60
    drivers.mini60.Mini60Driver.experimental_f75 = "f75" in flags
    if "f75" in flags:
        log.warning("EXPERIMENTAL: AULA F75 HE dead-zone and macro writes enabled "
                    "(never run on this board, bring-up only)")
```

Also update that function's docstring, which says only `magnet` exists. Suggested test, mirroring
`tests/test_magnet_driver.py::test_experimental_flag_comes_only_from_the_env_switch`:
`_apply_experimental_flags({})` leaves it `False`; `{"AETHER_EXPERIMENTAL": "f75"}` sets it `True`;
reset to `False` in a `finally`.

**2. Optional: battery in the UI.** No bridge method calls the driver's `device_status()`. A
read-only method on `Api` is enough, for example:

```python
    def get_device_status(self):
        """Battery / work mode over a 2.4 GHz dongle; {"ok": True, "status": None} when wired."""
        try:
            fn = getattr(self.driver, "device_status", None)
            return {"ok": True, "status": fn() if fn else None}
        except Exception as e:
            return {"ok": False, "error": str(e)}
```

I did not check how `Api` methods take the write lock or are registered with the bridge; follow
the neighbouring read methods. The UI side belongs to Agent A.

## Other notes for the merge

- I edited `drivers/__init__.py` (docstring only); it is on neither ownership list.
- Lighting mode names on the F75 other than Static and Drifting are labelled UNVERIFIED in the
  registry `_note` only. `boards.py` drops unknown per-mode keys, so there is no per-mode
  "unverified" marker for the UI to read.
- An F75 on Bluetooth enumerates as `0C45:FEFE` with product `AULA F75 HE-<n>`. That string matches
  no entry, so it falls back to `aula-mini60he-pro-24g` as any unknown string on that pair always
  has. It has no vendor collection, so the open fails. Not addressed.

## Next steps, in order

1. Fix the magnet test (or drop `2ebce23`'s registry change until Agent A is ready).
2. Apply `app_web.py` change 1 and its test.
3. udev: add the two lines to `99-aula.rules`; the Flatpak manifest only mentions the host rules
   in a comment, so there is no second copy. README line 170 already copies the file.
4. Sayo B1 + B2 per `fork-review-fatalist.md` section 3: `build_key_analog(..., *, base_payload,
   echo)`, `parse_key_analog`, `CAPTURED_ANALOG_FIXED_2F`, goldens with echo `0x13`. Commit
   trailer: "Adapted from origin/feat/sayo-actuation-decode@cfdcb8d", no co-author.
5. `docs/HARDWARE_TEST_CHECKLIST.md` F75 section; README F75 / Sayo prose.
6. Re-run the full suite and the README table check.
