"""open_submission_url opens ONLY this repo's new-issue form (bridge input)."""
import webbrowser

import app_web

OK = "https://github.com/MrWhosNexus/Aether-HE/issues/new"


def test_allows_the_issue_form_with_a_query():
    f = app_web.Api._is_submission_url
    assert f(OK) and f(OK + "?template=add-a-board.yml&title=%5BBoard%5D%20x")


def test_refuses_everything_else():
    f = app_web.Api._is_submission_url
    for bad in ("file:///C:/Windows/System32/calc.exe", "ms-settings:", "http://github.com/MrWhosNexus/Aether-HE/issues/new",
                "https://github.com.evil.io/MrWhosNexus/Aether-HE/issues/new",
                "https://evil@github.com/MrWhosNexus/Aether-HE/issues/new",
                "https://github.com/someone/else/issues/new",
                "https://github.com/MrWhosNexus/Aether-HE/issues/new/../../x",
                "https://github.com/MrWhosNexus/Aether-HE/issues/new#x",
                OK + "?" + "a" * 9000, None, 5):
        assert not f(bad), bad


def test_bridge_never_opens_a_refused_url(monkeypatch):
    opened = []
    monkeypatch.setattr(webbrowser, "open", opened.append)
    api = app_web.Api.__new__(app_web.Api)
    assert api.open_submission_url("file:///etc/passwd")["ok"] is False
    assert api.open_submission_url(OK)["ok"] is True
    assert opened == [OK]
