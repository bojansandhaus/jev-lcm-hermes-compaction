import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest
from jev_lcm_hermes_compaction.jev_client import post, ProviderError
from jev_lcm_hermes_compaction.providers import ProviderChain
from jev_lcm_hermes_compaction import cli


def _raising_settings(**kwargs):
    raise ValueError("invalid jev_provider_order")


def test_real_http_transport():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            body = json.loads(self.rfile.read(length))
            assert self.headers["Authorization"] == "Bearer synthetic"
            code = body.get("status", 200)
            self.send_response(code)
            self.end_headers()
            self.wfile.write(
                b"invalid" if body.get("bad") else b'{"answers":{"x":{"noul":0.19}}}'
            )

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = "http://127.0.0.1:%s/" % server.server_port
        assert post(url, "synthetic", {}, 1)["answers"]["x"]["noul"] == 0.19
        for code in (401, 403, 429, 500, 404):
            with pytest.raises(ProviderError):
                post(url, "synthetic", {"status": code}, 1)
        with pytest.raises(ProviderError, match="malformed"):
            post(url, "synthetic", {"bad": True}, 1)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    with pytest.raises(ProviderError, match="transport_error"):
        post(url, "synthetic", {}, 1)


def test_cli(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["jev-lcm", "jev_providers"])
    cli.main()
    assert json.loads(capsys.readouterr().out)["keys_present"] == []
    monkeypatch.setattr(
        "sys.argv", ["jev-lcm", "jev_calibrate", chr(45) * 2 + "dry-run"]
    )
    cli.main()
    assert json.loads(capsys.readouterr().out)["status"] == "disabled"
    monkeypatch.setattr("sys.argv", ["jev-lcm", "jev_calibrate"])
    with pytest.raises(SystemExit):
        cli.main()


def _patch_chain(monkeypatch, transport):
    """Inject a transport into the chain the CLI builds for itself.

    `ProviderChain.__init__` binds `post` as a default argument, so the module
    attribute is already captured by the time a test can patch it. Rebinding the
    default keeps the real construction path, including its `ValueError`
    handling.
    """
    original = ProviderChain.__init__

    def patched(self, settings, env=None, clock=time.monotonic):
        original(self, settings, env, transport)

    monkeypatch.setattr(ProviderChain, "__init__", patched)


def test_calibrate_dry_run_sends_nothing(monkeypatch, capsys):
    """`--dry-run` resolves the chain; it must not bill a request.

    The flag used to be the gate that *permitted* a live scoring call, so a dry
    run cost an operator one billed request and delivered no calibration, since
    the synthetic state it carried was never a real session's scores. The
    sending path is now `--live` and is named as such in the help text.
    """
    calls = []

    def transport(url, key, payload, timeout):
        calls.append(url)
        raise AssertionError("dry-run must not send a request")

    _patch_chain(monkeypatch, transport)
    monkeypatch.setattr("sys.argv", ["jev-lcm", "jev_calibrate", "--dry-run"])
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic")
    cli.main()
    report = json.loads(capsys.readouterr().out)
    assert calls == []
    assert "scores" not in report
    assert "latency_ms" not in report
    assert report["sent"] is False
    assert report["status"] == "resolved"
    assert report["order"] == ["openrouter"]


def test_calibrate_live_sends_exactly_one_request(monkeypatch, capsys):
    calls = []

    def transport(url, key, payload, timeout):
        calls.append(url)
        return {"answers": {q: {"noul": 0.5} for q in payload["questions"]}}

    _patch_chain(monkeypatch, transport)
    monkeypatch.setattr("sys.argv", ["jev-lcm", "jev_calibrate", "--dry-run", "--live"])
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic")
    cli.main()
    report = json.loads(capsys.readouterr().out)
    assert len(calls) == 1
    assert report["status"] == "ok"
    assert report["scores"] == {"probe": 0.5}
    assert isinstance(report["latency_ms"], float)


def test_a_load_failure_is_data_not_a_traceback(monkeypatch, capsys):
    """A mode that promises a fallback with no key reports it as JSON.

    `ProviderChain` and `Settings` both raise `ValueError` at load with the
    operator-facing message. Building the chain outside a guarded path turned
    that message into a traceback, which is the one shape that cannot be acted
    on, and it happened before the dry-run decision was ever reached.
    """
    monkeypatch.setattr("sys.argv", ["jev-lcm", "jev_providers"])
    for var in (
        "TYPESAFE_API_KEY",
        "OPENROUTER_API_KEY",
        "LAYA_API_KEY",
        "CLOUDFLARE_API_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(cli, "Settings", _raising_settings)
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert exit_info.value.code == 2
    report = json.loads(capsys.readouterr().out)
    assert report["error"] == "invalid jev_provider_order"
    assert report["command"] == "jev_providers"
