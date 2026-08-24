"""Errors the user is meant to read.

A :class:`GafferError` carries a message that tells the user what to do next,
so the CLI prints it plainly instead of a traceback. It subclasses
``ValueError`` because that is what these paths raised before, and callers
(and tests) that catch ``ValueError`` keep working.
"""

from __future__ import annotations


class GafferError(ValueError):
    """A condition the user can act on, reported without a traceback."""
