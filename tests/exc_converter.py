from __future__ import annotations

import sys
from collections.abc import Generator
from contextlib import contextmanager

if sys.version_info < (3, 11):  # pragma: no cover
    from exceptiongroup import BaseExceptionGroup


@contextmanager
def convert_excgroups() -> Generator[None, None, None]:
    try:
        yield
    except BaseException as exc:
        while isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
            exc = exc.exceptions[0]

        raise exc
