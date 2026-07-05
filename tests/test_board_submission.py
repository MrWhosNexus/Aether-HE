import tools.board_submission as bs

def _valid():
    s = bs.new_submission_skeleton("0.2.0")
    s["device"].update({"vid": "0x2E3C", "pid": "0xC365", "usage_page": "0xFF1B",
                         "hid_descriptor_b64": "AA=="})
    s["meta"].update({"brand": "Aula", "model": "Win60 HE", "switch_type": "Hall-effect",
                      "form_factor": "60%", "size": "60"})
    s["size_template"] = "generic-60"
    s["input_capture"] = {"duration_ms": 100, "report_len": 64,
                          "reports": [{"t": 5, "hex": "01ab"}], "keys_seen": 1}
    return s

def test_skeleton_has_schema_id():
    assert bs.new_submission_skeleton("0.2.0")["schema"] == "aether-board-submission/1"

def test_valid_submission_passes():
    assert bs.validate_submission(_valid()) == []

def test_missing_device_vid_fails():
    s = _valid(); s["device"]["vid"] = ""
    assert any("vid" in e for e in bs.validate_submission(s))

def test_bad_size_fails():
    s = _valid(); s["meta"]["size"] = "42"
    assert any("size" in e for e in bs.validate_submission(s))

def test_reports_must_be_hex():
    s = _valid(); s["input_capture"]["reports"] = [{"t": 1, "hex": "zz"}]
    assert any("hex" in e for e in bs.validate_submission(s))

def test_never_raises_on_garbage():
    for junk in [None, 5, "x", [], {"schema": 1}]:
        assert isinstance(bs.validate_submission(junk), list)
