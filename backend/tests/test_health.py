from app.extensions import db


def test_health_ok(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "database": "ok"}


def test_health_reports_database_error(client, monkeypatch):
    def broken_execute(*args, **kwargs):
        raise RuntimeError("database is down")

    monkeypatch.setattr(db.session, "execute", broken_execute)

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.get_json()["database"] == "error"
