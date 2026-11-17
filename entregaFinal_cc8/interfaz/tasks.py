"""Pruebas por eventos: los puertos pertenecen siempre a la sesión de la app."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import time
from PySide6.QtCore import QObject, QTimer, Signal
from .protocol import PROFILES, crc8, matrix_word


@dataclass
class Wait:
    predicate: object
    timeout: float
    description: str


@dataclass
class Pause:
    seconds: float


@dataclass
class Prompt:
    text: str


@dataclass
class Check:
    passed: bool
    text: str


# Duraciones aproximadas; las reparaciones pueden prolongarlas.
CATALOG = (
    ('presentacion', 'Presentación', 'Chat bidireccional y cuatro tipos de trama a 1 Hz', '2 min'),
    ('probe', 'Enlace', 'Sondas en ambos sentidos', '35 s'),
    ('clock', 'Diagnóstico', 'Relojes cruzados: cinco niveles por sentido', '12 s'),
    ('ir', 'Diagnóstico', 'IR: encendido y apagado en ambos sentidos', '35 s'),
    ('sound', 'Diagnóstico', 'Sonido: silencio, A→B, B→A y ambos', '12 s'),
    ('chat', 'Chat', 'Mensajes pendientes en ambos sentidos', '2 min'),
    ('noack', 'Enlace', 'Sin aceptación y arranque tardío', '2 min'),
    ('local23', 'Recuperación', 'Un escalón perdido: reconstrucción 2 de 3', '1 min'),
    ('parity', 'Recuperación', 'Dos bits borrados: paridad matricial', '1 min'),
    ('flip', 'Recuperación', 'Bits alterados: reparación del bloque', '1 min'),
    ('badcrc', 'Recuperación', 'CRC inválido y reparación', '1 min'),
    ('lostack', 'Recuperación', 'ACK perdido sin duplicar el mensaje', '1 min'),
    ('crc0', 'CRC', 'CRC-8 SMBUS', '2 min'), ('crc1', 'CRC', 'CRC-8 AUTOSAR', '2 min'),
    ('crc2', 'CRC', 'CRC-8 SAE-J1850', '2 min'), ('crc3', 'CRC', 'CRC-8 MAXIM-DOW', '2 min'),
    ('empty', 'Texto', 'Mensaje vacío: trama ÚNICA', '30 s'),
    ('character', 'Texto', 'Un carácter: A', '1 min'),
    ('dollar', 'Texto', 'Símbolo dólar: $', '1 min'),
    ('emoji', 'Texto', 'Un emoji de 4 bytes: 😀', '3 min'),
    ('utf8', 'Texto', 'UTF-8: caracteres de 1, 2, 3 y 4 bytes', '6 min'),
    ('cp1252', 'Texto', 'Extended ASCII: CP1252', '1 min'),
    ('compression', 'Texto', 'Límite de 185 bytes con compresión', '12 min'),
    ('ir_a', 'Medios', 'IR A→B fuera de servicio y recuperación', '2 min'),
    ('ir_b', 'Medios', 'IR B→A fuera de servicio y recuperación', '2 min'),
    ('sound_a', 'Medios', 'Sonido A→B fuera de servicio; Turbo IR', '2 min'),
    ('sound_b', 'Medios', 'Sonido B→A fuera de servicio; Turbo IR', '2 min'),
    ('demo', 'Demostración', '1 Hz fijo, sonido suspendido y restaurado', '1 min'),
    ('physical_ir', 'Interferencia física', 'Switch IR: ensayo guiado', '4 min'),
    ('physical_sound', 'Interferencia física', 'Ruido del teléfono: ensayo guiado', '4 min'),
    ('physical_crc', 'Interferencia física', 'Evidencia física CRC → NACK → reparación', '4 min'),
    ('math', 'Modelo local', 'CRC y matriz exhaustivos en la PC', '7 s'),
)
TITLES = {key: title for key, _, title, _ in CATALOG}
BASIC = ('probe', 'clock', 'ir', 'sound', 'chat', 'local23', 'parity', 'badcrc', 'lostack', 'demo')
FULL = tuple(k for k, group, _, _ in CATALOG if group not in ('Interferencia física', 'Presentación'))
# Estas dos pruebas verifican expresamente el cambio de velocidad y el piloto de Turbo.
SPEED_TESTS = frozenset(('sound_a', 'sound_b'))


def test_rate(key):
    return None if key == 'math' else 'max' if key in SPEED_TESTS else 'log'


class TestRunner(QObject):
    changed = Signal()
    prompt = Signal(str)

    def __init__(self, session):
        super().__init__()
        self.session = session
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.tick)
        self.running = False
        self.current = ''
        self.progress = ''
        self.started = 0.0
        self.results = {}
        self.queue = []
        self.generator = None
        self.step = None
        self.step_started = 0.0
        self.prompt_done = False
        self.cancelled = False
        self.hardware_controlled = False
        session.event.connect(lambda _, event: self.cancel() if self.running and event['kind'] == 'reboot' else None)

    def start(self, keys):
        if self.running:
            raise ValueError('Ya hay una prueba en ejecución.')
        if not keys:
            return
        if any(k != 'math' for k in keys):
            if set(self.session.ready_nodes) != {'A', 'B'}:
                raise ValueError('La tanda automática necesita observar A y B en esta PC. Con una K8 local usa el chat, controles y observa el protocolo; coordina las acciones con la otra PC.')
            if any(self.session.states[n].build < 1105 for n in ('A', 'B')):
                raise ValueError('Cargar BUILD1105 en ambas K8 para ejecutar la tanda con todos los eventos.')
            if self.session.unconfirmed or not all(self.session.states[n].idle for n in ('A', 'B')):
                raise ValueError('Esperar a que terminen los mensajes y se libere el turno.')
        self.running, self.cancelled = True, False
        self.hardware_controlled = any(k != 'math' for k in keys)
        self.queue = list(keys)
        self.previous_encoding = self.session.encoding
        self.saved = {n: (s.timing.get('PROFILE', 0), s.app.get('CRC', 0), s.app.get('COMPRESS', 1), s.app.get('RUN', 0)) for n, s in self.session.states.items() if s.ready}
        self.next_test()
        self.timer.start()

    def next_test(self):
        if not self.queue:
            self.finish()
            return
        self.current = self.queue.pop(0)
        self.started = time.monotonic()
        self.step = None
        self.generator = self.routine(self.current)
        self.results[self.current] = {'status': 'running', 'checks': [], 'origin': 'modelo local' if self.current == 'math' else 'física declarada por operador' if self.current.startswith('physical') else 'hardware con inyección por software' if self.current in ('badcrc', 'lostack', 'local23', 'parity', 'flip', 'ir_a', 'ir_b', 'sound_a', 'sound_b', 'demo') else 'hardware'}
        self.results[self.current]['rate'] = test_rate(self.current)
        self.session.log('A/B', 'Prueba', 'Inicio: ' + TITLES[self.current], origin=self.results[self.current]['origin'])
        self.changed.emit()

    def tick(self):
        try:
            if self.step is not None:
                elapsed = time.monotonic() - self.step_started
                if isinstance(self.step, Pause) and elapsed < self.step.seconds:
                    return
                if isinstance(self.step, Prompt) and not self.prompt_done:
                    return
                if isinstance(self.step, Wait):
                    if not self.step.predicate():
                        self.progress = self.step.description
                        self.changed.emit()
                        if elapsed >= self.step.timeout:
                            raise AssertionError('Tiempo agotado: ' + self.step.description)
                        return
                self.step = None
            for _ in range(8):
                step = next(self.generator)
                if isinstance(step, Check):
                    self.results[self.current]['checks'].append({'passed': bool(step.passed), 'text': step.text})
                    self.session.log('A/B', 'Prueba', step.text, 'success' if step.passed else 'error', self.results[self.current]['origin'])
                    if not step.passed:
                        raise AssertionError(step.text)
                    continue
                self.step, self.step_started = step, time.monotonic()
                if isinstance(step, Wait):
                    self.progress = step.description
                elif isinstance(step, Prompt):
                    self.progress = step.text
                    self.prompt_done = False
                    self.prompt.emit(step.text)
                self.changed.emit()
                return
        except StopIteration:
            self.complete(True)
            self.next_test()
        except Exception as exc:
            self.complete(False, str(exc))
            self.queue.clear()
            self.finish()

    def complete(self, passed, reason=''):
        if not self.current:
            return
        result = self.results[self.current]
        result.update(status='passed' if passed else 'cancelled' if self.cancelled else 'failed',
                      elapsed=round(time.monotonic() - self.started, 2), reason=reason,
                      test=self.current, title=TITLES[self.current], at=datetime.now().astimezone().isoformat())
        self.session.results.append(dict(result))
        self.session.log('A/B', 'Resultado', f"{TITLES[self.current]}: {'PASA' if passed else 'CANCELADA' if self.cancelled else 'INCOMPLETA'} {reason}", 'success' if passed else 'warning' if self.cancelled else 'error', result['origin'])
        self.changed.emit()

    def acknowledge(self):
        self.prompt_done = True
        self.prompt.emit('')
        self.session.log('A/B', 'Operador', self.progress, origin='declaración del operador')

    def note_intervention(self, node, command):
        if not self.running or self.current not in self.results:
            return
        result = self.results[self.current]
        actions = result.setdefault('manual_interventions', [])
        actions.append({'node': node, 'command': command, 'time': datetime.now().astimezone().isoformat()})
        if len(actions) == 1:
            result['origin'] += ' + intervención manual por software'
        self.session.log(node, 'Operador', 'Intervención manual durante la prueba: ' + command + '. El resultado conserva esta condición.', origin='software')
        self.changed.emit()

    def cancel(self):
        if self.running:
            self.cancelled = True
            self.complete(False, 'Interrumpida por el usuario.')
            self.queue.clear()
            self.finish()

    def finish(self):
        self.timer.stop()
        self.running = False
        self.step = self.generator = None
        self.prompt.emit('')
        for n in self.session.ready_nodes if self.hardware_controlled else ():
            try:
                for command in ('/fault 0', '/erase 0', '/flip 0', '/notch 0 0', '/stop'):
                    self.session.send(n, command)
            except (ValueError, OSError):
                pass
        # Un fallo conserva las colas del firmware: no se descartan mensajes para poder recuperarlos.
        self.progress = 'Pruebas terminadas. Emisores detenidos; los datos pendientes se conservan. Usa Activar chat para continuar.' if self.hardware_controlled else 'Modelo local terminado. Las K8 conservan su estado.'
        try:
            self.session.set_encoding(self.previous_encoding)
        except ValueError:
            pass
        self.changed.emit()

    def config(self, rate='log', crc=0, compress=True):
        for n in ('A', 'B'):
            self.session.send(n, '/stop')
        yield Pause(.3)
        for n in ('A', 'B'):
            for cmd in ('/fault 0', '/erase 0', '/flip 0', '/notch 0 0', '/rate ' + rate,
                        '/crc ' + str(crc), '/compress ' + str(int(compress)), '/events 1', '/phylog 1', '/status'):
                self.session.send(n, cmd)
        yield Wait(lambda: all(self.session.states[n].app.get('CRC') == crc and
                              self.session.states[n].app.get('COMPRESS') == int(compress) and
                              self.session.states[n].timing.get('PROFILE') == PROFILES[rate] and
                              self.session.states[n].app.get('RUN') == 0 for n in ('A', 'B')),
                   8, 'Esperando que ambas placas confirmen la configuración')
        if self.session.encoding != 'utf-8':
            yield Wait(lambda: all(not p.buffer for p in self.session.ports.values()), 5, 'Esperando cierre de las líneas serie antes de cambiar codificación')
            self.session.set_encoding('utf-8')
        for n in ('B', 'A'):
            self.session.send(n, '/start')
        yield Pause(.3)

    def idle(self, seconds=60):
        yield Wait(lambda: all(self.session.states[n].idle for n in ('A', 'B')), seconds, 'Esperando entrega y liberación del turno')

    def integrity(self):
        self.session.status()
        yield Pause(.4)
        for n in ('A', 'B'):
            s = self.session.states[n]
            good = all(s.hardware.get(k, 0) == 0 for k in ('UART_ERR', 'UART_DROP', 'CAP_OVR', 'CLOCK_BAD', 'EVENT_DROP')) and s.app.get('APP_ERR', 0) == 0 and s.app.get('RX_DROP', 0) == 0 and s.timing.get('DEADLINE_MISS', 0) == 0
            yield Check(good, f'{n}: sin errores de UART, aplicación, captura, reloj o pérdida de eventos.')

    def message(self, messages, timeout=260):
        counts = {src: len(self.session.states['B' if src == 'A' else 'A'].messages) for src in messages}
        for src, text in messages.items():
            self.session.queue_message(src, text)
        yield Wait(lambda: all(len(self.session.states['B' if src == 'A' else 'A'].messages) > count for src, count in counts.items()), timeout,
                   'Esperando el mensaje completo, validado y reconstruido en el destino')
        yield from self.idle(45)
        for src, count in counts.items():
            dest = 'B' if src == 'A' else 'A'
            got = list(self.session.states[dest].messages)[count:]
            yield Check(got == [messages[src]], f'{src}→{dest}: contenido exacto y una sola entrega.')
        yield from self.integrity()

    def routine(self, key):
        s = self.session.states
        if key == 'math':
            self.session.log('PC', 'Prueba', 'Modelo local: resultados espaciados para lectura; no utiliza reloj ni sensores de las K8.')
            for kind in range(4):
                known = (0xF4, 0xDF, 0x4B, 0xA1)[kind]
                yield Pause(1)
                yield Check(crc8(kind, b'123456789') == known, f'CRC {kind}: vector de referencia correcto.')
            cases = 0
            for data in range(64):
                word = matrix_word(data)
                for lost in range(4):
                    values, known = word, 255 ^ (3 << (2 * lost))
                    for group in ((0, 3, 4, 6), (1, 2, 5, 7)):
                        holes = [p for p in group if not known & (1 << p)]
                        assert len(holes) == 1
                        value = 0
                        for p in group:
                            if p not in holes:
                                value ^= (values >> p) & 1
                        values = (values & ~(1 << holes[0])) | (value << holes[0])
                    assert values == word
                    cases += 1
            yield Pause(1)
            yield Check(cases == 256, 'Modelo en PC: las 256 combinaciones de datos y ronda borrada se reconstruyen. No es una medición de sensores.')
            protected = 0
            for kind in range(4):
                for control in range(16):
                    original = crc8(kind, bytes((control, 0xA5)))
                    for bit in (2, 3):
                        assert crc8(kind, bytes((control ^ (1 << bit), 0xA5))) != original
                        protected += 1
            yield Pause(1)
            yield Check(protected == 128, 'Modelo en PC: el CRC detecta las 128 alteraciones de bits de tipo de trama.')
            return
        rate = test_rate(key)
        self.session.log('A/B', 'Velocidad', 'Prueba de aceleración: comienza en modo rápido y verifica Turbo Solo-IR y su piloto.' if rate == 'max' else 'Modo legible: datos a 1 Hz (1000 ms por ronda), sin Turbo. SYN y SFD conservan su velocidad rápida.')
        yield from self.config(rate, int(key[-1]) if key.startswith('crc') else 0, key not in ('utf8', 'cp1252', 'presentacion') and not key.startswith('crc'))
        if key == 'probe':
            for src in ('A', 'B'):
                old = s[src].mac.get('FRAMES', 0)
                self.session.send(src, '/probe')
                yield Wait(lambda src=src, old=old: s[src].mac.get('FRAMES', 0) > old and s[src].idle, 40, 'Ocho rondas de sonda ' + src)
                yield Check(s[src].active == 3, src + ': ambos medios validan las sondas.')
        elif key in ('clock', 'ir', 'sound'):
            for n in ('A', 'B'):
                self.session.send(n, '/stop')
            yield Pause(.3)
            if key in ('clock', 'ir'):
                for src in ('A', 'B'):
                    dest = 'B' if src == 'A' else 'A'
                    for level in (0, 1, 0, 1, 0):
                        self.session.send(src, f'/{key} {level}')
                        self.session.send(dest, '/status' if key == 'clock' else '/samples')
                        yield Pause(1)
                        if key == 'clock':
                            yield Check(s[dest].clock.get('CLOCK_RX_ACTIVE') == level, f'Reloj {src}→{dest}: nivel {level} observado.')
                        else:
                            # DO está disponible en el diagnóstico de nivel del firmware.
                            self.session.send(dest, '/mic')
                            self.session.log(src, 'Diagnóstico', f'IR: nivel ordenado {level}; la validación funcional se comprobará con los barridos de la sonda.')
                if key == 'ir':
                    for n in ('B', 'A'):
                        self.session.send(n, '/start')
                    self.session.send('A', '/probe')
                    yield Pause(.4)
                    yield from self.idle(40)
                    yield Check(s['A'].active & 1 != 0, 'IR A→B validado mediante barridos y retorno.')
                    self.session.send('B', '/probe')
                    yield Pause(.4)
                    yield from self.idle(40)
                    yield Check(s['B'].active & 1 != 0, 'IR B→A validado mediante barridos y retorno.')
            else:
                for dest in ('A', 'B'):
                    self.session.send(dest, '/mic')
                yield Pause(1)
                quiet = {n: s[n].mic or 0 for n in ('A', 'B')}
                for src in ('A', 'B'):
                    dest = 'B' if src == 'A' else 'A'
                    self.session.send(src, '/tone 1')
                    yield Pause(1)
                    self.session.send(dest, '/mic')
                    yield Pause(1)
                    yield Check((s[dest].mic or 0) > quiet[dest] + 10, f'Sonido {src}→{dest}: flancos por encima de la referencia en silencio.')
                    self.session.send(src, '/tone 0')
                    yield Pause(1)
                for n in ('A', 'B'):
                    self.session.send(n, '/tone 1')
                yield Pause(1)
                for n in ('A', 'B'):
                    self.session.send(n, '/mic')
                yield Pause(1)
                yield Check(all((s[n].mic or 0) > quiet[n] + 10 for n in ('A', 'B')), 'Ambos micrófonos detectan con los dos tonos presentes.')
                for n in ('A', 'B'):
                    self.session.send(n, '/tone 0')
                yield Pause(1)
        elif key == 'noack':
            self.session.send('B', '/stop')
            before = s['A'].app.get('TX', 0)
            self.session.queue_message('A', 'K')
            yield Pause(4.5)
            yield Check(s['A'].app.get('TX', 0) == before and s['A'].app.get('QUEUED', 0) > 0, 'Sin aceptación no se enviaron bytes de datos.')
            old = len(s['B'].messages)
            self.session.send('B', '/start')
            yield Wait(lambda: len(s['B'].messages) > old, 140, 'La segunda placa arranca tarde y recibe el mensaje pendiente')
            yield from self.idle()
            yield Check(s['B'].messages[-1] == 'K', 'Arranque tardío: mensaje recuperado.')
        elif key == 'presentacion':
            yield from self.message({'A': 'OK', 'B': ''}, 240)
        elif key in ('chat', 'crc0', 'crc1', 'crc2', 'crc3', 'empty', 'character', 'dollar', 'emoji', 'utf8', 'cp1252', 'compression'):
            if key == 'cp1252':
                yield Wait(lambda: all(not p.buffer for p in self.session.ports.values()), 5, 'Esperando líneas serie completas para CP1252')
                self.session.set_encoding('cp1252')
            messages = {'A': 'C', 'B': 'D'} if key.startswith('crc') else {'A': 'K', 'B': 'L'} if key == 'chat' else {'A': ''} if key == 'empty' else {'A': 'A'} if key == 'character' else {'A': '$'} if key == 'dollar' else {'A': '😀'} if key == 'emoji' else {'A': 'Uñ€😀'} if key == 'utf8' else {'B': 'ñ€'} if key == 'cp1252' else {'B': 'A' * 185}
            before = s['B'].app.get('COMP_TX', 0), s['A'].app.get('COMP_RX', 0)
            yield from self.message(messages, 1000 if key == 'compression' else 440)
            if key == 'compression':
                yield Check(s['B'].app.get('COMP_TX', 0) > before[0] and s['A'].app.get('COMP_RX', 0) > before[1], 'El receptor descomprimió y mostró los 185 bytes exactos.')
        elif key in ('local23', 'parity', 'flip', 'badcrc', 'lostack'):
            before = s['B'].local_events, s['B'].app.get('FEC', 0), s['B'].app.get('BAD', 0), s['A'].app.get('RETRY', 0), s['B'].app.get('DUP', 0)
            if key == 'local23':
                self.session.send('A', '/notch 1 3')
            if key == 'badcrc':
                self.session.send('A', '/badcrc')
            if key == 'lostack':
                self.session.send('B', '/dropack')
            counts = len(s['B'].messages)
            prior_round = s['A'].last_round.get('round', -1)
            self.session.queue_message('A', 'R')
            if key in ('parity', 'flip'):
                yield Wait(lambda: s['A'].last_round.get('round', -1) > prior_round and s['A'].last_round.get('sender') and s['A'].last_round.get('stage') == 0, 20, 'Esperando BEGIN para alterar el siguiente par de datos')
                self.session.send('A', '/erase 3' if key == 'parity' else '/flip 3')
            yield Wait(lambda: len(s['B'].messages) > counts, 230, 'Esperando reparación y entrega exacta de R')
            yield from self.idle()
            yield Check(list(s['B'].messages)[counts:] == ['R'], 'El fallo no produjo entrega errónea ni duplicada.')
            if key == 'local23':
                yield Check(s['B'].local_events > before[0], 'Se observó reconstrucción local 2 de 3 en el firmware.')
            if key == 'parity':
                yield Check(s['B'].app.get('FEC', 0) >= before[1] + 2, 'La matriz recuperó al menos dos bits.')
            if key == 'badcrc':
                yield Check(s['B'].app.get('BAD', 0) > before[2], 'Se observó CRC inválido y reparación posterior.')
            if key == 'lostack':
                yield Check(s['A'].app.get('RETRY', 0) > before[3] and s['B'].app.get('DUP', 0) > before[4], 'Se repitió el trabajo y el receptor reconoció el duplicado.')
        elif key in ('ir_a', 'ir_b', 'sound_a', 'sound_b') or key.startswith('physical'):
            src = 'B' if key.endswith('_b') else 'A'
            dest = 'B' if src == 'A' else 'A'
            fault = 1 if key.startswith('ir_') or key == 'physical_ir' else 2
            old_rx, old_messages = s[dest].app.get('RX', 0), len(s[dest].messages)
            old_bad = s[dest].app.get('BAD', 0)
            old_turbo = s[src].timing.get('TURBO_ON', 0)
            self.session.queue_message(src, 'A' * 32 if key.startswith('physical') else 'M')
            yield Wait(lambda: s[src].mac.get('STATE') == 7 and s[src].app.get('PENDING'), 20, 'Esperando inicio de datos para introducir la interferencia')
            if key.startswith('physical'):
                yield Prompt(f"{src}→{dest}: {'apaga únicamente su LED IR con el switch' if key == 'physical_ir' else 'reproduce ruido junto al micrófono del destino, manteniendo IR despejado'}. No muevas los módulos. Pulsa «Acción realizada» cuando la interferencia esté aplicada.")
            else:
                self.session.send(src, '/fault ' + str(fault))
            checkpoint = s[dest].app.get('RX', 0)
            yield Wait(lambda: s[dest].app.get('RX', 0) > checkpoint, 140, 'Comprobando que siguen llegando bytes durante la interrupción')
            yield Check(s[dest].app.get('RX', 0) > old_rx, 'Hubo avance con la interferencia aplicada.')
            if key.startswith('physical'):
                yield Prompt('Restablece el switch o pausa el ruido. Deja los medios despejados y pulsa «Acción realizada».')
            else:
                yield Check(s[src].active == 3 - fault, 'El otro medio absorbió la transmisión.')
                if fault == 2:
                    yield Check(s[src].timing.get('TURBO_ON', 0) > old_turbo and s[src].timing.get('PILOT_STEP_MS') == 120 and s[src].timing.get('PILOT_PAIR_MS') == 800, 'Turbo IR activo y piloto de sonido espaciado en dos rondas.')
                self.session.send(src, '/fault 0')
            yield Wait(lambda: len(s[dest].messages) > old_messages, 400, 'Esperando la reconstrucción del mensaje después de restaurar el medio')
            yield from self.idle(60)
            yield Check(list(s[dest].messages)[old_messages:] == ['A' * 32 if key.startswith('physical') else 'M'], 'Mensaje completo y sin duplicados tras la interferencia.')
            if s[src].active != 3:
                self.session.send(src, '/probe')
                yield Pause(.4)
                yield from self.idle(40)
            yield Check(s[src].active == 3, 'Ambos medios reincorporados.')
            if key == 'physical_crc':
                yield Check(s[dest].app.get('BAD', 0) > old_bad, 'Se observó CRC inválido por la interferencia física. Si no aparece, esta evidencia no queda demostrada aunque PHY haya compensado el ruido.')
        elif key == 'demo':
            for src in ('A', 'B'):
                before = s[src].timing.get('TURBO_ON', 0)
                self.session.send(src, '/fault 2')
                self.session.send(src, '/probe')
                yield Pause(.4)
                yield from self.idle(40)
                yield Check(s[src].active == 1 and s[src].timing.get('Q_MS') == 1000 and s[src].timing.get('TURBO_ON', 0) == before, src + ': demostración a 1000 ms sin activar Turbo.')
                self.session.send(src, '/fault 0')
                self.session.send(src, '/probe')
                yield Pause(.4)
                yield from self.idle(40)
                yield Check(s[src].active == 3, src + ': sonido restaurado.')
        yield from self.integrity()
