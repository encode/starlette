from enum import Enum
from starlette.datastructures import Headers
import asyncio
import tempfile
import typing

try:
    from multipart.multipart import parse_options_header
    import multipart
except ImportError:  # pragma: nocover
    parse_options_header = None  # type: ignore
    multipart = None  # type: ignore


class MessageType(Enum):
    PART_BEGIN = 1
    PART_DATA = 2
    PART_END = 3
    HEADER_FIELD = 4
    HEADER_VALUE = 5
    HEADER_END = 6
    HEADERS_FINISHED = 7
    END = 8


class UploadFile:
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self._file = None
        self._loop = asyncio.get_event_loop()

    async def setup(self) -> None:
        self._file = await self._loop.run_in_executor(
            None, tempfile.SpooledTemporaryFile
        )

    async def write(self, data: bytes) -> None:
        await self._loop.run_in_executor(None, self._file.write, data)

    async def read(self, size: int = None) -> bytes:
        return await self._loop.run_in_executor(None, self._file.read, size)

    async def seek(self, offset: int) -> None:
        await self._loop.run_in_executor(None, self._file.seek, offset)

    async def close(self) -> None:
        await self._loop.run_in_executor(None, self._file.close)


class MultiPartParser:
    def __init__(
        self, headers: Headers, stream: typing.AsyncGenerator[bytes, None]
    ) -> None:
        assert (
            multipart is not None
        ), "The `python-multipart` library must be installed to use form parsing."
        self.headers = headers
        self.stream = stream
        self.messages = []  # type: typing.List[typing.Tuple[MessageType, bytes]]

    def on_part_begin(self) -> None:
        message = (MessageType.PART_BEGIN, b"")
        self.messages.append(message)

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        message = (MessageType.PART_DATA, data[start:end])
        self.messages.append(message)

    def on_part_end(self) -> None:
        message = (MessageType.PART_END, b"")
        self.messages.append(message)

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        message = (MessageType.HEADER_FIELD, data[start:end])
        self.messages.append(message)

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        message = (MessageType.HEADER_VALUE, data[start:end])
        self.messages.append(message)

    def on_header_end(self) -> None:
        message = (MessageType.HEADER_END, b"")
        self.messages.append(message)

    def on_headers_finished(self) -> None:
        message = (MessageType.HEADERS_FINISHED, b"")
        self.messages.append(message)

    def on_end(self) -> None:
        message = (MessageType.END, b"")
        self.messages.append(message)

    async def parse(self) -> typing.Dict[str, typing.Union[str, UploadFile]]:
        # Parse the Content-Type header to get the multipart boundary.
        content_type, params = parse_options_header(self.headers["Content-Type"])
        boundary = params.get(b"boundary")

        # Callbacks dictionary.
        callbacks = {
            "on_part_begin": self.on_part_begin,
            "on_part_data": self.on_part_data,
            "on_part_end": self.on_part_end,
            "on_header_field": self.on_header_field,
            "on_header_value": self.on_header_value,
            "on_header_end": self.on_header_end,
            "on_headers_finished": self.on_headers_finished,
            "on_end": self.on_end,
        }

        # Create the parser.
        parser = multipart.MultipartParser(boundary, callbacks)
        header_field = b""
        header_value = b""
        raw_headers = []  # type: typing.List[typing.Tuple[bytes, bytes]]
        field_name = ""
        data = b""
        file = None  # type: UploadFile

        result = {}  # type: typing.Dict[str, typing.Union[str, UploadFile]]

        # Feed the parser with data from the request.
        async for chunk in self.stream():
            parser.write(chunk)
            for message_type, message_bytes in self.messages:
                if message_type == MessageType.PART_BEGIN:
                    raw_headers = []
                    data = b""
                elif message_type == MessageType.HEADER_FIELD:
                    header_field += message_bytes
                elif message_type == MessageType.HEADER_VALUE:
                    header_value += message_bytes
                elif message_type == MessageType.HEADER_END:
                    raw_headers.append((header_field.lower(), header_value))
                    header_field = b""
                    header_value = b""
                elif message_type == MessageType.HEADERS_FINISHED:
                    headers = Headers(raw_headers)
                    content_disposition = headers.get("Content-Disposition")
                    disposition, options = parse_options_header(content_disposition)
                    field_name = options[b"name"].decode("latin-1")
                    if b"filename" in options:
                        filename = options[b"filename"].decode("latin-1")
                        file = UploadFile(filename=filename)
                        await file.setup()
                elif message_type == MessageType.PART_DATA:
                    if file is None:
                        data += message_bytes
                    else:
                        await file.write(message_bytes)
                elif message_type == MessageType.PART_END:
                    if file is None:
                        result[field_name] = data.decode("latin-1")
                    else:
                        await file.seek(0)
                        result[field_name] = file
                elif message_type == MessageType.END:
                    pass

        return result
