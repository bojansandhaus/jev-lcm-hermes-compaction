import json
import threading
from http.server import BaseHTTPRequestHandler,HTTPServer
import pytest
from jev_lcm_hermes_compaction.jev_client import post,ProviderError
from jev_lcm_hermes_compaction import cli


def test_real_http_transport():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length=int(self.headers['Content-Length']);body=json.loads(self.rfile.read(length))
            assert self.headers['Authorization']=='Bearer synthetic'
            code=body.get('status',200)
            self.send_response(code);self.end_headers()
            self.wfile.write(b'invalid' if body.get('bad') else b'{"answers":{"x":{"noul":0.19}}}')
        def log_message(self,*args): pass
    server=HTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        url='http://127.0.0.1:%s/'%server.server_port
        assert post(url,'synthetic',{},1)['answers']['x']['noul']==.19
        for code in (401,403,429,500,404):
            with pytest.raises(ProviderError):post(url,'synthetic',{'status':code},1)
        with pytest.raises(ProviderError,match='malformed'):post(url,'synthetic',{'bad':True},1)
    finally:server.shutdown();server.server_close();thread.join()
    with pytest.raises(ProviderError,match='transport_error'):post(url,'synthetic',{},1)


def test_cli(monkeypatch,capsys):
    monkeypatch.setattr('sys.argv',['jev-lcm','jev_providers']);cli.main()
    assert json.loads(capsys.readouterr().out)['keys_present']==[]
    monkeypatch.setattr('sys.argv',['jev-lcm','jev_calibrate',chr(45)*2+'dry-run']);cli.main()
    assert json.loads(capsys.readouterr().out)['status']=='disabled'
    monkeypatch.setattr('sys.argv',['jev-lcm','jev_calibrate'])
    with pytest.raises(SystemExit):cli.main()
