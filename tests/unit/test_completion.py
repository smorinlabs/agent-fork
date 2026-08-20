"""Unit tests for parser-derived shell completion.

These assert the invariant the parser-derived rewrite exists to hold: every
option ``argparse`` declares reaches the completion vocabulary. The instance
that motivated it was ``-o`` drifting out of the hand-maintained ``fork`` and
``cleanup`` lists, but asserting that one flag would not catch the next drift.
"""

import argparse
from typing import cast

import pytest

from agent_fork.cli import _parser
from agent_fork.completion import _vocabulary

SUBCOMMANDS = ("fork", "cleanup", "session", "list", "doctor", "config")


def _subcommand_parsers() -> dict[str, argparse.ArgumentParser]:
    root = _parser()
    action = next(
        item for item in root._actions if isinstance(item, argparse._SubParsersAction)
    )
    return cast(dict[str, argparse.ArgumentParser], action.choices)


def _declared_options(parser: argparse.ArgumentParser) -> set[str]:
    return {value for action in parser._actions for value in action.option_strings}


@pytest.mark.matrix("T-CLI-33")
def test_completion_offers_every_declared_option():
    parsers = _subcommand_parsers()
    vocabulary = _vocabulary()
    missing = {}
    for command in SUBCOMMANDS:
        declared = _declared_options(parsers[command]) - {"-h", "--help"}
        offered = set(vocabulary[f"{command}_options"])
        if declared - offered:
            missing[command] = sorted(declared - offered)
    assert not missing, f"completion is missing declared options: {missing}"


@pytest.mark.matrix("T-CLI-34")
def test_completion_offers_every_declared_command():
    assert set(_subcommand_parsers()) <= set(_vocabulary()["commands"])


@pytest.mark.matrix("T-CLI-35")
def test_completion_output_choices_track_the_parser():
    """Output formats offered must be exactly those the parser accepts.

    Guards the ``table`` alias in particular: it was removed from the parser,
    and a completion that still offered it would send users to a rejected value.
    """
    declared = next(
        action.choices
        for action in _subcommand_parsers()["fork"]._actions
        if action.dest == "output"
    )
    assert declared is not None, "fork --output no longer declares choices"
    assert set(_vocabulary()["outputs"]) == set(declared)
