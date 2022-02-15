import typing
from cgi import parse_header

from starlette.datastructures import FormData, Headers, UploadFile

try:
    from baize import multipart
except ImportError:  # pragma: nocover
    multipart = None  # type: ignore[assignment]


class MultiPartParser:
    def __init__(
        self, headers: Headers, stream: typing.AsyncGenerator[bytes, None]
    ) -> None:
        assert (
            multipart is not None
        ), "The `baize` library must be installed to use form parsing."
        self.headers = headers
        self.stream = stream

    async def parse(self) -> FormData:
        # Parse the Content-Type header to get the multipart boundary.
        content_type, params = parse_header(self.headers["Content-Type"])
        charset = params.get("charset", "utf-8")
        boundary = params["boundary"]
        parser = multipart.MultipartDecoder(boundary.encode("latin-1"), charset)
        field_name = ""
        data = bytearray()
        file: typing.Optional[UploadFile] = None

        items: typing.List[typing.Tuple[str, typing.Union[str, UploadFile]]] = []

        async for chunk in self.stream:
            parser.receive_data(chunk)
            while True:
                event = parser.next_event()
                if isinstance(event, (multipart.Epilogue, multipart.NeedData)):
                    break
                elif isinstance(event, multipart.Field):
                    field_name = event.name
                elif isinstance(event, multipart.File):
                    field_name = event.name
                    file = UploadFile(
                        event.filename,
                        content_type=event.headers.get("content-type", ""),
                        headers=Headers(
                            raw=[
                                (key.encode(charset), value.encode(charset))
                                for key, value in event.headers.items()
                            ]
                        ),
                    )
                elif isinstance(event, multipart.Data):
                    if file is None:
                        data.extend(event.data)
                    else:
                        await file.write(event.data)

                    if not event.more_data:
                        if file is None:
                            items.append(
                                (field_name, multipart.safe_decode(data, charset))
                            )
                            data.clear()
                        else:
                            await file.seek(0)
                            items.append((field_name, file))
                            file = None

        return FormData(items)
