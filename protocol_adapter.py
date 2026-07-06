"""protocol_adapter.py — per-board protocol dispatch for the Api layer.

`app_web.Api` was written against `protocol.py` (the Aula 2E3C command set). Boards
on other silicon speak different packet formats with different builder signatures,
so the Api cannot simply swap the import: `protocol.build_light(mode,r,g,b,...)`
and `protocol_sayo.build_lighting(mode)` are not interchangeable.

This module provides a thin adapter the Api consults for the operations whose wire
format is board-specific: the connect handshake, actuation writes, and lighting.
The legacy 2E3C path stays inline in `app_web` and is left byte-for-byte unchanged;
`for_board()` returns None for it (meaning "use the existing inline path") and a
real adapter only for boards that need one.

Each adapter also advertises capability flags so the Api can refuse operations the
board's protocol cannot yet perform (e.g. live actuation read-back on SayoDevice,
whose cmd-0x15 poll *response* is not decoded yet), instead of sending packets that
would be silently wrong on the wire.
"""
import protocol_sayo as psy


class SayoAdapter:
    """Adapter for SayoDevice boards (VID 0x8089), e.g. the Aula WIN 60 HE Pro.

    Wraps `protocol_sayo`. Actuation is decoded and golden-tested (cmd-0x1C, plus
    a cmd-0x0D save); live read-back, lighting color, and rapid-trigger semantics
    are not verified yet and are gated off via the capability flags below.
    """
    protocol_name = "protocol_sayo"

    # cmd-0x15 poll *response* format is not decoded — no live travel / read-back.
    supports_live_read = False
    # cmd-0x26 color/brightness fields are unverified — only the effect-mode byte.
    supports_color = False
    # Rapid-trigger hysteresis (and whether it needs the trailing save) unverified.
    supports_rt = False

    def __init__(self, board=None, echo=psy.DEFAULT_ECHO):
        self.board = board
        self.echo = echo

    # ---- connect ----
    def needs_legacy_handshake(self):
        """The 2E3C connect flow (cmd-0 heartbeat + cmd-24 Fn-layer keymap read)
        is meaningless on SayoDevice and would put wrong bytes on the 0xFF12
        interface. SayoDevice needs no handshake beyond opening the device."""
        return False

    # ---- actuation (cmd 0x1C + save) ----
    def actuation_packets(self, key_ids, press_mm, release_mm=None):
        """Return the wire packets that set actuation for `key_ids`: one cmd-0x1C
        per-key analog write, then a single cmd-0x0D save to persist. In fixed
        mode `release_mm` tracks `press_mm` (build_key_analog's default).

        `key_ids` are the SayoDevice per-key TLV ids. On the Aula WIN 60 HE Pro
        these currently come from the layout's grid indices, which are flagged
        provisional (`provisionalIndices`) until per-key captures confirm the
        index->key-id mapping. build_key_analog raises ValueError on out-of-range
        travel; callers should surface that."""
        key_ids = list(key_ids)
        if not key_ids:
            return []
        pkts = [psy.build_key_analog(kid, press_mm, release_mm, echo=self.echo)
                for kid in key_ids]
        pkts.append(psy.build_save(echo=self.echo))
        return pkts

    # ---- lighting (cmd 0x26, effect-mode byte only) ----
    def lighting_packet(self, mode):
        """cmd-0x26 lighting packet carrying only the effect-mode byte. Color and
        brightness are replayed verbatim from the capture (fields unverified), so
        the Api should not pass r/g/b through for this board yet."""
        return psy.build_lighting(mode & 0xFF, echo=self.echo)


# Registry protocol name -> adapter class. A board whose protocol is absent here
# (currently "protocol" and "protocol_sonix") uses the legacy inline Api path.
_ADAPTERS = {
    SayoAdapter.protocol_name: SayoAdapter,
}


def for_board(board):
    """Return a protocol adapter for `board`, or None to use the legacy inline
    2E3C path. `board` is a boards.BoardProfile (or None)."""
    if board is None:
        return None
    cls = _ADAPTERS.get(board.protocol)
    return cls(board) if cls else None
