from starlette import asgi_application, Response, TestClient


def test_text_response():
    @asgi_application
    def app(request):
        return Response("hello, world", media_type="text/plain")

    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.text == "hello, world"
