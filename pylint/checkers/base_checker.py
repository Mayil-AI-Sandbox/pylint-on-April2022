# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/PyCQA/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/PyCQA/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import functools
import warnings
from inspect import cleandoc
from typing import TYPE_CHECKING, Any

from astroid import nodes

from pylint.config.arguments_provider import _ArgumentsProvider
from pylint.constants import _MSG_ORDER, WarningScope
from pylint.exceptions import InvalidMessageError
from pylint.interfaces import Confidence, IRawChecker, ITokenChecker, implements
from pylint.message.message_definition import MessageDefinition
from pylint.typing import Options
from pylint.utils import get_rst_section, get_rst_title

if TYPE_CHECKING:
    from pylint.lint import PyLinter


@functools.total_ordering
class BaseChecker(_ArgumentsProvider):

    # checker name (you may reuse an existing one)
    name: str = ""
    # ordered list of options to control the checker behaviour
    options: Options = ()
    # messages issued by this checker
    msgs: Any = {}
    # reports issued by this checker
    reports: Any = ()
    # mark this checker as enabled or not.
    enabled: bool = True

    def __init__(self, linter: PyLinter) -> None:
        """Checker instances should have the linter as argument."""
        if self.name is not None:
            self.name = self.name.lower()
        self.linter = linter

        _ArgumentsProvider.__init__(self, linter)

    def __gt__(self, other):
        """Permit to sort a list of Checker by name."""
        return f"{self.name}{self.msgs}" > f"{other.name}{other.msgs}"

    def __eq__(self, other):
        """Permit to assert Checkers are equal."""
        return f"{self.name}{self.msgs}" == f"{other.name}{other.msgs}"

    def __hash__(self):
        """Make Checker hashable."""
        return hash(f"{self.name}{self.msgs}")

    def __repr__(self):
        status = "Checker" if self.enabled else "Disabled checker"
        msgs = "', '".join(self.msgs.keys())
        return f"{status} '{self.name}' (responsible for '{msgs}')"

    def __str__(self):
        """This might be incomplete because multiple classes inheriting BaseChecker
        can have the same name.

        See: MessageHandlerMixIn.get_full_documentation()
        """
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            return self.get_full_documentation(
                msgs=self.msgs, options=self.options_and_values(), reports=self.reports
            )

    def get_full_documentation(self, msgs, options, reports, doc=None, module=None):
        result = ""
        checker_title = f"{self.name.replace('_', ' ').title()} checker"
        if module:
            # Provide anchor to link against
            result += f".. _{module}:\n\n"
        result += f"{get_rst_title(checker_title, '~')}\n"
        if module:
            result += f"This checker is provided by ``{module}``.\n"
        result += f"Verbatim name of the checker is ``{self.name}``.\n\n"
        if doc:
            # Provide anchor to link against
            result += get_rst_title(f"{checker_title} Documentation", "^")
            result += f"{cleandoc(doc)}\n\n"
        # options might be an empty generator and not be False when cast to boolean
        options = list(options)
        if options:
            result += get_rst_title(f"{checker_title} Options", "^")
            result += f"{get_rst_section(None, options)}\n"
        if msgs:
            result += get_rst_title(f"{checker_title} Messages", "^")
            for msgid, msg in sorted(
                msgs.items(), key=lambda kv: (_MSG_ORDER.index(kv[0][0]), kv[1])
            ):
                msg = self.create_message_definition_from_tuple(msgid, msg)
                result += f"{msg.format_help(checkerref=False)}\n"
            result += "\n"
        if reports:
            result += get_rst_title(f"{checker_title} Reports", "^")
            for report in reports:
                result += (
                    ":%s: %s\n" % report[:2]  # pylint: disable=consider-using-f-string
                )
            result += "\n"
        result += "\n"
        return result

    def add_message(
        self,
        msgid: str,
        line: int | None = None,
        node: nodes.NodeNG | None = None,
        args: Any = None,
        confidence: Confidence | None = None,
        col_offset: int | None = None,
        end_lineno: int | None = None,
        end_col_offset: int | None = None,
    ) -> None:
        self.linter.add_message(
            msgid, line, node, args, confidence, col_offset, end_lineno, end_col_offset
        )

    def check_consistency(self):
        """Check the consistency of msgid.

        msg ids for a checker should be a string of len 4, where the two first
        characters are the checker id and the two last the msg id in this
        checker.

        :raises InvalidMessageError: If the checker id in the messages are not
        always the same.
        """
        checker_id = None
        existing_ids = []
        for message in self.messages:
            if checker_id is not None and checker_id != message.msgid[1:3]:
                error_msg = "Inconsistent checker part in message id "
                error_msg += f"'{message.msgid}' (expected 'x{checker_id}xx' "
                error_msg += f"because we already had {existing_ids})."
                raise InvalidMessageError(error_msg)
            checker_id = message.msgid[1:3]
            existing_ids.append(message.msgid)

    def create_message_definition_from_tuple(self, msgid, msg_tuple):
        if implements(self, (IRawChecker, ITokenChecker)):
            default_scope = WarningScope.LINE
        else:
            default_scope = WarningScope.NODE
        options = {}
        if len(msg_tuple) > 3:
            (msg, symbol, descr, options) = msg_tuple
        elif len(msg_tuple) > 2:
            (msg, symbol, descr) = msg_tuple
        else:
            error_msg = """Messages should have a msgid and a symbol. Something like this :

"W1234": (
    "message",
    "message-symbol",
    "Message description with detail.",
    ...
),
"""
            raise InvalidMessageError(error_msg)
        options.setdefault("scope", default_scope)
        return MessageDefinition(self, msgid, msg, descr, symbol, **options)

    @property
    def messages(self) -> list:
        return [
            self.create_message_definition_from_tuple(msgid, msg_tuple)
            for msgid, msg_tuple in sorted(self.msgs.items())
        ]

    # dummy methods implementing the IChecker interface

    def get_message_definition(self, msgid):
        for message_definition in self.messages:
            if message_definition.msgid == msgid:
                return message_definition
        error_msg = f"MessageDefinition for '{msgid}' does not exists. "
        error_msg += f"Choose from {[m.msgid for m in self.messages]}."
        raise InvalidMessageError(error_msg)

    def open(self):
        """Called before visiting project (i.e. set of modules)."""

    def close(self):
        """Called after visiting project (i.e set of modules)."""


class BaseTokenChecker(BaseChecker):
    """Base class for checkers that want to have access to the token stream."""

    def process_tokens(self, tokens):
        """Should be overridden by subclasses."""
        raise NotImplementedError()
