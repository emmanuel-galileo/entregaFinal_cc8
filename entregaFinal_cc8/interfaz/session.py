from __future__ import annotations

from collections import deque
from datetime import datetime
import re
from PySide6.QtCore import QObject, QTimer, Signal, QIODevice
from PySide6.QtSerialPort import QSerialPort, QSerialPortInfo
from .protocol import BoardState, LogEntry


class BoardPort(QObject):
    line = Signal(str)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.port = QSerialPort(self)
        self.port.readyRead.connect(self.read)
        self.port.errorOccurred.connect(self.error)
        self.buffer = bytearray()
        self.encoding = 'utf-8'

    def open(self, name):
        self.buffer.clear()
        self.port.setPortName(name)
        self.port.setBaudRate(115200)
        self.port.setDataBits(QSerialPort.DataBits.Data8)
        self.port.setParity(QSerialPort.Parity.NoParity)
        self.port.setStopBits(QSerialPort.StopBits.OneStop)
        self.port.setFlowControl(QSerialPort.FlowControl.NoFlowControl)
        if not self.port.open(QIODevice.OpenModeFlag.ReadWrite):
            raise OSError(self.port.errorString())
        self.port.setDataTerminalReady(False)
        self.port.setRequestToSend(False)

    def read(self):
        self.buffer.extend(bytes(self.port.readAll()))
        if len(self.buffer) > 16384:
            self.buffer.clear()
            self.failed.emit('Se descartó una línea serie sin terminación; revisar el registro.')
            return
        while b'\n' in self.buffer:
            raw, _, rest = self.buffer.partition(b'\n')
            self.buffer = bytearray(rest)
            self.line.emit(raw.rstrip(b'\r').decode(self.encoding, errors='replace'))

    def write(self, text, command=True):
        if not self.port.isOpen():
            raise OSError('El puerto está cerrado')
        raw = (('\r' + text + '\r') if command else text).encode(self.encoding, errors='strict')
        if self.port.write(raw) != len(raw):
            raise OSError(self.port.errorString())

    def error(self, code):
        if code in (QSerialPort.SerialPortError.ResourceError, QSerialPort.SerialPortError.DeviceNotFoundError):
            self.failed.emit(self.port.errorString())

    def close(self):
        if self.port.isOpen():
            self.port.write(b'\r/stop\r/fault 0\r/events 0\r')
            self.port.waitForBytesWritten(150)
            self.port.close()


