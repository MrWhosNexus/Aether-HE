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
