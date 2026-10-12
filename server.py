# -*- coding: utf-8 -*-
"""ISM 初中組陀螺大賽 — 場地計分主機（即時同步）

用法：雙擊「啟動主機.bat」，或執行  python server.py
再用瀏覽器打開視窗中顯示的網址即可。
"""
import json
import os
import socket
import sys
import threading
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

try:
    import qrcode
except ImportError:
    qrcode = None

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE, 'state.json')

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

lock = threading.Lock()
rev = 0
state = None


def load():
    global rev, state
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                obj = json.load(f)
            rev = int(obj.get('rev', 0))
            state = obj.get('state')
        except Exception:
            rev, state = 0, None


def persist():
    tmp = STATE_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'rev': rev, 'state': state}, f, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=BASE, **kw)

    def log_message(self, fmt, *args):
        pass

    def _send_json(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/state':
            with lock:
                self._send_json(200, {'rev': rev, 'state': state})
            return
        if path in ('/', '/index.html'):
            try:
                with open(os.path.join(BASE, 'index.html'), 'rb') as f:
                    data = f.read()
            except OSError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def do_POST(self):
        global rev, state
        if urlparse(self.path).path != '/api/state':
            self.send_error(404)
            return
        try:
            ln = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(ln).decode('utf-8'))
        except Exception:
            self._send_json(400, {'error': 'bad request'})
            return
        with lock:
            if body.get('baseRev') != rev:
                self._send_json(409, {'rev': rev, 'state': state})
                return
            new_state = body.get('state')
            same = (json.dumps(new_state, ensure_ascii=False, sort_keys=True)
                    == json.dumps(state, ensure_ascii=False, sort_keys=True))
            if same:
                self._send_json(200, {'rev': rev, 'unchanged': True})
                return
            state = new_state
            rev += 1
            persist()
            self._send_json(200, {'rev': rev})


def lan_ips():
    primary = None
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        primary = s.getsockname()[0]
        s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith('127.') and not ip.startswith('169.254.'):
                ips.add(ip)
    except Exception:
        pass
    if primary:
        ips.discard(primary)

    def score(ip):
        if ip.startswith('192.168.'):
            return 0
        if ip.startswith('10.'):
            return 1
        return 2  # 172.x 常見於虛擬網卡，排最後

    rest = sorted(ips, key=score)
    return ([primary] if primary else []) + rest


def main():
    load()
    httpd = None
    port = 8000
    for p in range(8000, 8011):
        try:
            httpd = ThreadingHTTPServer(('0.0.0.0', p), Handler)
            port = p
            break
        except OSError:
            continue
    if httpd is None:
        print('找不到可用的連接埠（8000-8010 都被佔用了）')
        input('按 Enter 結束...')
        return

    print('=' * 56)
    print('  ISM 初中組陀螺大賽 — 計分主機已啟動')
    print('=' * 56)
    print()
    print('  這台電腦開啟：  http://localhost:%d' % port)
    print()
    print('  其他人（手機 / 平板 / 電腦）連上同一個 Wi-Fi，')
    print('  用瀏覽器打開下面任一網址：')
    ips = lan_ips()
    for ip in ips:
        print('      http://%s:%d' % (ip, port))
    print()
    print('  ✔ 所有裝置的比分會即時同步')
    print('  ✔ 關掉視窗後再開，資料還在（state.json）')
    print()
    if qrcode is not None and ips:
        try:
            print('  手機相機掃描下面的 QR Code 就能直接打開：')
            print()
            qr = qrcode.QRCode(border=1)
            qr.add_data('http://%s:%d' % (ips[0], port))
            qr.make(fit=True)
            qr.print_ascii(invert=True)
            print()
        except Exception:
            pass
    print('  （要結束請按 Ctrl+C，或直接關掉這個視窗）')
    print('=' * 56)
    if os.environ.get('NO_BROWSER') != '1':
        try:
            webbrowser.open('http://localhost:%d' % port)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        print('已停止。')


if __name__ == '__main__':
    main()