class Session(QObject):
    updated = Signal(str)
    entry = Signal(object)
    event = Signal(str, object)
    connected = Signal(str, bool)

    def __init__(self):
        super().__init__()
        self.states = {n: BoardState(n) for n in ('A', 'B')}
        self.ports: dict[str, BoardPort] = {}
        self.entries = deque(maxlen=20000)
        self.raw = deque(maxlen=100000)
        self.results = []
        self.sent = {'A': deque(), 'B': deque()}
        self.selecting = set()
        self.encoding = 'utf-8'
        self.records_truncated = False
        self.poll = QTimer(self)
        self.poll.setInterval(1500)
        self.poll.timeout.connect(self.status)
        self.poll.start()

    @staticmethod
    def available_ports():
        return sorted([(p.portName(), p.description()) for p in QSerialPortInfo.availablePorts()], key=lambda p: (int(re.sub(r'\D', '', p[0]) or 0), p[0]))

    @property
    def nodes(self):
        return [n for n in ('A', 'B') if self.states[n].connected]

    @property
    def ready_nodes(self):
        return [n for n in self.nodes if self.states[n].ready]

    @property
    def unconfirmed(self):
        return any(not m['confirmed'] and not m.get('rejected') for node in self.nodes for m in self.sent[node])

    def log(self, node, category, text, severity='info', origin='observado', raw=''):
        value = LogEntry(node, category, text, severity, origin, raw)
        if len(self.entries) == self.entries.maxlen:
            self.records_truncated = True
        self.entries.append(value)
        self.entry.emit(value)

    def connect_board(self, node, port_name):
        if any(p.port.portName() == port_name for p in self.ports.values()):
            raise ValueError('Ese puerto ya está asignado a otra K8 en esta ventana.')
        if self.states[node].connected:
            self.disconnect_board(node)
        self.states[node] = BoardState(node)
        board = BoardPort(self)
        board.encoding = self.encoding
        board.line.connect(lambda line, n=node: self.receive(n, line))
        board.failed.connect(lambda message, n=node: self.log(n, 'Conexión', message, 'error'))
        board.open(port_name)
        self.ports[node] = board
        self.states[node].connected = True
        self.log(node, 'Conexión', f'Puerto {port_name} abierto a 115200 baudios.')
        self.connected.emit(node, True)
        self.send(node, '?')
        QTimer.singleShot(350, lambda n=node: self.setup(n))
        QTimer.singleShot(5000, lambda n=node: self.log(n, 'Conexión', 'Puerto abierto sin respuesta de la K8. Comprueba el COM y pulsa RESET si Keil dejó el programa detenido.', 'warning') if self.states[n].connected and not self.states[n].build else None)

    def setup(self, node):
        if node not in self.ports:
            return
        if self.states[node].build >= 1105:
            self.send(node, '/events 1')
        self.send(node, '/phylog 1')
        self.send(node, '/status')

    def disconnect_board(self, node):
        for item in self.sent[node]:
            if not item['confirmed'] and not item.get('rejected'):
                item['rejected'] = True
                item['error'] = 'Conexión cerrada; entrega sin verificar'
                self.event.emit(node, {'kind': 'chat_changed', 'item': item})
        if node in self.ports:
            self.ports.pop(node).close()
        self.states[node].connected = self.states[node].ready = False
        self.selecting.discard(node)
        self.connected.emit(node, False)
        self.updated.emit(node)

    def send(self, node, command, origin='control'):
        if node not in self.ports:
            raise ValueError(f'K8 {node} no conectada')
        self.ports[node].write(command)
        self.raw.append({'time': datetime.now().astimezone().isoformat(), 'node': node, 'direction': 'TX', 'text': command, 'origin': origin})
        if command.startswith(('/fault ', '/erase ', '/flip ', '/notch ', '/badcrc', '/dropack')):
            self.log(node, 'Inyección', command, 'warning', 'software')

    def send_all(self, command):
        for node in self.ready_nodes:
            self.send(node, command)

    def status(self):
        for node in tuple(self.nodes):
            try:
                if self.ports[node].port.bytesToWrite() < 128:
                    self.send(node, '/status')
            except (ValueError, OSError) as exc:
                self.log(node, 'Conexión', str(exc), 'error')

    def set_encoding(self, name):
        if name not in ('utf-8', 'cp1252'):
            raise ValueError(name)
        if name == self.encoding:
            return
        if any(self.states[n].app.get('QUEUED') or self.states[n].app.get('PENDING') for n in self.nodes):
            raise ValueError('Esperar a que terminen los mensajes antes de cambiar codificación.')
        self.encoding = name
        for port in self.ports.values():
            if port.buffer:
                raise ValueError('Hay una línea serie en curso; repetir el cambio de codificación.')
        for port in self.ports.values():
            port.encoding = name
        self.log('—', 'Configuración', f'Codificación local: {name}. La otra PC debe usar la misma.')

    def queue_message(self, node, text):
        if not self.states[node].ready:
            raise ValueError(f'K8 {node} todavía no está identificada correctamente.')
        data = text.encode(self.encoding, errors='strict')
        if len(data) > 185:
            raise ValueError(f'El mensaje ocupa {len(data)} bytes; el límite es 185.')
        if any(c in text for c in ('\r', '\n', '\x00')):
            raise ValueError('Usar una sola línea por mensaje, sin caracteres NUL.')
        item = {'text': text, 'goal': None, 'confirmed': False, 'received': False}
        self.sent[node].append(item)
        try:
            self.send(node, '/send ' + text, 'chat')
        except Exception:
            self.sent[node].remove(item)
            raise
        self.event.emit(node, {'kind': 'chat_sent', 'item': item})
        return item

    def receive(self, node, line, origin='observado', recorded_time=None):
        moment = datetime.now().astimezone().isoformat()
        if recorded_time:
            try:
                moment = datetime.fromisoformat(recorded_time.replace('Z', '+00:00')).astimezone().isoformat(timespec='milliseconds')
            except ValueError:
                pass
        if len(self.raw) == self.raw.maxlen:
            self.records_truncated = True
        self.raw.append({'time': moment, 'node': node, 'direction': 'RX', 'text': line, 'origin': origin})
        state = self.states[node]
        if 'Emisores apagados.' in line and state.build:
            for item in self.sent[node]:
                if not item['confirmed']:
                    item['error'] = 'La K8 se reinició; envío sin confirmar'
                    item['rejected'] = True
                    self.event.emit(node, {'kind': 'chat_changed', 'item': item})
            self.states[node] = state = BoardState(node, connected=state.connected)
            self.selecting.discard(node)
            self.log(node, 'Conexión', 'La K8 se reinició. Reinicia ambas placas antes de reanudar el protocolo.', 'warning')
            self.event.emit(node, {'kind': 'reboot'})
        if 'elige 1=a' in line.lower() and node not in self.selecting and node in self.ports:
            self.selecting.add(node)
            self.ports[node].write('1' if node == 'A' else '2', command=False)
            QTimer.singleShot(120, lambda n=node: self.setup(n))
        event, entries = state.consume(line)
        event['source'] = origin
        event['time'] = moment
        if state.ready:
            self.selecting.discard(node)
        for value in entries:
            if origin != 'observado':
                value.origin = origin
                value.time = moment
            if len(self.entries) == self.entries.maxlen:
                self.records_truncated = True
            self.entries.append(value)
            self.entry.emit(value)
        if event['kind'] == 'device' and not state.ready:
            self.log(node, 'Identificación', f"La placa indica identidad {state.hardware.get('NODE')}; se esperaba {'0 (A)' if node == 'A' else '1 (B)'}. Seleccionar la identidad correcta o reiniciar ambas K8.", 'error')
        if event['kind'] == 'device' and state.build and state.build < 1105:
            if not getattr(state, '_old_warning', False):
                state._old_warning = True
                self.log(node, 'Firmware', f'BUILD{state.build}: chat disponible; cargar BUILD1105 para eventos y pruebas completas.', 'warning')
        if event['kind'] == 'queued':
            pending = next((m for m in self.sent[node] if m['goal'] is None and not m.get('rejected')), None)
            if pending is not None:
                pending['goal'] = event.get('goal_tx')
                pending['wire_bytes'] = event.get('bytes')
                self.event.emit(node, {'kind': 'chat_changed', 'item': pending})
        if event['kind'] == 'rejected' and event['line'].startswith(('QUEUE_FULL', 'MESSAGE_TOO_LONG', 'INPUT_TOO_LONG')):
            pending = next((m for m in self.sent[node] if m['goal'] is None and not m.get('rejected')), None)
            if pending:
                pending['rejected'] = True
                pending['error'] = event['line']
                self.event.emit(node, {'kind': 'chat_changed', 'item': pending})
        tx = state.app.get('TX', 0)
        for item in self.sent[node]:
            if item['goal'] is not None and tx >= item['goal'] and not item['confirmed'] and not item.get('rejected'):
                item['confirmed'] = True
                self.event.emit(node, {'kind': 'chat_changed', 'item': item})
        if event['kind'] == 'chat':
            other = 'B' if node == 'A' else 'A'
            pending = next((m for m in self.sent[other] if not m['received'] and not m.get('rejected')), None)
            if pending is not None and pending['text'] == event['text']:
                pending['received'] = True
                pending['confirmed'] = True
                event['paired'] = True
                self.event.emit(other, {'kind': 'chat_changed', 'item': pending})
        self.event.emit(node, event)
        self.updated.emit(node)

    def close(self):
        self.poll.stop()
        for node in tuple(self.nodes):
            self.disconnect_board(node)
