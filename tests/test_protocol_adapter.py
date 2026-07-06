"""Tests for protocol_adapter — the per-board protocol dispatch the Api uses.

Verifies that for_board() routes by the registry's `protocol` field, that the
SayoAdapter builds actuation writes byte-for-byte identical to protocol_sayo's
golden output plus a trailing save, and that its capability flags gate the
features whose SayoDevice wire format is not decoded yet.

Run: python -m pytest tests/test_protocol_adapter.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import boards
import protocol_adapter
import protocol_sayo as psy


def _profile(slug):
    return boards.load_registry().by_slug(slug)


def test_for_board_returns_sayo_adapter_for_sayo_board():
    a = protocol_adapter.for_board(_profile("aula-win60he-pro"))
    assert isinstance(a, protocol_adapter.SayoAdapter)
    assert a.protocol_name == "protocol_sayo"


def test_for_board_returns_none_for_legacy_2e3c_board():
    # The 2E3C board keeps the inline legacy path -> no adapter.
    assert protocol_adapter.for_board(_profile("aula-win60-he")) is None


def test_for_board_returns_none_for_none():
    assert protocol_adapter.for_board(None) is None


def test_actuation_packets_match_golden_plus_save():
    a = protocol_adapter.for_board(_profile("aula-win60he-pro"))
    pkts = a.actuation_packets([0x2F], 0.4)
    assert len(pkts) == 2                       # one per-key write + one save
    assert pkts[0] == psy.build_key_analog(0x2F, 0.4)
    assert pkts[1] == psy.build_save()


def test_actuation_packets_multi_key_then_single_save():
    a = protocol_adapter.for_board(_profile("aula-win60he-pro"))
    pkts = a.actuation_packets([0x2F, 0x30, 0x31], 1.0)
    assert len(pkts) == 4                        # 3 writes + 1 save
    assert pkts[:3] == [psy.build_key_analog(k, 1.0) for k in (0x2F, 0x30, 0x31)]
    assert pkts[3] == psy.build_save()


def test_actuation_packets_explicit_release():
    a = protocol_adapter.for_board(_profile("aula-win60he-pro"))
    pkts = a.actuation_packets([0x2F], 2.0, 0.5)
    assert pkts[0] == psy.build_key_analog(0x2F, 2.0, 0.5)


def test_actuation_packets_empty_keys_is_noop():
    a = protocol_adapter.for_board(_profile("aula-win60he-pro"))
    assert a.actuation_packets([], 1.0) == []    # no keys -> no save either


def test_actuation_out_of_range_propagates_valueerror():
    import pytest
    a = protocol_adapter.for_board(_profile("aula-win60he-pro"))
    with pytest.raises(ValueError):
        a.actuation_packets([0x2F], 5.0)


def test_lighting_packet_matches_protocol_sayo():
    a = protocol_adapter.for_board(_profile("aula-win60he-pro"))
    assert a.lighting_packet(0x01) == psy.build_lighting(0x01)


def test_capability_flags_gate_undecoded_features():
    a = protocol_adapter.for_board(_profile("aula-win60he-pro"))
    assert a.supports_live_read is False
    assert a.supports_color is False
    assert a.supports_rt is False
    assert a.needs_legacy_handshake() is False
