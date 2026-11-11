"""SOCD model numbering and the one-time renumbering of saved profiles
(ui/runtime_src/src/components/socd-model.jsx), run in node.

The UI and saved profiles hold the vendor's model NUMBER (1..4); the wire byte
is that minus one. Builds before this fix sent the number verbatim, so a state
they wrote holds the byte the keyboard received. The migration renumbers such
a state once, so the keyboard keeps behaving as it did, and stamps it.
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
] };
const frozen = JSON.stringify(legacy);
const once = S.migrateState(legacy);
const twice = S.migrateState(once);
const viaJson = S.migrateState(JSON.parse(JSON.stringify(once)));
console.log(JSON.stringify({
  rev: S.SOCD_REV,
  models: S.SOCD_MODELS,
  text: S.SOCD_MODELS.map(m => S.SOCD_MODEL_TEXT[m]),
  wire: [1, 2, 3, 4].map(S.wireModel),
  wireJunk: [undefined, null, 0, 5, "x", 2.5, -1].map(S.wireModel),
  wireString: S.wireModel("3"),
  inputUntouched: JSON.stringify(legacy) === frozen,
  once,
  sameObjectSecondTime: twice === once,
  viaJsonEqual: JSON.stringify(viaJson) === JSON.stringify(once),
  oldWire: legacy.socdProfiles.slice(0, 3).map(p => p.mode),
  newWire: once.socdProfiles.slice(0, 3).map(p => S.wireModel(p.mode)),
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


def test_model_number_maps_to_the_zero_based_wire_value(socd):
    assert socd["models"] == [1, 2, 3, 4]
    assert socd["wire"] == [0, 1, 2, 3]
    assert socd["wireString"] == 2
    assert len(socd["text"]) == 4 and all(socd["text"])


def test_a_bad_stored_mode_is_model_1_never_out_of_range(socd):
    assert socd["wireJunk"] == [0] * 7


def test_legacy_rows_keep_the_behaviour_the_keyboard_had(socd):
    """Old 1/2/3 were sent as wire 1/2/3; after the renumbering they still are."""
    assert socd["oldWire"] == [1, 2, 3]
    assert socd["newWire"] == [1, 2, 3]
    modes = [p.get("mode") for p in socd["once"]["socdProfiles"]]
    # old 4 was never a model (its label promised "later key wins" = Model 1);
    # a row without a mode, or with junk, becomes Model 1.
    assert modes == [2, 3, 4, 1, 1, 1]


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
