"""Safe rendering of repository-controlled text.

Filenames, branch names, and Git output are attacker-influenced: a path may
carry terminal escape sequences, or bytes that are not valid UTF-8 and reach
Python as surrogates through ``surrogateescape``. Both are rendered here as
printable text so they cannot drive a terminal and cannot fail encoding when a
machine-readable document is written.
"""

from __future__ import annotations

_CONTROL_ESCAPES = {
    "\a": r"\a",
    "\b": r"\b",
    "\t": r"\t",
    "\n": r"\n",
    "\v": r"\v",
    "\f": r"\f",
    "\r": r"\r",
}

# Bidirectional formatting characters reorder how text is displayed without
# being control bytes, so the C0/C1 ranges below do not cover them. A branch
# name carrying U+202E can make the rendered line read differently from the
# name that is actually stored. `agents` imports this set for its own
# terminal-safety predicate rather than keeping a second copy.
BIDI_CONTROLS = frozenset(
    {
        "؜",
        "‎",
        "‏",
        "‪",
        "‫",
        "‬",
        "‭",
        "‮",
        "⁦",
        "⁧",
        "⁨",
        "⁩",
    }
)


def escape_terminal_text(value: str) -> str:
    """Render ``value`` printable: control bytes and surrogates become escapes.

    Bidirectional formatting characters are escaped too. They are not control
    bytes, so the C0/C1 ranges miss them, but they reorder displayed text and
    are therefore a spoofing vector in any repository-controlled string.
    """
    escaped: list[str] = []
    for character in value:
        codepoint = ord(character)
        if character == "\\":
            escaped.append(r"\\")
        elif character in _CONTROL_ESCAPES:
            escaped.append(_CONTROL_ESCAPES[character])
        elif codepoint < 0x20 or 0x7F <= codepoint <= 0x9F:
            escaped.append(f"\\x{codepoint:02x}")
        elif character in BIDI_CONTROLS:
            escaped.append(f"\\u{codepoint:04x}")
        elif 0xDC80 <= codepoint <= 0xDCFF:
            escaped.append(f"\\x{codepoint - 0xDC00:02x}")
        elif 0xD800 <= codepoint <= 0xDFFF:
            escaped.append(f"\\u{codepoint:04x}")
        else:
            escaped.append(character)
    return "".join(escaped)
