"""Accounts, server-side CVs and the free-tier gate.

Every test names the mutation that makes it fail; those mutations are also listed
in the pull request. Nothing here touches a network: the provider is a stub.
"""
from __future__ import annotations

import pytest

import admin as admin_cli
import app as elevate
import store

PASSWORD = "correct horse battery staple"


class StubBackend:
    """A provider that records every request it receives."""

    def __init__(self, text: str = "STUB ANSWER"):
        self.text = text
        self.model = "stub-model"
        self.base_url = "https://provider.invalid/v1"
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.text


class FailingBackend(StubBackend):
    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        raise RuntimeError("provider is down")


@pytest.fixture
def app(tmp_path):
    elevate.LOGIN_FAILURES.clear()
    application = elevate.create_app(
        {
            "ELEVATE_DB_PATH": str(tmp_path / "elevate.db"),
            "SECRET_KEY": "test-secret-key",
            "TESTING": True,
        }
    )
    try:
        yield application
    finally:
        elevate.LOGIN_FAILURES.clear()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    conn = store.connect(app.config["ELEVATE_DB_PATH"])
    try:
        yield conn
    finally:
        conn.close()


def page_csrf(client) -> str:
    """The CSRF token the signup/login forms carry."""
    client.get("/signup")
    with client.session_transaction() as sess:
        return sess["csrf"]


def session_csrf(client) -> str:
    with client.session_transaction() as sess:
        return sess["csrf"]


def signup(client, email="a@example.com", password=PASSWORD):
    token = page_csrf(client)
    return client.post(
        "/signup", json={"email": email, "password": password, "csrf_token": token}
    )


def use_provider(app, backend):
    app.config["ELEVATE_BACKEND_FACTORY"] = lambda: backend
    return backend


# 1 ------------------------------------------------------------------------
def test_signup_creates_a_user_and_never_stores_the_password(app, client, db):
    """Mutation: store the raw password -> the hash assertions fail."""
    resp = signup(client)
    assert resp.status_code == 201, resp.get_json()

    row = db.execute("SELECT * FROM users WHERE email = ?", ("a@example.com",)).fetchone()
    assert row is not None
    assert row["password_hash"] != PASSWORD
    assert PASSWORD not in row["password_hash"]
    assert row["password_hash"].startswith("pbkdf2:") or ":" in row["password_hash"]
    assert row["plan"] == "free"
    assert row["ai_calls"] == 0
    with client.session_transaction() as sess:
        assert sess["user_id"] == row["id"]


# 2 ------------------------------------------------------------------------
def test_duplicate_email_is_rejected_and_case_and_space_variants_collide(app, db):
    """Mutation: skip normalisation -> the variant creates a second account."""
    assert signup(app.test_client(), "Dup@Example.com ").status_code == 201
    again = signup(app.test_client(), "  dup@example.COM")
    assert again.status_code == 409
    assert "already registered" in again.get_json()["error"].lower()
    count = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    assert count == 1


# 3 ------------------------------------------------------------------------
def test_login_succeeds_fails_and_locks_after_five_failures(app, client):
    """Mutation: drop the failure counter -> the 6th attempt is 401, not 429."""
    signup(client)

    good = app.test_client()
    token = page_csrf(good)
    ok = good.post(
        "/login", json={"email": "a@example.com", "password": PASSWORD, "csrf_token": token}
    )
    assert ok.status_code == 200
    with good.session_transaction() as sess:
        assert sess["user_id"] is not None
        assert sess["csrf"] != token  # the session was regenerated on login

    bad = app.test_client()
    token = page_csrf(bad)
    for attempt in range(5):
        resp = bad.post(
            "/login",
            json={"email": "a@example.com", "password": "wrong password", "csrf_token": token},
        )
        assert resp.status_code == 401, f"attempt {attempt + 1}"
    sixth = bad.post(
        "/login",
        json={"email": "a@example.com", "password": "wrong password", "csrf_token": token},
    )
    assert sixth.status_code == 429


# 4 ------------------------------------------------------------------------
def test_cv_endpoints_require_a_session(client):
    """Mutation: read the CV from the body/cookie -> these are 200, not 401."""
    assert client.get("/api/cv").status_code == 401
    assert client.put("/api/cv", json={"content": {"name": "Nobody"}}).status_code == 401


