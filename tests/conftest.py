import os

import pytest


@pytest.fixture(
    params=[
        pytest.param(("asyncio", {"use_uvloop": True}), id="asyncio+uvloop"),
        pytest.param(("asyncio", {"use_uvloop": False}), id="asyncio"),
        pytest.param(
            ("trio", {"restrict_keyboard_interrupt_to_checkpoints": True}), id="trio"
        ),
    ],
    autouse=True,
)
def anyio_backend(request):
    os.environ["STARLETTE_TESTCLIENT_ASYNC_BACKEND"] = request.param[0]
    return request.param


@pytest.fixture
def no_trio_support(request):
    if request.keywords.get("trio"):
        pytest.skip("Trio not supported (yet!)")
