import hashlib
import inspect

# TODO: Remove when dropping support for PY38. inspect.signature() is used to
# detect whether the usedforsecurity argument is available as this fix may also
# have been applied by downstream package maintainers to other versions in
# their repositories.
if "usedforsecurity" in inspect.signature(hashlib.md5).parameters:

    def md5_hexdigest(data: bytes, *, usedforsecurity: bool = True) -> str:
        return hashlib.md5(data, usedforsecurity=usedforsecurity).hexdigest()


else:

    def md5_hexdigest(data: bytes, *, usedforsecurity: bool = True) -> str:
        return hashlib.md5(data).hexdigest()