# 5 ------------------------------------------------------------------------
def test_one_user_cannot_read_or_overwrite_another_users_cv(app, client, db):
    """Mutation: write by the id in the payload -> Alice's CV becomes "B WAS HERE"."""
    signup(client, "a@example.com")
    assert client.put("/api/cv", json={"content": {"name": "Alice"}}).status_code == 200

    other = app.test_client()
    signup(other, "b@example.com")
    assert other.get("/api/cv").get_json()["cv"] is None

    alice_row = db.execute(
        "SELECT c.id FROM cvs c JOIN users u ON u.id = c.user_id WHERE u.email = ?",
        ("a@example.com",),
    ).fetchone()
    assert alice_row is not None

    # B guesses A's CV id and tries to overwrite it.
    resp = other.put(
        "/api/cv",
        json={"id": alice_row["id"], "user_id": 1, "content": {"name": "B WAS HERE"}},
    )
    assert resp.status_code == 200

    assert client.get("/api/cv").get_json()["cv"]["name"] == "Alice"
    assert other.get("/api/cv").get_json()["cv"]["name"] == "B WAS HERE"


# 6 ------------------------------------------------------------------------
def test_free_user_gets_three_ai_calls_then_402_without_calling_the_provider(app, client):
    """Mutation: increment before the call, or drop the gate -> 4 stub calls / a 200."""
    signup(client)
    stub = use_provider(app, StubBackend())

    for _ in range(3):
        assert client.post("/api/ai/bullets", json={"role": "HR", "notes": "n"}).status_code == 200

    fourth = client.post("/api/ai/star", json={"role": "HR", "question": "q", "notes": "n"})
    assert fourth.status_code == 402
    body = fourth.get_json()
    assert body["limit"] == 3
    assert body["used"] == 3
    assert body["remaining"] == 0
    assert "admin.py grant" in body["upgrade"]
    assert "not called" in body["error"]
    assert len(stub.calls) == 3  # the capped call never reached the provider


# 7 ------------------------------------------------------------------------
def test_pro_user_is_allowed_past_the_free_limit(app, client, db):
    """Mutation: hardcode the limit at 3 -> the 4th call is 402 for a Pro user."""
    signup(client)
    assert store.grant_plan(db, "a@example.com", "pro") is True
    stub = use_provider(app, StubBackend())

    for _ in range(4):
        assert client.post("/api/ai/bullets", json={"role": "HR", "notes": "n"}).status_code == 200
    assert len(stub.calls) == 4

    usage = store.ai_usage(db, db.execute("SELECT id FROM users").fetchone()["id"])
    assert usage["plan"] == "pro"
    assert usage["limit"] == store.PLANS["pro"] == 200
    assert usage["used"] == 4


# 8 ------------------------------------------------------------------------
def test_a_failed_provider_call_does_not_burn_credit(app, client, db):
    """Mutation: increment the counter before the provider answers -> used == 1."""
    signup(client)
    use_provider(app, FailingBackend())

    resp = client.post("/api/ai/bullets", json={"role": "HR", "notes": "n"})
    assert resp.status_code == 502
    used = db.execute("SELECT ai_calls FROM users WHERE email = ?", ("a@example.com",)).fetchone()
    assert used["ai_calls"] == 0


# 9 ------------------------------------------------------------------------
def test_account_delete_removes_the_user_and_the_cvs(app, client, db):
    """Mutation: drop ON DELETE CASCADE / the delete -> rows survive, login still works."""
    signup(client)
    assert client.put("/api/cv", json={"content": {"name": "Alice"}}).status_code == 200

    token = session_csrf(client)
    wrong = client.post(
        "/api/account/delete", json={"password": "not my password", "csrf_token": token}
    )
    assert wrong.status_code == 403
    assert db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 1

    token = session_csrf(client)
    resp = client.post("/api/account/delete", json={"password": PASSWORD, "csrf_token": token})
    assert resp.status_code == 200

    assert db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 0
    assert db.execute("SELECT COUNT(*) AS c FROM cvs").fetchone()["c"] == 0
    assert client.get("/api/cv").status_code == 401

    login_again = app.test_client()
    token = page_csrf(login_again)
    after = login_again.post(
        "/login", json={"email": "a@example.com", "password": PASSWORD, "csrf_token": token}
    )
    assert after.status_code == 401


# 10 -----------------------------------------------------------------------
def test_missing_secret_key_outside_dev_refuses_to_start(tmp_path, monkeypatch):
    """Mutation: generate a random key silently -> no RuntimeError and sessions sign with it."""
    monkeypatch.delenv("ELEVATE_SECRET_KEY", raising=False)
    monkeypatch.delenv("ELEVATE_DEV", raising=False)
    with pytest.raises(RuntimeError) as excinfo:
        elevate.create_app({"ELEVATE_DB_PATH": str(tmp_path / "refused.db")})
    assert "ELEVATE_SECRET_KEY" in str(excinfo.value)


