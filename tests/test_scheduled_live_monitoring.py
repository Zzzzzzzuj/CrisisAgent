from __future__ import annotations

import argparse

from scripts.run_scheduled_live_monitor import build_request, main, run_once


def test_scheduler_defaults_to_offline_request():
    args = argparse.Namespace(entity_id=None, provider=None, background=False, live_fetch=False)
    request = build_request(args)
    assert request["live_fetch"] is False
    assert request["background"] is False


def test_scheduler_disabled_does_not_enter_loop(monkeypatch, capsys):
    monkeypatch.delenv("ENABLE_SCHEDULED_LIVE_MONITOR", raising=False)
    monkeypatch.setattr("scripts.run_scheduled_live_monitor.run_once", lambda _args: (_ for _ in ()).throw(AssertionError("must not run")))
    assert main([]) == 0
    assert "disabled" in capsys.readouterr().out.lower()


def test_once_reads_enabled_watchlists_and_does_not_run_agent(monkeypatch, tmp_path):
    monkeypatch.setenv("WATCHLIST_STORE_PATH", str(tmp_path / "watchlists.json"))
    monkeypatch.setenv("LIVE_MONITOR_RUN_STORE_PATH", str(tmp_path / "runs.json"))
    monkeypatch.setattr("scripts.run_scheduled_live_monitor.get_watchlist_store", lambda: type("Store", (), {"list": lambda self, enabled=True: [{"entity_id": "e1", "entity_name": "Acme"}]})())
    calls = []
    monkeypatch.setattr("scripts.run_scheduled_live_monitor.execute_monitor_payload", lambda payload, run_id: calls.append((payload, run_id)) or {"status": "completed", "item_count": 0, "alert_count": 0})
    args = argparse.Namespace(entity_id="e1", provider="gdelt_doc", background=False, live_fetch=False)
    result = run_once(args)
    assert result["status"] == "completed"
    assert result["automatic_publish"] is False
    assert calls and calls[0][0]["live_fetch"] is False


def test_live_fetch_requires_server_switch(monkeypatch, tmp_path):
    monkeypatch.setenv("WATCHLIST_STORE_PATH", str(tmp_path / "watchlists.json"))
    monkeypatch.delenv("ENABLE_API_LIVE_FETCH", raising=False)
    monkeypatch.setattr("scripts.run_scheduled_live_monitor.get_watchlist_store", lambda: type("Store", (), {"list": lambda self, enabled=True: [{"entity_id": "e1"}]})())
    args = argparse.Namespace(entity_id="e1", provider="gdelt_doc", background=False, live_fetch=True)
    try:
        run_once(args)
    except RuntimeError as exc:
        assert "disabled" in str(exc)
    else:
        raise AssertionError("live fetch should be guarded")
