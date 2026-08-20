from backend.observability.readiness import check_readiness


def test_readiness_reports_json_vector_backend(monkeypatch):
    monkeypatch.setenv("CHECKPOINT_STORAGE", "json")
    monkeypatch.setenv("VECTOR_BACKEND", "json")
    monkeypatch.setenv("AUTH_ENABLED", "false")

    readiness = check_readiness()

    assert readiness["checks"]["vector_backend"]["ok"] is True
    assert readiness["checks"]["vector_backend"]["backend"] == "json"


def test_readiness_rejects_pgvector_without_postgres_storage(monkeypatch):
    monkeypatch.setenv("CHECKPOINT_STORAGE", "json")
    monkeypatch.setenv("VECTOR_BACKEND", "pgvector")
    monkeypatch.setenv("AUTH_ENABLED", "false")

    readiness = check_readiness()

    assert readiness["ready"] is False
    assert readiness["checks"]["vector_backend"]["ok"] is False
    assert "CHECKPOINT_STORAGE=postgres" in readiness["checks"]["vector_backend"]["error"]