def test_dev_mode_without_a_secret_key_starts_with_one_loud_warning(tmp_path, monkeypatch, capsys):
    """Mutation: drop the ELEVATE_DEV branch -> dev cannot start at all."""
    monkeypatch.delenv("ELEVATE_SECRET_KEY", raising=False)
    monkeypatch.setenv("ELEVATE_DEV", "1")
    application = elevate.create_app({"ELEVATE_DB_PATH": str(tmp_path / "dev.db")})
    assert application.secret_key
    assert "ELEVATE_SECRET_KEY is not set" in capsys.readouterr().err


# CSRF ----------------------------------------------------------------------
def test_signup_without_a_csrf_token_is_rejected(app, client, db):
    """Mutation: remove _csrf_ok() from /signup -> the account is created."""
    client.get("/signup")
    resp = client.post("/signup", json={"email": "c@example.com", "password": PASSWORD})
    assert resp.status_code == 400
    assert db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 0


def test_signup_with_a_wrong_csrf_token_is_rejected(client, db):
    """Mutation: compare only that a token is present -> the wrong token is accepted."""
    client.get("/signup")
    resp = client.post(
        "/signup",
        json={"email": "d@example.com", "password": PASSWORD, "csrf_token": "not-the-token"},
    )
    assert resp.status_code == 400
    assert db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 0


def test_delete_without_a_csrf_token_keeps_the_account(app, client, db):
    """Mutation: remove _csrf_ok() from the delete route -> the account is deleted."""
    signup(client)
    resp = client.post("/api/account/delete", json={"password": PASSWORD})
    assert resp.status_code == 400
    assert db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 1


# Cookie flags --------------------------------------------------------------
def test_session_cookie_flags_follow_dev_mode(tmp_path, monkeypatch):
    """Mutation: hardcode Secure=True -> dev fails; hardcode False -> production fails."""
    monkeypatch.setenv("ELEVATE_SECRET_KEY", "a-real-secret")
    monkeypatch.delenv("ELEVATE_DEV", raising=False)
    production = elevate.create_app({"ELEVATE_DB_PATH": str(tmp_path / "prod.db")})
    assert production.config["SESSION_COOKIE_SECURE"] is True
    assert production.config["SESSION_COOKIE_HTTPONLY"] is True
    assert production.config["SESSION_COOKIE_SAMESITE"] == "Lax"

    monkeypatch.setenv("ELEVATE_DEV", "1")
    dev = elevate.create_app({"ELEVATE_DB_PATH": str(tmp_path / "dev-cookie.db")})
    assert dev.config["SESSION_COOKIE_SECURE"] is False


# Anonymous use -------------------------------------------------------------
def test_anonymous_visitors_still_work_with_three_calls_in_the_cookie(app, client):
    """Mutation: require a session for AI -> 401 instead of 200/402."""
    stub = use_provider(app, StubBackend())
    for _ in range(3):
        assert client.post("/api/ai/bullets", json={"role": "HR", "notes": "n"}).status_code == 200
    capped = client.post("/api/ai/bullets", json={"role": "HR", "notes": "n"})
    assert capped.status_code == 402
    assert capped.get_json()["plan"].startswith("anonymous")
    assert len(stub.calls) == 3
    # Anonymous CV building is untouched: no account needed for the browser-local CV.
    assert client.get("/").status_code == 200
    assert client.get("/api/roles").status_code == 200


# Operator CLI --------------------------------------------------------------
def test_admin_cli_grants_and_revokes_a_plan(app, db, monkeypatch, capsys):
    """Mutation: make grant_plan a no-op -> the plan never changes."""
    signup(app.test_client())
    monkeypatch.setenv("ELEVATE_DB_PATH", app.config["ELEVATE_DB_PATH"])

    assert admin_cli.main(["grant", "A@Example.com", "pro"]) == 0
    assert "pro plan" in capsys.readouterr().out
    row = db.execute("SELECT plan FROM users WHERE email = 'a@example.com'").fetchone()
    assert row["plan"] == "pro"

    assert admin_cli.main(["revoke", "a@example.com"]) == 0
    row = db.execute("SELECT plan FROM users WHERE email = 'a@example.com'").fetchone()
    assert row["plan"] == "free"

    assert admin_cli.main(["grant", "nobody@example.com", "pro"]) == 1
