from fastapi.testclient import TestClient

from main import VERSION, app


def test_the_version_is_defined_once_and_reported_everywhere():
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
    assert VERSION == "1.3.0"
    assert app.version == VERSION
    assert client.get("/").json()["version"] == VERSION
