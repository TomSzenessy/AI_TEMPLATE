import pytest

from notes import create_app


@pytest.fixture()
def client(tmp_path):
    return create_app(str(tmp_path / "test.db")).test_client()


def test_create_and_list(client):
    assert client.post("/notes", json={"title": "Standup", "body": "Ship it"}).status_code == 201
    notes = client.get("/notes").get_json()
    assert [note["title"] for note in notes] == ["Standup"]


def test_title_required(client):
    assert client.post("/notes", json={"body": "no title"}).status_code == 400


def test_delete_missing_note(client):
    assert client.delete("/notes/99").status_code == 404
