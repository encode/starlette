from typing import Any, Optional

try:
    from contextvars import Context, ContextVar, copy_context
except ImportError:  # pragma: no cover
    Context = object  # type: ignore
    ContextVar = copy_context = None  # type: ignore


def _set_cvar(cvar: ContextVar, val: Any) -> None:
    cvar.set(val)


class CaptureContext:
    def __init__(self) -> None:
        if Context is not None:
            self.context = Context()
        else:
            self.context = None

    def __enter__(self) -> "CaptureContext":
        if copy_context is not None:
            self._outer = copy_context()
        else:   # pragma: no cover
            self._outer = None
        return self

    def sync(self) -> None:
        if self._outer is None:  # pragma: no cover
            return
        final = copy_context()
        for cvar in final:
            if cvar not in self._outer:
                # new contextvar set
                self.context.run(_set_cvar, cvar, final.get(cvar))
            else:
                final_val = final.get(cvar)
                if self._outer.get(cvar) != final_val:
                    # value changed
                    self.context.run(_set_cvar, cvar, final_val)

    def __exit__(self, *args: Any) -> None:
        self.sync()


def restore_context(context: Optional[Context]) -> None:
    """Restore `context` to the current Context"""
    if context is None:
        return
    for cvar in context.keys():
        try:
            cvar.set(context.get(cvar))
        except LookupError:
            cvar.set(context.get(cvar))
