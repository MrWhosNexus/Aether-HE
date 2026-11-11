"""SOCD model numbering and the one-time renumbering of saved profiles
(ui/runtime_src/src/components/socd-model.jsx), run in node.

The UI, saved profiles and the bridge hold the vendor's model NUMBER (1..4).
The Win60 driver alone turns it into a wire byte (number - 1); other boards'
drivers take the number as is. Builds before this fix sent the stored value
verbatim, so a state they wrote holds the byte a Win60 received. The migration
renumbers such a state once, so that keyboard keeps behaving as it did, and
stamps it.
"""
import json
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "ui", "runtime_src")
BUILT = os.path.join(SRC, "build", "comp_socd-model.js")
NODE = shutil.which("node")

HARNESS = r"""
const fs = require("fs");
global.window = {};
eval(fs.readFileSync(process.argv[2], "utf8"));
const S = window.AetherSocd;
const legacy = { actuation: 1.2, socdActive: "SOCD1", socdProfiles: [
  { id: "SOCD1", k1: "A", k2: "D", mode: 1, active: true },
  { id: "SOCD2", k1: "W", k2: "S", mode: 2 },
  { id: "SOCD3", k1: "Q", k2: "E", mode: 3 },
  { id: "SOCD4", k1: "Z", k2: "C", mode: 4 },
  { id: "SOCD5", k1: "", k2: "" },
  { id: "SOCD6", k1: "1!", k2: "2@", mode: 0 },
  { id: "SOCD7", k1: "3#", k2: "$4", mode: 9 },
] };
// What the pre-fix build put on the wire for a row: `p.mode || 1`, verbatim.
const sentBefore = (p) => p.mode || 1;
// What a Win60 gets now: the driver's number - 1 (drivers/win60.py).
const win60Wire = (mode) => S.modelOf(mode) - 1;
const frozen = JSON.stringify(legacy);
const once = S.migrateState(legacy);
const twice = S.migrateState(once);
const viaJson = S.migrateState(JSON.parse(JSON.stringify(once)));
console.log(JSON.stringify({
  rev: S.SOCD_REV,
  models: S.SOCD_MODELS,
  text: S.SOCD_MODELS.map(m => S.SOCD_MODEL_TEXT[m]),
  hasWire: "wireModel" in S,
  number: [1, 2, 3, 4].map(S.modelOf),
  numberJunk: [undefined, null, 0, 5, "x", 2.5, -1].map(S.modelOf),
  numberString: S.modelOf("3"),
  inputUntouched: JSON.stringify(legacy) === frozen,
  once,
  sameObjectSecondTime: twice === once,
  viaJsonEqual: JSON.stringify(viaJson) === JSON.stringify(once),
  oldWire: legacy.socdProfiles.map(sentBefore),
  newWire: once.socdProfiles.map(p => win60Wire(p.mode)),
  noRows: S.migrateState({ actuation: 1.0 }),
  empty: S.migrateState({}),
  stamped: S.migrateState({ socdRev: 2, socdProfiles: [{ id: "SOCD1", k1: "A", k2: "D", mode: 1 }] }),
  nullish: [S.migrateState(null), S.migrateState(undefined)].map(v => v === null || v === undefined),
}));
"""


@pytest.fixture(scope="module")
def socd(tmp_path_factory):
    if NODE is None:
        pytest.skip("node not installed")
    h = tmp_path_factory.mktemp("socd") / "harness.cjs"
    h.write_text(HARNESS, encoding="utf-8")
    out = subprocess.run([NODE, str(h), BUILT], check=True, capture_output=True,
                         text=True, encoding="utf-8")
    return json.loads(out.stdout)


def test_the_ui_module_holds_model_numbers_and_knows_no_wire_value(socd):
    """The wire byte is per board, so it is the driver's business. A shared
    UI-side conversion is what leaked the Win60's zero-basing into the
    MINI 60 and magnet drivers."""
    assert socd["models"] == [1, 2, 3, 4]
    assert socd["number"] == [1, 2, 3, 4]
    assert socd["numberString"] == 3
    assert socd["hasWire"] is False
    assert len(socd["text"]) == 4 and all(socd["text"])


def test_a_bad_stored_mode_is_model_1_never_out_of_range(socd):
    assert socd["numberJunk"] == [1] * 7


def test_legacy_rows_keep_the_behaviour_the_keyboard_had(socd):
    """Every row a Win60 acted on is sent the same wire byte after the
    renumbering - including a row with NO mode or mode 0, which the old build
    sent as `p.mode || 1` = wire 1 (it used to be migrated to Model 1 = wire 0,
    silently changing the pair's behaviour)."""
    #                 1  2  3  4  none 0  junk
    assert socd["oldWire"] == [1, 2, 3, 4, 1, 1, 9]
    assert socd["newWire"] == [1, 2, 3, 0, 1, 1, 0]
    modes = [p.get("mode") for p in socd["once"]["socdProfiles"]]
    # old 4 was never a model (its label promised "later key wins" = Model 1),
    # and neither was junk: the firmware ignored both, they become Model 1.
    assert modes == [2, 3, 4, 1, 2, 2, 1]


def test_migration_keeps_everything_else_and_stamps_the_state(socd):
    once = socd["once"]
    assert once["socdRev"] == socd["rev"] == 2
    assert once["actuation"] == 1.2 and once["socdActive"] == "SOCD1"
    assert once["socdProfiles"][0] == {"id": "SOCD1", "k1": "A", "k2": "D",
                                       "mode": 2, "active": True}
    assert socd["inputUntouched"], "migrateState must not mutate its input"


def test_migration_is_idempotent(socd):
    assert socd["sameObjectSecondTime"], "a stamped state must come back unchanged"
    assert socd["viaJsonEqual"], "a save/load round trip must not renumber again"
    assert socd["stamped"]["socdProfiles"][0]["mode"] == 1


def test_states_without_socd_rows_are_left_alone(socd):
    assert socd["noRows"] == {"actuation": 1.0}
    assert socd["empty"] == {}
    assert socd["nullish"] == [True, True]


def test_app_stamps_every_state_it_writes_and_migrates_every_state_it_reads():
    with open(os.path.join(SRC, "src", "app.jsx"), encoding="utf-8") as f:
        app = f.read()
    # written: profile saves, the close-time flush and backups all go through collectState
    assert "socdProfiles, socdActive, socdRev: SOCD_REV," in app
    # read: every profile at load, and any state applied later (profile switch,
    # backup import, wizard restore)
    assert "const migrateSettings = (raw) => withSocdMigrated(migrateSettingsShape(raw));" in app
    assert "    s = migrateSocdState(s);\n" in app
    # the game-switch spec of a non-active profile
    assert "socdPairsFrom(migrateSocdState(s).socdProfiles)" in app


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_built_module_parses():
    subprocess.run([NODE, "--check", BUILT], check=True)
