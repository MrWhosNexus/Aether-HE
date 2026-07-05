import tools.board_bot as bot

def test_extract_json_block():
    body = 'intro\n```json\n{"schema": "aether-board-submission/1", "meta": {}}\n```\nend'
    d = bot.extract_json_block(body)
    assert d and d["schema"] == "aether-board-submission/1"

def test_extract_json_block_none():
    assert bot.extract_json_block("no code here") is None

def test_extract_attachment_url():
    body = "see file [board.json](https://github.com/x/files/1/board.json) attached"
    assert bot.extract_attachment_url(body) == "https://github.com/x/files/1/board.json"

def test_extract_attachment_url_none():
    assert bot.extract_attachment_url("no links") is None

def test_build_prompt_includes_submission():
    p = bot.build_prompt({"meta": {"brand": "Aula"}}, "TEMPLATE:\n{submission}")
    assert "TEMPLATE:" in p and "Aula" in p


_MODEL_OUT = '''
=== FILE: registry_entry.json ===
{"slug": "acme-60", "name": "Acme 60", "vid": "0x1", "pid": "0x2",
 "usage_page": "0xFF1B", "formFactor": "60%", "protocol": "protocol_acme_60",
 "keymap": "ui/layouts/acme-60.json",
 "capabilities": {"actuation": true, "lighting": false, "perKeyRgb": false},
 "status": "experimental"}
=== FILE: layout.json ===
{"_meta": {"board": "acme-60"}, "type": "60", "keys": [{"index": 0, "name": "A", "code": "KeyA", "hidCode": "0x04", "x": 0, "y": 0}]}
=== FILE: protocol_adapter.py ===
# AI-DRAFTED - UNVERIFIED
def build(): return b""
=== FILE: DECODE_NOTES.md ===
Inferred input reports only. Lighting unknown (no pcap).
'''

def test_parse_model_output():
    a = bot.parse_model_output(_MODEL_OUT)
    assert a["registry"]["slug"] == "acme-60"
    assert a["registry"]["status"] == "experimental"
    assert a["layout"]["type"] == "60"
    assert "def build" in a["adapter"]
    assert "Lighting unknown" in a["notes"]

def test_sanity_check_ok():
    a = bot.parse_model_output(_MODEL_OUT)
    assert bot.sanity_check(a, existing_slugs=set()) == []

def test_sanity_check_dup_slug():
    a = bot.parse_model_output(_MODEL_OUT)
    errs = bot.sanity_check(a, existing_slugs={"acme-60"})
    assert any("slug" in e for e in errs)

def test_sanity_check_bad_status():
    a = bot.parse_model_output(_MODEL_OUT)
    a["registry"]["status"] = "supported"
    assert any("experimental" in e for e in bot.sanity_check(a, set()))

def test_sanity_check_unparseable_adapter_not_fatal():
    a = bot.parse_model_output(_MODEL_OUT)
    a["adapter"] = "def (:::"   # invalid python
    errs = bot.sanity_check(a, set())
    assert any("adapter" in e.lower() for e in errs)  # reported, but caller treats as non-fatal


def test_run_happy_path(tmp_path, monkeypatch):
    # existing registry with no boards
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "board_registry.json").write_text('{"boards": []}')
    (tmp_path / "ui" / "layouts").mkdir(parents=True)
    calls = {"pr": None, "comment": None}
    def fake_gh(args):
        if args[:2] == ["issue", "view"]:
            return '{"number": 9, "title": "t", "body": "```json\\n' + \
                   '{\\"schema\\":\\"aether-board-submission/1\\",\\"device\\":{\\"vid\\":\\"0x1\\",\\"pid\\":\\"0x2\\"},' + \
                   '\\"meta\\":{\\"brand\\":\\"Acme\\",\\"model\\":\\"60\\",\\"size\\":\\"60\\"},\\"input_capture\\":{\\"reports\\":[]}}\\n```"}'
        if args[0] == "pr":
            calls["pr"] = args; return "https://github.com/x/pull/3"
        if args[:2] == ["issue", "comment"]:
            calls["comment"] = args; return ""
        return ""
    monkeypatch.setattr(bot, "_read_prompt", lambda: "T {submission}")
    res = bot.run(9, gh=fake_gh, complete=lambda p: _MODEL_OUT, repo_root=str(tmp_path))
    assert res["ok"] is True and res["pr_url"] == "https://github.com/x/pull/3"
    assert (tmp_path / "ui" / "layouts" / "acme-60.json").exists()
    assert (tmp_path / "protocol_acme_60.py").exists()
    assert calls["comment"] is not None   # commented the PR link on the issue

def test_run_invalid_submission_comments_no_pr(tmp_path, monkeypatch):
    def fake_gh(args):
        if args[:2] == ["issue", "view"]:
            return '{"number": 9, "title": "t", "body": "```json\\n{\\"schema\\":\\"wrong\\"}\\n```"}'
        return ""
    monkeypatch.setattr(bot, "_read_prompt", lambda: "T {submission}")
    res = bot.run(9, gh=fake_gh, complete=lambda p: "", repo_root=str(tmp_path))
    assert res["ok"] is False and res["pr_url"] is None
    assert "invalid" in res["reason"].lower()
