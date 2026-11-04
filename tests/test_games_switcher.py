"""Phase 3: the debounced profile-switch state machine. Pure: the test owns
the clock and calls step() the way the 3 s poll does."""
import games

G, H = "100000000000000001", "100000000000000002"
MAP = {G: "pg", H: "ph"}
NAMES = {G: "Starfall Arena", H: "Neon Quest"}


class Run:
    """Drive a switcher on a fake clock, one poll per call."""

    def __init__(self, auto=True, active="p1"):
        self.sw = games.GameSwitcher()
        self.t = 0.0
        self.auto = auto
        self.active = active
        self.mapping = dict(MAP)

    def poll(self, running=(), fg=None, dt=games.POLL_S):
        self.t += dt
        out = self.sw.step(self.t, set(running), fg, self.mapping, self.auto,
                           self.active, NAMES)
        if out:
            self.active = out["profileId"]                     # the app obeys
            self.sw.note_active(self.active, out["seq"])
        return out

    def until_switch(self, running=(), fg=None, polls=5):
        for _ in range(polls):
            out = self.poll(running, fg)
            if out:
                return out
        return None


def test_game_start_switches_after_the_debounce():
    r = Run()
    assert r.poll({G}) is None                                  # t=3: seen
    assert r.poll({G}) is None                                  # t=6: held 3 s < 5 s
    out = r.until_switch({G})
    assert out == {"seq": 1, "profileId": "pg", "reason": "game",
                   "gameId": G, "gameName": "Starfall Arena"}
    assert r.t >= 3.0 + games.DEBOUNCE_S


def test_exit_reverts_to_the_profile_active_before_the_game():
    r = Run(active="p1")
    r.until_switch({G})
    assert r.poll({G}) is None                                  # steady while running
    out = r.until_switch(set())
    assert out["profileId"] == "p1" and out["reason"] == "revert" and out["gameId"] is None


def test_a_short_blip_never_switches():
    r = Run()
    r.poll({G})
    assert r.poll(set()) is None                                # gone again before 5 s
    for _ in range(4):
        assert r.poll(set()) is None
    assert r.sw.seq == 0


def test_alt_tab_between_two_games_is_debounced():
    r = Run()
    r.until_switch({G, H}, fg=G)
    assert r.active == "pg"
    assert r.poll({G, H}, fg=H) is None                         # tabbed to H for 3 s ...
    assert r.poll({G, H}, fg=G) is None                         # ... and back: nothing
    for _ in range(3):
        assert r.poll({G, H}, fg=G) is None
    out = r.until_switch({G, H}, fg=H)                          # H stays in front: switch
    assert out["profileId"] == "ph" and out["gameId"] == H


def test_foreground_non_game_keeps_the_current_game():
    r = Run()
    r.until_switch({G, H}, fg=H)
    for _ in range(5):
        assert r.poll({G, H}, fg=None) is None                  # browser in front: stay on H


def test_without_focus_the_most_recently_started_game_wins():
    r = Run()
    r.poll({G})
    r.poll({G, H})
    out = r.until_switch({G, H})
    assert out["gameId"] == H


def test_switching_between_games_keeps_the_original_revert_target():
    r = Run(active="p1")
    r.until_switch({G}, fg=G)
    r.until_switch({G, H}, fg=H)
    out = r.until_switch(set())
    assert out["profileId"] == "p1"


def test_manual_switch_during_a_game_cancels_revert_and_reapply():
    r = Run(active="p1")
    out = r.until_switch({G})
    r.active = "p9"
    r.sw.note_active("p9", out["seq"])                          # user picked p9 by hand
    for _ in range(4):
        assert r.poll({G}) is None                              # game NOT re-applied
    for _ in range(4):
        assert r.poll(set()) is None                            # and no revert on exit
    assert r.sw.session is False


def test_a_stale_report_before_the_ui_handled_the_switch_is_not_an_override():
    r = Run(active="p1")
    out = r.until_switch({G})
    r.sw.note_active("p1", out["seq"] - 1)                      # old sync landing late
    assert r.sw.overridden is False
    assert r.until_switch(set())["profileId"] == "p1"


def test_auto_switch_off_tracks_but_never_switches():
    r = Run(auto=False)
    for _ in range(5):
        assert r.poll({G}) is None
    assert r.sw.current == G and r.sw.session is False
    for _ in range(5):
        assert r.poll(set()) is None


def test_reset_lets_a_running_game_apply_when_auto_is_turned_on():
    r = Run(auto=False)
    for _ in range(4):
        r.poll({G})
    r.auto = True
    r.sw.reset()
    assert r.until_switch({G})["profileId"] == "pg"


def test_remapping_the_running_game_switches_to_the_new_profile():
    r = Run()
    r.until_switch({G})
    r.mapping[G] = "pz"
    out = r.until_switch({G})
    assert out["profileId"] == "pz" and out["reason"] == "game"


def test_unmapping_the_running_game_reverts():
    r = Run(active="p1")
    r.until_switch({G})
    del r.mapping[G]
    assert r.until_switch({G})["profileId"] == "p1"


def test_unmapped_games_are_ignored():
    r = Run()
    for _ in range(5):
        assert r.poll({"999"}) is None


def test_no_revert_when_the_previous_profile_is_unknown():
    r = Run(active=None)
    r.until_switch({G})
    assert r.until_switch(set()) is None


def test_seq_increases_and_last_is_a_copy():
    r = Run()
    a = r.until_switch({G})
    b = r.until_switch(set())
    assert (a["seq"], b["seq"]) == (1, 2)
    a["profileId"] = "tamper"
    assert r.sw.last["seq"] == 2 and r.sw.last["profileId"] == "p1"
