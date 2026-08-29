"""Serving the UI to a phone on the same network (spec §7).

No auth and none planned: the trust boundary is the home network, exactly as
it is the loopback interface by default. The CLI says so out loud.
"""

from __future__ import annotations

import socket


def lan_ip() -> str | None:
    """This machine's address on the local network, or ``None``.

    Opening a UDP socket to a routable address asks the kernel which interface
    it *would* use without sending a packet — more reliable than resolving the
    hostname, which on a Mac often answers 127.0.0.1.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return str(sock.getsockname()[0])
    except OSError:
        return None
    finally:
        sock.close()


MISSING_QRCODE = "qrcode not installed — run uv sync"
"""Said out loud: an absent QR is a missing dependency, not a narrow terminal."""


def qr_lines(url: str) -> list[str]:
    """The URL as terminal-renderable QR rows; ``[]`` if qrcode is missing.

    The degraded path prints why. Returning ``[]`` in silence left the user
    reading a LAN banner with a QR-shaped hole in it and nothing anywhere
    saying that one `uv sync` would fill it.
    """
    try:
        import qrcode
    except ImportError:
        print(MISSING_QRCODE)
        return []
    if qrcode is None:
        # Belt and braces. A name can import to nothing — a stubbed or
        # half-initialised sys.modules entry under an import hook — and
        # `qrcode.QRCode` on None is an AttributeError traceback where the
        # honest answer is the same one line the ImportError gets.
        print(MISSING_QRCODE)
        return []
    code = qrcode.QRCode(border=1)
    code.add_data(url)
    code.make(fit=True)
    matrix = code.get_matrix()
    # Two rows per line with half-block characters: a QR drawn one module per
    # character line is taller than most terminals.
    lines = []
    for top in range(0, len(matrix), 2):
        upper = matrix[top]
        lower = matrix[top + 1] if top + 1 < len(matrix) else [False] * len(upper)
        lines.append("".join(
            "█" if u and l else "▀" if u else "▄" if l else " "
            for u, l in zip(upper, lower)))
    return lines
