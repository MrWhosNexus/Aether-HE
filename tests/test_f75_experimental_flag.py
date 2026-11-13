"""AETHER_EXPERIMENTAL=f75 is the only switch for the F75 HE's unrun paths."""
import app_web
import drivers.mini60


def test_f75_flag_is_off_by_default_and_on_when_named():
    try:
        app_web._apply_experimental_flags({})
        assert drivers.mini60.Mini60Driver.experimental_f75 is False
        app_web._apply_experimental_flags({"AETHER_EXPERIMENTAL": "magnet, F75"})
        assert drivers.mini60.Mini60Driver.experimental_f75 is True
    finally:
        app_web._apply_experimental_flags({})
