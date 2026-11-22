"""Signing in and the two roles. The refusals matter most: nobody gets in without signing in, a developer can look
but never change, a wrong password and an unknown email look the same, and the last PM cannot be removed."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cognipm.api.deps import get_conn
from cognipm.api.main import app
from cognipm.auth import (
    COOKIE_NAME,
    authenticate,
    create_user,
    ensure_first_user,
    hash_password,
    password_problem,
    start_session,
    verify_password,
)
from tests.test_api import _Shared, build_api, draft_ids, start_p1

pytestmark = pytest.mark.real_auth

PASSWORD = "a long enough password"


# ---------- passwords and accounts ----------


def test_a_password_is_stored_salted_and_checks_only_the_right_one():
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)

    assert first != second  # a fresh salt each time
    assert PASSWORD not in first
    assert verify_password(PASSWORD, first) and verify_password(PASSWORD, second)
    assert not verify_password("a different password", first)


@pytest.mark.parametrize(
    "stored", ["", "plain text", "scrypt$x$y", "bcrypt$1$2$3$4$5", "scrypt$16384$8$1$!!$!!"]
)
def test_a_malformed_stored_hash_never_verifies_and_never_raises(stored):
    assert verify_password(PASSWORD, stored) is False


def test_short_passwords_are_refused_with_a_sentence():
    assert password_problem("short") == "A password needs at least 10 characters."
    assert password_problem(PASSWORD) is None


def test_the_database_never_holds_the_password_or_the_session_token(conn):
    user = create_user(conn, email="a@example.com", display_name="A", role="pm", password=PASSWORD)
    token = start_session(conn, user.id)

    stored = str(conn.execute("SELECT * FROM users").fetchall()) + str(
        conn.execute("SELECT * FROM sessions").fetchall()
    )

    assert PASSWORD not in stored and token not in stored


def test_an_email_can_only_have_one_account_whatever_its_capitals(conn):
    create_user(conn, email="Pat@Example.com", display_name="Pat", role="pm", password=PASSWORD)

    with pytest.raises(ValueError, match="already has an account"):
        create_user(conn, email="pat@example.com", display_name="Other", role="developer", password=PASSWORD)
    assert authenticate(conn, "PAT@EXAMPLE.COM", PASSWORD) is not None  # and signing in ignores capitals too


def test_the_first_account_comes_from_the_environment_once_and_never_resets_anything(
    conn, monkeypatch, capsys
):
    ensure_first_user(
        conn
    )  # nothing set: no account, and it says why on stderr (stdout belongs to the MCP transport)
    assert conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0
    captured = capsys.readouterr()
    assert captured.out == "" and "no accounts yet" in captured.err

    monkeypatch.setenv("COGNIPM_ADMIN_EMAIL", "boss@example.com")
    monkeypatch.setenv("COGNIPM_ADMIN_PASSWORD", PASSWORD)
    ensure_first_user(conn)
    assert authenticate(conn, "boss@example.com", PASSWORD).role == "pm"

    monkeypatch.setenv("COGNIPM_ADMIN_PASSWORD", "something else entirely")
    ensure_first_user(conn)  # someone exists now: a changed variable must not reset a password
    assert authenticate(conn, "boss@example.com", PASSWORD) is not None
    assert authenticate(conn, "boss@example.com", "something else entirely") is None


# ---------- the HTTP side ----------


@pytest.fixture
def client(conn):
    app.dependency_overrides[get_conn] = lambda: _Shared(conn)
    with TestClient(app) as c:
        c.conn = conn
        c.pm = create_user(conn, email="pm@example.com", display_name="Pat PM", role="pm", password=PASSWORD)
        c.dev = create_user(
            conn, email="dev@example.com", display_name="Dev Dana", role="developer", password=PASSWORD
        )
        yield c
    app.dependency_overrides.clear()


def sign_in(client, email="pm@example.com", password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_signing_in_sets_a_cookie_scripts_cannot_read_and_returns_who_you_are(client):
    response = sign_in(client)

    assert response.status_code == 200
    assert response.json() == {
        "id": client.pm.id,
        "email": "pm@example.com",
        "display_name": "Pat PM",
        "role": "pm",
        "disabled": False,
    }
    cookie = response.headers["set-cookie"].lower()
    assert COOKIE_NAME in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert "secure" not in cookie  # only when the site is served over https (COGNIPM_COOKIE_SECURE=1)
    assert client.get("/api/auth/me").json()["display_name"] == "Pat PM"
    assert "password" not in response.text


def test_the_cookie_is_marked_secure_when_the_site_is_on_https(client, monkeypatch):
    monkeypatch.setenv("COGNIPM_COOKIE_SECURE", "1")

    assert "secure" in sign_in(client).headers["set-cookie"].lower()


def test_a_wrong_password_and_an_unknown_email_get_the_same_answer_and_no_session(client):
    wrong = sign_in(client, password="not the password")
    unknown = sign_in(client, email="nobody@example.com")

    assert (wrong.status_code, wrong.json()) == (401, {"detail": "Wrong email or password."})
    assert (unknown.status_code, unknown.json()) == (401, wrong.json())
    assert COOKIE_NAME not in wrong.headers.get("set-cookie", "")
    assert client.conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"] == 0
    refused = client.conn.execute(
        "SELECT detail FROM audit_log WHERE action = 'login' AND outcome = 'refused'"
    ).fetchall()
    assert len(refused) == 2 and all(
        PASSWORD not in r["detail"] for r in refused
    )  # the attempts are logged, no secrets


def test_a_disabled_account_cannot_sign_in(client):
    sign_in(client)
    client.patch(f"/api/users/{client.dev.id}", json={"disabled": True})
    client.post("/api/auth/logout")

    assert sign_in(client, email="dev@example.com").status_code == 401


def test_signing_out_ends_the_session_and_works_even_when_nobody_was_signed_in(client):
    sign_in(client)
    assert client.post("/api/auth/logout").status_code == 204

    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/logout").status_code == 204


def test_an_expired_session_is_not_a_session(client):
    sign_in(client)
    client.conn.execute("UPDATE sessions SET expires_at = now() - interval '1 minute'")
    client.conn.commit()

    assert client.get("/api/auth/me").status_code == 401


def test_a_forged_or_unknown_cookie_gets_nothing(client):
    client.cookies.set(COOKIE_NAME, "made-up-token")

    assert client.get("/api/runs").status_code == 401


@pytest.mark.parametrize(
    "path",
    [
        "/api/runs",
        "/api/audit",
        "/api/documents",
        "/api/settings",
        "/api/insights",
        "/api/artifacts",
        "/api/modes",
        "/api/project",
        "/api/stories",
        "/api/chat/sessions",
        "/api/insights/export.csv",
        "/api/audit/export.csv",
    ],
)
def test_nothing_is_served_to_someone_who_is_not_signed_in(client, path):
    assert client.get(path).status_code == 401


def test_only_health_and_sign_in_work_without_signing_in(client):
    assert client.get("/api/health").status_code == 200
    assert (
        client.post("/api/auth/login", json={"email": "x", "password": "y"}).status_code == 401
    )  # reachable, refused


# ---------- the two roles ----------

CHANGES = [
    ("post", "/api/runs", {"task": "p1", "input_text": "notes"}),
    ("post", "/api/runs/nope/approve", None),
    ("post", "/api/runs/nope/reject", None),
    ("post", "/api/runs/nope/rerun", {"note": "again"}),
    ("patch", "/api/changes/nope", {"summary": "x"}),
    ("post", "/api/documents", {"title": "t", "text": "x"}),
    ("delete", "/api/documents/nope", None),
    ("delete", "/api/documents", None),
    ("post", "/api/chat", {"message": "hello"}),
    ("delete", "/api/chat/sessions/nope", None),
    ("post", "/api/settings/test-jira", None),
    ("post", "/api/settings/test-model", None),
    ("post", "/api/settings/clear-run-inputs", None),
]


@pytest.mark.parametrize(("method", "path", "body"), CHANGES)
def test_a_developer_can_never_change_anything(client, method, path, body):
    sign_in(client, email="dev@example.com")

    response = getattr(client, method)(path, **({"json": body} if body is not None else {}))

    assert response.status_code == 403
    assert response.json()["detail"] == "Your account can look but not change anything. Ask a PM."


@pytest.mark.parametrize(
    "path",
    [
        "/api/runs",
        "/api/audit",
        "/api/documents",
        "/api/settings",
        "/api/insights",
        "/api/modes",
        "/api/audit/export.csv",
    ],
)
def test_a_developer_can_look_at_everything(client, path):
    sign_in(client, email="dev@example.com")

    assert client.get(path).status_code == 200


def test_a_developer_can_sign_out_even_though_that_is_a_change(client):
    sign_in(client, email="dev@example.com")

    assert client.post("/api/auth/logout").status_code == 204


def test_a_developer_sees_a_run_that_waits_for_review_but_has_no_way_to_decide(client):
    client.conn.execute(
        "INSERT INTO runs (id, mode, task_type, agent, scope, status) VALUES ('r1', 'M2', 'p1', 'a', 's', 'awaiting_review')"
    )
    client.conn.execute(
        "INSERT INTO staged_changes (id, run_id, kind, payload, sources, reasoning) VALUES "
        "('c1', 'r1', 'backlog_item', '{\"summary\": \"x\"}', '[\"q\"]', 'because')"
    )
    client.conn.commit()

    sign_in(client, email="dev@example.com")
    as_developer = client.get("/api/runs/r1").json()
    client.post("/api/auth/logout")
    sign_in(client)
    as_pm = client.get("/api/runs/r1").json()

    assert (as_developer["can_decide"], as_developer["editable"]) == (False, False)
    assert (as_pm["can_decide"], as_pm["editable"]) == (True, True)
    assert len(as_developer["drafts"]) == 1  # looking is allowed: the drafts are there


# ---------- people ----------


def test_a_developer_cannot_even_list_who_has_an_account(client):
    sign_in(client, email="dev@example.com")

    assert client.get("/api/users").status_code == 403
    assert (
        client.post(
            "/api/users",
            json={"email": "x@example.com", "display_name": "X", "role": "pm", "password": PASSWORD},
        ).status_code
        == 403
    )


def test_a_pm_adds_a_person_and_the_password_is_never_sent_back(client):
    sign_in(client)

    response = client.post(
        "/api/users",
        json={"email": " New@Example.com ", "display_name": "New", "role": "developer", "password": PASSWORD},
    )

    assert response.status_code == 201 and response.json()["email"] == "New@Example.com"
    assert PASSWORD not in response.text and "password" not in response.text
    assert PASSWORD not in client.get("/api/users").text
    assert sign_in(client, email="new@example.com").status_code == 200


def test_adding_a_duplicate_or_a_weak_account_is_refused(client):
    sign_in(client)
    body = {"email": "pm@example.com", "display_name": "Copy", "role": "pm", "password": PASSWORD}

    assert client.post("/api/users", json=body).status_code == 409
    assert (
        client.post("/api/users", json=body | {"email": "other@example.com", "password": "short"}).status_code
        == 422
    )
    assert client.post("/api/users", json=body | {"email": "not-an-email"}).status_code == 422


def test_the_last_pm_cannot_be_demoted_or_disabled_but_another_can(client):
    sign_in(client)

    assert client.patch(f"/api/users/{client.pm.id}", json={"role": "developer"}).status_code == 409
    assert client.patch(f"/api/users/{client.pm.id}", json={"disabled": True}).status_code == 409
    second = client.post(
        "/api/users",
        json={"email": "two@example.com", "display_name": "Two", "role": "pm", "password": PASSWORD},
    ).json()

    assert client.patch(f"/api/users/{second['id']}", json={"disabled": True}).status_code == 200
    assert (
        client.patch(f"/api/users/{client.pm.id}", json={"disabled": True}).status_code == 409
    )  # a disabled PM is not a PM


def test_changing_a_role_or_a_password_signs_that_person_out_at_once(client):
    sign_in(client, email="dev@example.com")
    dev_cookie = client.cookies.get(COOKIE_NAME)
    client.cookies.clear()
    sign_in(client)

    client.patch(f"/api/users/{client.dev.id}", json={"password": "a brand new password"})

    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, dev_cookie)
    assert client.get("/api/auth/me").status_code == 401  # the old sign-in is gone
    assert sign_in(client, email="dev@example.com").status_code == 401  # and the old password no longer works
    assert sign_in(client, email="dev@example.com", password="a brand new password").status_code == 200


def test_changes_to_people_are_in_the_log_without_any_password(client):
    sign_in(client)
    client.patch(f"/api/users/{client.dev.id}", json={"password": "a brand new password", "role": "pm"})

    rows = client.conn.execute(
        "SELECT detail FROM audit_log WHERE action IN ('create_user', 'update_user', 'login')"
    ).fetchall()
    text = " ".join(str(r["detail"]) for r in rows)

    assert "update_user" in str(client.conn.execute("SELECT action FROM audit_log").fetchall())
    assert "a brand new password" not in text and PASSWORD not in text
    assert "password" in text  # that the password was changed is recorded; what it was never is


def test_unknown_people_and_empty_changes_are_refused(client):
    sign_in(client)

    assert client.patch("/api/users/nope", json={"role": "pm"}).status_code == 404
    assert client.patch(f"/api/users/{client.dev.id}", json={}).status_code == 422


# ---------- who did it ----------


def test_an_approval_names_the_person_in_the_log_and_in_jira(conn):
    api = build_api(conn)
    pm = create_user(conn, email="pm@example.com", display_name="Pat PM", role="pm", password=PASSWORD)
    with TestClient(app) as client:
        api.client = client
        assert sign_in(client).status_code == 200
        detail = start_p1(api)
        client.patch(f"/api/changes/{draft_ids(detail)[0]}", json={"summary": "Reset it"})
        assert client.post(f"/api/runs/{detail['run']['id']}/approve").status_code == 200

        log = client.get("/api/audit").json()["rows"]
        library = client.get("/api/artifacts").json()["items"]

    decisions = [r for r in log if r["action"] in ("edit_draft", "approve", "create_issue")]
    assert decisions and all(
        r["actor"] == f"human:{pm.id}" and r["actor_name"] == "Pat PM" for r in decisions
    )
    assert {i["approved_by_name"] for i in library} == {"Pat PM"}
    comments = [text for _, text in api.jira.comments]
    assert comments and all("Approved by Pat PM" in text for text in comments)  # a name, not an id
    app.dependency_overrides.clear()


def test_entries_from_before_sign_in_still_read_as_the_shared_reviewer(client):
    client.conn.execute(
        "INSERT INTO audit_log (actor, mode, action, outcome) VALUES ('human:reviewer', 'M2', 'approve', 'applied')"
    )
    client.conn.commit()
    sign_in(client)

    [row] = [r for r in client.get("/api/audit").json()["rows"] if r["action"] == "approve"]

    assert row["actor"] == "human:reviewer" and row["actor_name"] is None
