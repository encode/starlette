import hashlib

# TODO: Remove when dropping support for PY38. a try/except is used to
# detect whether the usedforsecurity argument is available as this fix may also
# have been applied by downstream package maintainers to other versions in
# their repositories.
try:

    hashlib.md5(b"data", usedforsecurity=True)  # type: ignore[call-arg]

    def md5_hexdigest(data: bytes, *, usedforsecurity: bool = True) -> str:
        return hashlib.md5(  # type: ignore[call-arg]
            data, usedforsecurity=usedforsecurity
        ).hexdigest()


except TypeError:

    def md5_hexdigest(data: bytes, *, usedforsecurity: bool = True) -> str:
        return hashlib.md5(data).hexdigest()
