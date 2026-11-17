"""Chat HTTP local. Los mensajes se entregan a la misma sesión serie de la app."""
from __future__ import annotations

from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import RLock, Thread
from uuid import uuid4
import json

from PySide6.QtCore import QObject, QTimer, Signal
from .chat_model import ChatHistory, TEXT_SAMPLES, PALETTES, representable


class WebChat(QObject):
    requested = Signal(str, str, str, str)

    def __init__(self, session, busy, cancel):
        super().__init__()
        self.session, self.busy, self.cancel = session, busy, cancel
        self.lock = RLock()
        self.results = {}
        self.history = []
        self.conversations = ChatHistory()
        self.snapshot = b'{}'
        self.requested.connect(self.perform)
        session.event.connect(self.observe)
        hub = self
        page = (Path(__file__).parent / 'web' / 'index.html').read_bytes()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, data, content='application/json; charset=utf-8'):
                body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', content)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def local(self):
                return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

            def do_GET(self):
                if not self.local():
                    self.reply(403, {'error': 'Host no permitido'})
                elif self.path == '/':
                    self.reply(200, page, 'text/html; charset=utf-8')
                elif self.path == '/api/state':
                    with hub.lock:
                        data = hub.snapshot
                    self.reply(200, data)
                elif self.path.startswith('/api/result/'):
                    with hub.lock:
                        data = dict(hub.results.get(self.path.rsplit('/', 1)[-1], {'state': 'unknown'}))
                    self.reply(200, data)
                else:
                    self.reply(404, {'error': 'No encontrado'})

            def do_POST(self):
                if not self.local() or self.headers.get('Origin', hub.url) not in (hub.url, hub.url.replace('127.0.0.1', 'localhost')):
                    self.reply(403, {'error': 'Origen no permitido'})
                    return
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    self.reply(415, {'error': 'Se requiere JSON'})
                    return
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 4096:
                        raise ValueError('Solicitud demasiado grande')
                    data = json.loads(self.rfile.read(length))
                    node = data.get('node')
                    if node not in ('A', 'B'):
                        raise ValueError('Selecciona A o B')
                    if self.path == '/api/send':
                        action, text = 'send', data.get('text')
                        if not isinstance(text, str):
                            raise ValueError('Mensaje no válido')
                    elif self.path == '/api/action':
                        action, text = data.get('action'), ''
                        if action not in ('start', 'stop', 'probe', 'status'):
                            raise ValueError('Acción no permitida')
                    else:
                        self.reply(404, {'error': 'No encontrado'})
                        return
                    key = uuid4().hex
                    with hub.lock:
                        if len(hub.results) >= 100:
                            hub.results.pop(next(iter(hub.results)))
                        hub.results[key] = {'state': 'pending'}
                    hub.requested.emit(key, node, action, text)
                    self.reply(202, {'id': key, 'state': 'pending'})
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    self.reply(400, {'error': str(exc)})

        self.server = None
        for port in (8765, 8766, 8767, 0):
            try:
                self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
                break
            except OSError:
                continue
        if self.server is None:
            raise OSError('No se pudo iniciar el servidor de chat local.')
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = Thread(target=self.server.serve_forever, kwargs={'poll_interval': .2}, daemon=True)
        self.thread.start()
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.publish)
        self.timer.start()
        self.publish()

    def perform(self, key, node, action, text):
        try:
            if node not in self.session.ready_nodes:
                raise ValueError('Conecta esa K8 desde la aplicación.')
            if self.busy() and action != 'stop':
                raise ValueError('Hay una prueba en ejecución; espera o cancélala desde la app.')
            if action == 'send':
                if self.session.states[node].app.get('RUN') != 1:
                    raise ValueError('Activa el chat en ambos extremos.')
                self.session.queue_message(node, text)
            else:
                if action == 'stop':
                    self.cancel()
                for target in (self.session.ready_nodes if action in ('start', 'stop') else [node]):
                    self.session.send(target, '/' + action)
            result = {'state': 'accepted', 'message': 'Solicitud aceptada por el programa; la entrega se confirma en el chat.'}
        except Exception as exc:
            result = {'state': 'error', 'message': str(exc)}
        with self.lock:
            self.results[key] = result
        self.publish()

    def observe(self, node, event):
        self.conversations.consume(node, event)
        if event['kind'] == 'chat_sent':
            self.history.append({'node': node, 'outgoing': True, 'item': event['item'], 'time': datetime.now().strftime('%H:%M:%S')})
        elif event['kind'] == 'chat' and not event.get('paired'):
            self.history.append({'node': 'B' if node == 'A' else 'A', 'outgoing': False, 'item': {'text': event['text'], 'received': True}, 'time': event.get('time', datetime.now().isoformat())[11:19]})
        if len(self.history) > 500:
            self.history.pop(0)

    def publish(self):
        data = {'url': self.url, 'busy': self.busy(), 'encoding': self.session.encoding,
                'conversations': self.conversations.snapshot(),
                'text_samples': [{'key': key, 'label': label, 'text': text, 'allowed': representable(text, self.session.encoding)} for key, label, text in TEXT_SAMPLES],
                'palettes': PALETTES,
                'allowed_symbols': {c: representable(c, self.session.encoding) for chars in PALETTES.values() for c in chars},
                'nodes': {n: {'connected': s.connected, 'ready': s.ready, 'version': s.version,
                    'build': s.build, 'app': dict(s.app), 'timing': dict(s.timing), 'mac': dict(s.mac)}
                    for n, s in self.session.states.items()},
                'history': [{'node': h['node'], 'outgoing': h['outgoing'], 'time': h['time'],
                    'text': h['item']['text'], 'received': h['item'].get('received', False),
                    'confirmed': h['item'].get('confirmed', False), 'error': h['item'].get('error', '')}
                    for h in self.history],
                'logs': [{'time': e.time[11:23], 'node': e.node, 'category': e.category,
                    'text': e.text, 'severity': e.severity} for e in list(self.session.entries)[-50:]]}
        raw = json.dumps(data, ensure_ascii=False).encode('utf-8')
        with self.lock:
            self.snapshot = raw

    def close(self):
        self.timer.stop()
        self.server.shutdown()
        self.server.server_close()
