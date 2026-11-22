"""Personal passwords: chosen once, kept, visible to the lecturer for testing."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app  # noqa: E402
from test_flow import TestConfig  # noqa: E402


class PwConfig(TestConfig):
    REQUIRE_PIN = True
    REQUIRE_LECTURER_PASSWORD = True
    SHOW_PASSWORDS = True


def login_student(app, pin, sid="100000001"):
    return app.test_client().post("/api/login/student", json={"student_id": sid, "pin": pin})


def login_lecturer(app, password):
    client = app.test_client()
    return client, client.post("/api/login/lecturer", json={"lecturer_id": "maayan", "key": "test-key", "password": password})


def test_student_password_is_chosen_once_and_cannot_be_changed():
    app = create_app(PwConfig)
    assert login_student(app, "1234").get_json()["ok"]
    assert login_student(app, "9999").status_code == 400      # a second value does not replace the first
    assert login_student(app, "1234").get_json()["ok"]


def test_lecturer_password_is_chosen_once_and_required():
    app = create_app(PwConfig)
    assert login_lecturer(app, "")[1].status_code == 400
    assert login_lecturer(app, "my-secret")[1].get_json()["ok"]
    assert login_lecturer(app, "other-one")[1].status_code == 400
    assert login_lecturer(app, "my-secret")[1].get_json()["ok"]


def test_lecturer_downloads_passwords_and_others_cannot():
    app = create_app(PwConfig)
    login_student(app, "4321")
    client, _ = login_lecturer(app, "my-secret")
    text = client.get("/lecturer/passwords.csv").get_data(as_text=True)
    assert "100000001" in text and "4321" in text and "my-secret" in text
    assert app.test_client().get("/lecturer/passwords.csv").status_code == 403


def test_passwords_survive_a_restart_when_a_file_is_configured(tmp_path):
    class Kept(PwConfig):
        PASSWORDS_PATH = str(tmp_path / "pw.json")
    first = create_app(Kept)
    assert login_student(first, "2468").get_json()["ok"]
    second = create_app(Kept)
    assert login_student(second, "1111").status_code == 400
    assert login_student(second, "2468").get_json()["ok"]


def test_plain_passwords_hidden_when_switched_off():
    class Hidden(PwConfig):
        SHOW_PASSWORDS = False
    app = create_app(Hidden)
    login_student(app, "4321")
    client, _ = login_lecturer(app, "my-secret")
    text = client.get("/lecturer/passwords.csv").get_data(as_text=True)
    assert "4321" not in text and "True" in text
