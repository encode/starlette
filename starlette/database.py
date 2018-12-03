import logging
import typing

from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.sql import ClauseElement

logger = logging.getLogger("starlette.database")


def compile(query: ClauseElement, dialect: Dialect) -> typing.Tuple[str, list]:
    # query = execute_defaults(query)  # default values for Insert/Update
    compiled = query.compile(dialect=dialect)
    compiled_params = sorted(compiled.params.items())

    mapping = {key: "$" + str(i) for i, (key, _) in enumerate(compiled_params, start=1)}
    compiled_query = compiled.string % mapping

    processors = compiled._bind_processors
    args = [
        processors[key](val) if key in processors else val
        for key, val in compiled_params
    ]

    logger.debug(compiled_query)
    return compiled_query, args


class DatabaseBackend:
    async def startup(self) -> None:
        raise NotImplementedError()  # pragma: no cover

    async def shutdown(self) -> None:
        raise NotImplementedError()  # pragma: no cover

    def new_session(self) -> "DatabaseSession":
        raise NotImplementedError()  # pragma: no cover


class DatabaseSession:
    async def fetch(self, query: ClauseElement) -> typing.Any:
        raise NotImplementedError()  # pragma: no cover

    async def execute(self, query: ClauseElement) -> None:
        raise NotImplementedError()  # pragma: no cover
