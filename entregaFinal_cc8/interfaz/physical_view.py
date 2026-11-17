"""Lectura didáctica de la telemetría existente. No controla el transporte."""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTabWidget, QScrollArea, QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView)

from .protocol import CRC_NAMES, HS_NAMES, MAC_NAMES, STAGES, TAGS, matrix_word

GREEN, AMBER, MUTED = '#6fe0b6', '#f4c577', '#8ca7b8'
MEDIA = {0: 'Sin canal disponible', 1: 'Solo IR', 2: 'Solo sonido', 3: 'IR + sonido'}


def text(value='', muted=False):
    w = QLabel(value)
    w.setWordWrap(True)
    if muted:
        w.setObjectName('muted')
    w.setTextFormat(Qt.TextFormat.PlainText)
    return w


def table(headers, rows=0, height=None):
    w = QTableWidget(rows, len(headers))
    w.setHorizontalHeaderLabels(headers)
    w.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    w.verticalHeader().hide()
    w.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    w.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    w.setWordWrap(True)
    w.verticalHeader().setDefaultSectionSize(36)
    if height:
        w.setFixedHeight(height)
    return w


def fill(w, rows, colors=None):
    w.setRowCount(len(rows))
    for row, values in enumerate(rows):
        for col, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if colors and (row, col) in colors:
                item.setForeground(QColor(colors[row, col]))
            w.setItem(row, col, item)


def matrix_cells(r):
    """No inferir casillas desconocidas a partir de una trama RX todavía parcial."""
    if not r or not r.get('real'):
        return []
    encoded = matrix_word((r['frame'] >> (18 - 6 * r['block'])) & 63)
    sender = r['sender']
    known = 255 if sender else r['known'] | r['fixed']
    values = encoded if sender else (r['values'] & ~r['fixed']) | (encoded & r['fixed'])
    return [{'bit': (values >> p) & 1 if known & (1 << p) else None,
             'fixed': not sender and bool(r['fixed'] & (1 << p)),
             'planned': sender} for p in range(8)]


def frame_bits(r):
    if not r or not r.get('real'):
        return '?' * 24
    return ''.join(str((r['frame'] >> bit) & 1)
                   if r['sender'] or r['frame_mask'] & (1 << ((23 - bit) // 6)) else '?'
                   for bit in range(23, -1, -1))


@dataclass
class Observation:
    node: str
    source: str
    time: str
    round: dict
    sweeps: dict
    app: dict
    mac: dict
    timing: dict
    local_count: int
    handshake: tuple
    handshake_sweeps: dict


class PhysicalHistory:
    """Instantáneas acotadas; las rondas nunca heredan barridos de otra ronda."""
    def __init__(self):
        self.rounds = {n: deque(maxlen=256) for n in 'AB'}
        self.handshakes = {n: deque(maxlen=32) for n in 'AB'}
        self.hs_sweeps = {n: {} for n in 'AB'}
        self.evidence = {n: deque(maxlen=48) for n in 'AB'}
        self.sources = {}
        self.times = {}

    def reset(self, node=None):
        for n in (node,) if node else 'AB':
            self.rounds[n].clear()
            self.handshakes[n].clear()
            self.hs_sweeps[n].clear()
            self.evidence[n].clear()
            self.sources.pop(n, None)
            self.times.pop(n, None)

    def consume(self, node, event, state):
        if node not in self.rounds:
            return
        if event['kind'] == 'reboot':
            self.reset(node)
        source = event.get('source')
        if source:
            if self.sources.get(node) and self.sources[node] != source:
                self.reset(node)
            self.sources[node] = source
            self.times[node] = event.get('time', '')
        if event.get('line', '').startswith('PHY_HS EVENT='):
            key = (state.mac.get('EVENT'), state.mac.get('STATE'), state.mac.get('REQ'))
            previous = self.handshakes[node][-1] if self.handshakes[node] else None
            if not previous or previous['key'] != key:
                self.handshakes[node].append({'key': key, 'mac': deepcopy(state.mac),
                                              'time': event.get('time', '')})
        if event['kind'] == 'sweep' and event['tag'] == 0:
            self.hs_sweeps[node][event['lane']] = deepcopy(event)
        if event['kind'] == 'round':
            r = state.last_round
            previous = self.rounds[node][-1].round if self.rounds[node] else {}
            obs = Observation(node, self.sources.get(node, 'observado'),
                event.get('time', ''), deepcopy(r),
                deepcopy({key: s for key, s in state.sweeps.items() if s['round'] == r['round']}),
                deepcopy(state.app), deepcopy(state.mac), deepcopy(state.timing),
                state.local_events, deepcopy(tuple(self.handshakes[node])), deepcopy(self.hs_sweeps[node]))
            self.rounds[node].append(obs)
            marks = []
            if any(s['reconstructed'] for s in obs.sweeps.values()):
                marks.append('Rescate 2/3')
            if not r['sender'] and r['fixed'] and r['fec'] > previous.get('fec', 0):
                marks.append('Paridad recuperó bits')
            if not r['sender'] and r['stage'] == 2 and r['real'] and r['frame_mask'] == 15 and (
                    r['crc_received'] != r['crc_calculated'] or r['field'] != 10):
                marks.append('CRC / FIELD inválido')
            if r['stage'] in (3, 4):
                marks.append('Reparación de posición')
            if r['turbo'] and not previous.get('turbo'):
                marks.append('Turbo IR ×2')
            if r['real'] and r['stage'] == 2 and r['done']:
                marks.append('Trama completada')
            if marks:
                self.evidence[node].append((' · '.join(marks), obs))


class RoundTimeline(QWidget):
    """Esquema temporal calculado desde T y escalón reportados, no señal capturada."""
    def __init__(self):
        super().__init__()
        self.round = {}
        self.setMinimumHeight(112)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.round
        if not r:
            p.setPen(QColor(MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'La primera ronda recibida dibujará su reparto de tiempo aquí.')
            return
        period, step = r['period_ms'], r['step_ms']
        if period <= 0:
            return
        width = self.width() - 32
        names = ('H0 · tipo', 'H1 · canales', 'DATOS', 'RETORNO')
        colors = ('#29556b', '#33527b', '#146d59', '#795c31')
        for i, name in enumerate(names):
            x = 16 + int(width * 3 * step * i / period)
            right = 16 + int(width * 3 * step * (i + 1) / period)
            p.fillRect(x, 29, right-x-2, 46, QColor(colors[i]))
            p.setPen(QColor('#eef7f7'))
            p.drawText(x, 29, right-x-2, 46, Qt.AlignmentFlag.AlignCenter, name)
            p.setPen(QColor(MUTED))
            p.drawText(x, 14, str(3*step*i) + ' ms')
            for j in (1, 2):
                xx = x + int((right-x)*j/3)
                p.setPen(QPen(QColor('#7fa0ac'), 1, Qt.PenStyle.DotLine))
                p.drawLine(xx, 61, xx, 74)
        p.setPen(QColor(MUTED))
        p.drawText(self.width()-76, 14, f'{period} ms')
        p.drawText(16, 99, f'12 escalones × {step} ms = {12*step} ms activos  ·  margen {max(0, period-12*step)} ms')


class SweepCard(QGroupBox):
    def __init__(self, name):
        super().__init__(name)
        self.name = name
        v = QVBoxLayout(self)
        self.head = text('Esperando un barrido medido…')
        v.addWidget(self.head)
        self.graph = MeasuredSweep()
        v.addWidget(self.graph)
        self.metrics = table(('Paso', 'Hz', 'Flancos', 'Esperados', 'Validez'), height=147)
        v.addWidget(self.metrics)
        self.explanation = text('', True)
        v.addWidget(self.explanation)

    def render(self, s):
        self.graph.sweep = s
        self.graph.update()
        if not s:
            self.head.setText('Sin captura de esta fase en la ronda elegida.')
            fill(self.metrics, [])
            self.explanation.setText('No se reutilizan mediciones de otra ronda para completar esta vista.')
            return
        symbol = str(s['symbol']) if s['symbol'] >= 0 else 'no reconocido'
        self.head.setText(f'{"Baja ↑ · ida" if s["band"] == 0 else "Alta ↓ · vuelta"}  ·  símbolo {symbol}'
                          + ('  ·  RESCATE 2/3' if s['reconstructed'] else ''))
        rows, colors = [], {}
        for i in range(3):
            expected = s['hz'][i] * s['windows'][i] / 1000
            rows.append((i+1, s['hz'][i], s['edges'][i], f'{expected:.1f}', 'Válido' if s['valid'] & (1 << i) else 'Descartado'))
            colors[i, 4] = GREEN if s['valid'] & (1 << i) else AMBER
        fill(self.metrics, rows, colors)
        windows = ' / '.join(str(n) for n in s['windows'])
        self.explanation.setText(f'Ventana útil: {windows} ms. N esperado ≈ f × T / 1000.\n'
            f'Pendiente medida: {s["slope"]} Hz/s. '
            + ('Dos escalones sanos identificaron un único patrón.' if s['reconstructed'] else
               'Patrón aceptado por la K8.' if s['symbol'] >= 0 else 'La K8 no aceptó este patrón; no equivale a un bit 0.')
            + f' Código de diagnóstico: {s["reason"]}.')


class MeasuredSweep(QWidget):
    def __init__(self):
        super().__init__()
        self.sweep = None
        self.setMinimumHeight(125)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor('#0b171f'))
        s = self.sweep
        if not s:
            p.setPen(QColor(MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Sin medición')
            return
        hz = s['hz']
        low, high = min(hz), max(hz)
        gap = max(40, (high-low)*0.25)
        low, high = max(0, low-gap), high+gap
        points = [(48+i*(self.width()-96)/2, self.height()-25-(h-low)*(self.height()-53)/max(1, high-low)) for i, h in enumerate(hz)]
        for i, (x, y) in enumerate(points):
            color = QColor(GREEN if s['valid'] & (1 << i) else AMBER)
            p.setPen(QPen(color, 2))
            if i:
                p.drawLine(int(points[i-1][0]), int(points[i-1][1]), int(x), int(y))
            p.setBrush(color)
            p.drawEllipse(int(x)-4, int(y)-4, 8, 8)
            p.drawText(int(x)-36, max(15, int(y)-9), f'{hz[i]} Hz')
            p.setPen(QColor(MUTED))
            p.drawText(int(x)-19, self.height()-5, f'Paso {i+1}')


class PhysicalView(QWidget):
    def __init__(self, session):
        super().__init__()
        self.session = session
        self.history = PhysicalHistory()
        self.selected = None  # Frozen observation object, not an index that shifts on append.
        self.snapshot = None
        self.local_nodes = ('A', 'B')
        self._last_signature = None
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        tools = QHBoxLayout()
        tools.addWidget(text('Observar K8'))
        self.node = QComboBox()
        self.node.addItems(('A', 'B'))
        self.node.setCurrentText('B')
        self.node.currentTextChanged.connect(self.change_node)
        tools.addWidget(self.node)
        self.source = text('SIN DATOS', True)
        tools.addWidget(self.source, 1)
        self.previous = QPushButton('← Ronda')
        self.next = QPushButton('Ronda →')
        self.pause = QPushButton('Pausar vista')
        self.live = QPushButton('Volver al vivo')
        self.previous.clicked.connect(lambda: self.move(-1))
        self.next.clicked.connect(lambda: self.move(1))
        self.pause.clicked.connect(self.freeze)
        self.live.clicked.connect(self.resume)
        for b in (self.previous, self.next, self.pause, self.live):
            tools.addWidget(b)
        v.addLayout(tools)
        self.story = text('Conecta las tarjetas y activa el chat. Aquí verás cómo viajan los bits por los medios.')
        self.story.setObjectName('physicalStory')
        v.addWidget(self.story)
        self.context = text('Se muestran eventos de las K8, sin generar mediciones artificiales.', True)
        v.addWidget(self.context)
        self.chapters = QTabWidget()
        v.addWidget(self.chapters, 1)
        self.build_handshake()
        self.build_round()
        self.build_sweeps()
        self.build_matrix()
        self.build_channels()
        self.build_frame()
        self.chapters.setCurrentIndex(1)
        evidence_row = QHBoxLayout()
        evidence_row.addWidget(text('Volver a una evidencia'))
        self.evidence = QComboBox()
        self.evidence.activated.connect(self.jump_evidence)
        evidence_row.addWidget(self.evidence, 1)
        v.addLayout(evidence_row)
        self.note = text('La pantalla observa el enlace. Pausarla no detiene las tarjetas ni la captura del registro.', True)
        v.addWidget(self.note)
        self.refresh(force=True)

    def page(self, title, intro):
        area = QScrollArea()
        area.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        layout.addWidget(text(intro, True))
        area.setWidget(inner)
        self.chapters.addTab(area, title)
        return layout

    def build_handshake(self):
        v = self.page('1 · Turno', 'Cualquiera puede solicitar transmitir. Las bandas separan la ida y la respuesta; A/B solo desempata una solicitud simultánea.')
        self.hs_state = text('Sin negociación registrada.')
        v.addWidget(self.hs_state)
        self.hs_events = table(('Hora', 'Evento observado', 'Estado'), height=198)
        v.addWidget(self.hs_events)
        self.hs_table = table(('Paso', 'Quién habla', 'Qué acuerdan'), 4, 190)
        fill(self.hs_table, [('SYN', 'Solicitante · banda baja ↑', '1111 + CFG: perfil, Turbo y paridad'),
            ('SYN-ACK', 'Receptor · banda alta ↓', 'Devuelve el mismo CFG'),
            ('SFD', 'Solicitante · banda baja ↑', '0000: comienza el cuerpo de la trama'),
            ('SFD-ACK', 'Receptor · banda alta ↓', 'Devuelve CFG invertido')])
        v.addWidget(self.hs_table)
        v.addWidget(text('Durante SYN/SFD: escalón fijo de 75 ms. Al entrar a datos cambia el período de ronda, según el perfil elegido.'))
        v.addWidget(text('Reloj cruzado: primer pulso de 12 ms (SYN), 20 ms (SYN-ACK), 28 ms (SFD) o 32 ms (SFD-ACK); los siguientes usan 37 ms. Son los tiempos configurados del saludo, no una captura eléctrica del cable.', True))
        v.addWidget(text('Empate ≤ 2 ms: A gana y B conserva su mensaje. Sin aceptación en 1100 ms: espera de 40–140 ms antes de reintentar. Estos valores describen el firmware; la tabla superior muestra su actividad observada.', True))
        v.addStretch()

    def build_round(self):
        v = self.page('2 · Ronda', 'Una ronda conversa en cuatro fases. En DATOS viajan dos bits distintos al mismo tiempo; en RETORNO se comprueban antes del CRC final.')
        self.round_title = text('Esperando la primera ronda…')
        self.round_title.setObjectName('section')
        v.addWidget(self.round_title)
        self.primed = table(('Medio', 'Bit / símbolo', 'Retorno', 'Validación'), 2, 118)
        self.primed.verticalHeader().setDefaultSectionSize(40)
        v.addWidget(self.primed)
        self.primed_note = text('', True)
        v.addWidget(self.primed_note)
        self.timeline = RoundTimeline()
        v.addWidget(self.timeline)
        v.addWidget(text('Esquema calculado con los tiempos reportados; no representa una captura de osciloscopio.', True))
        self.phase_table = table(('Fase', 'Lo que transporta', 'Dato de esta ronda'), 4, 200)
        v.addWidget(self.phase_table)
        v.addWidget(text('1 Hz = una ronda de 1000 ms. Los tonos dentro de la ronda siguen en cientos o miles de Hz: son magnitudes distintas.', True))
        v.addStretch()

    def build_sweeps(self):
        v = self.page('3 · Barridos', 'Cada símbolo usa tres frecuencias. La dirección distingue ida/vuelta; el tamaño del salto distingue el símbolo. Se grafican frecuencias medidas, no una onda inventada.')
        selector = QHBoxLayout()
        selector.addWidget(text('Ver fase'))
        self.tag = QComboBox()
        self.tag.addItems(TAGS)
        self.tag.setCurrentIndex(3)
        self.tag.currentIndexChanged.connect(lambda: self.refresh(force=True))
        selector.addWidget(self.tag, 1)
        v.addLayout(selector)
        row = QHBoxLayout()
        self.sweep_cards = [SweepCard('INFRARROJO'), SweepCard('SONIDO')]
        for card in self.sweep_cards:
            row.addWidget(card, 1)
        v.addLayout(row)
        v.addWidget(text('Filtros del receptor: ≥ 3 períodos, densidad ≈ f × T (±35 % + 2), tono ±1.2 %, dirección y patrón único. Un solo paso perdido puede rescatarse con los otros dos; dos pasos perdidos no bastan.'))
        v.addWidget(text('Pendiente: m = (f₂ − f₁) / Δt. Los flancos y ventanas de la tabla son telemetría; la validez y el rescate son decisiones reportadas por la K8.', True))
        v.addStretch()

    def build_matrix(self):
        v = self.page('4 · Matriz', 'Cada bloque lleva seis bits del cuerpo y dos paridades cruzadas. Las columnas se llenan ronda a ronda y permiten resolver posiciones perdidas durante la transmisión.')
        self.matrix_title = text('Sin bloque de datos observado.')
        self.matrix_title.setObjectName('section')
        v.addWidget(self.matrix_title)
        self.matrix = table(('Fila lógica', 'Ronda 1', 'Ronda 2', 'Ronda 3', 'Paridad'), 2, 132)
        v.addWidget(self.matrix)
        v.addWidget(text('Verde: recibido o planeado (TX) · Ámbar: reconstruido por paridad · ?: aún desconocido. Las filas son posiciones lógicas; un canal sano puede transportar ambas.', True))
        self.equations = text('pIR = i₁ ⊕ s₂ ⊕ i₃\npSND = s₁ ⊕ i₂ ⊕ s₃\nDatos ⊕ paridad debe dar 0 en cada ecuación completa.')
        v.addWidget(self.equations)
        self.recovery = text('')
        v.addWidget(self.recovery)
        v.addWidget(text('Tres defensas, en orden:'))
        self.defenses = table(('Nivel', 'Qué recupera', 'Evidencia de esta K8'), 3, 160)
        v.addWidget(self.defenses)
        v.addWidget(text('Si quedan dos incógnitas en una misma ecuación, se solicita una posición por REPAIR. El CRC-8 revisa el byte al completar la trama; cumple un papel distinto a la validación de bits en vivo.', True))
        v.addStretch()

    def build_channels(self):
        v = self.page('5 · Canales', 'Si falla un medio, el sano absorbe sus posiciones. Los pilotos comprueban el canal suspendido y tres respuestas correctas seguidas permiten reincorporarlo.')
        self.channel_title = text('Sin máscara observada.')
        self.channel_title.setObjectName('section')
        v.addWidget(self.channel_title)
        self.channel_table = table(('Medio', 'Estado en la dirección observada', 'Trabajo'), 2, 122)
        v.addWidget(self.channel_table)
        self.turbo = text('Turbo: esperando telemetría.')
        v.addWidget(self.turbo)
        self.capacity = text('', True)
        v.addWidget(self.capacity)
        pilot = QGroupBox('Piloto de sonido durante Turbo Solo-IR')
        pv = QVBoxLayout(pilot)
        self.pilot = text('Ronda rápida 1: piloto de ida → Ronda rápida 2: respuesta del piloto.')
        pv.addWidget(self.pilot)
        pv.addWidget(text('El sonido conserva el tiempo de dos rondas rápidas. El IR sigue llevando datos en ambas. La prueba del buzzer no se acelera al doble.', True))
        v.addWidget(pilot)
        self.channel_note = text('', True)
        v.addWidget(self.channel_note)
        v.addStretch()

    def build_frame(self):
        v = self.page('6 · Trama', 'La trama organiza los bits. Los barridos, primados y matrices son la capa física que los transporta y protege en el camino.')
        v.addWidget(text('SYN 1111 → SFD 0000 → Control (4) → DATA (8) → CRC (8) → FIELD 1010'))
        self.frame_title = text('Aún no hay una trama de usuario observada.')
        self.frame_title.setObjectName('section')
        v.addWidget(self.frame_title)
        self.crc_note = text('El CRC se compara cuando están completos los cuatro bloques.', True)
        v.addWidget(self.crc_note)
        self.frame_table = table(('Campo', 'Bits conocidos', 'Interpretación'), 4, 195)
        v.addWidget(self.frame_table)
        self.blocks = table(('Bloque', 'Seis bits del cuerpo', 'Contenido', 'Estado'), 4, 190)
        v.addWidget(self.blocks)
        v.addWidget(text('Cada trama DATA transporta exactamente un byte. Un carácter UTF-8 puede necesitar varias tramas. La compresión se aplica al mensaje antes de repartirlo en bytes.', True))
        v.addStretch()

    def set_local_nodes(self, nodes):
        self.local_nodes = tuple(nodes)
        if self.node.currentText() not in nodes:
            self.node.setCurrentText(nodes[0])
        self.node.setEnabled(len(nodes) > 1)

    def consume(self, node, event):
        self.history.consume(node, event, self.session.states[node])
        if event['kind'] == 'reboot' and self.node.currentText() == node:
            self.selected = None

    def change_node(self):
        self.selected = None
        self.refresh(force=True)

    def freeze(self):
        rows = self.history.rounds[self.node.currentText()]
        if rows:
            self.selected = rows[-1]
        self.refresh(force=True)

    def resume(self):
        self.selected = None
        self.refresh(force=True)

    def jump_evidence(self, index):
        obs = self.evidence.itemData(index)
        if obs is None:
            return
        self.selected = obs
        label = self.evidence.itemText(index)
        if '2/3' in label:
            self.chapters.setCurrentIndex(2)
            tag = next(s['tag'] for s in obs.sweeps.values() if s['reconstructed'])
            self.tag.setCurrentIndex(tag)
        elif 'Paridad' in label or 'posición' in label:
            self.chapters.setCurrentIndex(3)
        elif 'Turbo' in label:
            self.chapters.setCurrentIndex(4)
        else:
            self.chapters.setCurrentIndex(5)
        self.refresh(force=True)

    def move(self, amount):
        rows = list(self.history.rounds[self.node.currentText()])
        if not rows:
            return
        index = next((i for i, r in enumerate(rows) if r is self.selected), len(rows)-1)
        self.selected = rows[max(0, min(len(rows)-1, index+amount))]
        self.refresh(force=True)

    def refresh(self, force=False):
        n = self.node.currentText()
        s = self.session.states[n]
        rows = self.history.rounds[n]
        obs = self.selected or (rows[-1] if rows else None)
        mac = obs.mac if self.selected else s.mac
        app = obs.app if self.selected else s.app
        hs = obs.handshake if self.selected else tuple(self.history.handshakes[n])
        signature = (id(obs), tuple(mac.items()), tuple(app.items()), self.tag.currentIndex(),
                     bool(self.selected), s.connected, self.history.sources.get(n), len(hs),
                     tuple((lane, sweep['tick']) for lane, sweep in self.history.hs_sweeps[n].items()))
        if not force and signature == self._last_signature:
            return
        self._last_signature = signature
        self.snapshot = obs
        self.evidence.blockSignals(True)
        self.evidence.clear()
        self.evidence.addItem('Selecciona un evento destacado de esta K8…', None)
        for title, saved in reversed(self.history.evidence[n]):
            self.evidence.addItem(f'Ronda {saved.round["round"]} · {title}', saved)
            if saved is self.selected:
                self.evidence.setCurrentIndex(self.evidence.count()-1)
        self.evidence.setEnabled(self.evidence.count() > 1)
        self.evidence.blockSignals(False)
        r = obs.round if obs else {}
        source = obs.source if self.selected else self.history.sources.get(n, '')
        source_name = 'ARCHIVO IMPORTADO' if source == 'archivo importado' else 'EN VIVO · USB' if source == 'observado' and s.connected else 'CAPTURA CONSERVADA' if source else 'SIN DATOS'
        self.source.setText(source_name + (' · VISTA PAUSADA' if self.selected else ''))
        self.previous.setEnabled(bool(rows))
        self.next.setEnabled(bool(self.selected))
        self.pause.setEnabled(bool(rows) and not self.selected)
        self.live.setEnabled(bool(self.selected))
        state = mac.get('STATE')
        latest_hs = mac.get('EVENT', '')
        if self.selected:
            story = f'Ronda {r["round"]} guardada: puedes recorrerla sin alterar el registro.' if source == 'archivo importado' else f'Ronda {r["round"]} guardada: puedes leerla mientras las tarjetas continúan.'
        elif state in (1, 2, 3, 4, 5, 6, 9):
            story = HS_NAMES.get(latest_hs, MAC_NAMES.get(state, 'Negociando el turno.'))
        elif state == 0:
            story = 'Escuchando: el próximo byte comenzará con una nueva negociación.' if app.get('RUN') else 'Chat detenido. Actívalo para permitir nuevas transmisiones.'
        elif r:
            story = ('Reparando una posición del bloque.' if r['stage'] in (3, 4) else
                'El IR lleva los datos al doble de ritmo; el sonido se prueba en dos rondas.' if r['turbo'] else
                'La K8 comprueba el bloque antes de continuar.' if r['stage'] == 2 else
                'IR y sonido transportan dos bits en paralelo.' if not r['control'] and r['mask'] == 3 else
                'El medio disponible transporta las posiciones pendientes.' if not r['control'] else 'Comienza un bloque de seis bits.')
        else:
            story = 'Conecta las tarjetas, aplica la configuración y activa el chat para observar la capa física.'
        self.story.setText(story)
        time = obs.time[11:23] if obs and len(obs.time) > 11 else '—'
        role = ('TX · planeada; retorno observado' if r.get('sender') else 'RX · recepción y retorno preparado') if r else 'sin ronda'
        self.context.setText(f'K8 {n} · {MAC_NAMES.get(state, "sin estado de enlace")} · {role} · captura {time}'
            + (f' · ronda {r["round"]}, bloque {r["block"]+1}/4' if r and r['real'] else ''))
        self.render_handshake(s, mac, hs, r)
        self.render_round(r)
        for lane, card in enumerate(self.sweep_cards):
            if self.tag.currentIndex() == 0:
                sweep = obs.handshake_sweeps.get(lane) if self.selected and obs else self.history.hs_sweeps[n].get(lane)
            else:
                sweep = obs.sweeps.get((self.tag.currentIndex(), lane)) if obs else None
            card.render(sweep)
            if sweep and self.tag.currentIndex() == 0:
                card.explanation.setText(('Último saludo guardado antes de esta ronda.' if self.selected else 'Última captura SYN/SFD.')
                    + f' Tick de captura: {sweep["tick"]} ms; independiente de la ronda DATA.\n' + card.explanation.text())
        self.render_matrix(r, obs, app)
        self.render_channels(r)
        self.render_frame(r)

    def render_handshake(self, state, mac, hs, r):
        self.hs_state.setText(f'Último estado: {MAC_NAMES.get(mac.get("STATE"), "sin datos")} · '
            f'{HS_NAMES.get(mac.get("EVENT"), mac.get("EVENT", "esperando eventos"))}\n'
            f'SYN/SFD: escalón fijo 75 ms → datos observados: ronda {r.get("period_ms", "—")} ms, escalón {r.get("step_ms", "—")} ms')
        fill(self.hs_events, [(item['time'][11:23], HS_NAMES.get(item['mac'].get('EVENT'), item['mac'].get('EVENT', '—')),
                              MAC_NAMES.get(item['mac'].get('STATE'), '—')) for item in hs[-8:]])

    def render_round(self, r):
        self.timeline.round = r
        self.timeline.update()
        if not r:
            self.round_title.setText('Esperando la primera ronda…')
            fill(self.phase_table, [])
            fill(self.primed, [])
            self.primed_note.setText('Los eventos se muestran cuando el firmware termina su lectura de la ronda.')
            return
        stage = STAGES[r['stage']] if r['stage'] < len(STAGES) else 'ENCABEZADO NO VÁLIDO'
        self.round_title.setText(f'Ronda {r["round"]} · {stage} · {r["period_ms"]} ms ({1000/max(1,r["period_ms"]):.2f} Hz)')
        h = ['??' if x > 3 else f'{x:02b}' for x in r['headers']]
        fill(self.phase_table, [('H0', 'Tipo de ronda + bit alternante', h[0]),
            ('H1', 'Máscara de canales / control', h[1]),
            ('DATOS', 'Dos bits paralelos / símbolo de control', str(r['bits'])),
            ('RETORNO', 'Primados / estado de confirmación', str(r['replies']))])
        rows, colors = [], {}
        for lane, name in enumerate(('IR', 'Sonido')):
            bit, reply = r['bits'][lane], r['replies'][lane]
            if r['turbo'] and lane == 1:
                values = (name, 'Piloto', 'Dos rondas', 'No es un segundo bit DATA')
            elif not r['control'] and not (r['mask'] & (1 << lane)):
                values = (name, 'Piloto / sin DATA', str(reply) if reply >= 0 else '?', 'Fuera de la máscara')
            elif r['control']:
                status = {0: 'ACK', 1: 'Reparar bloque', 2: 'CRC / trama inválida', 3: 'Sin respuesta'}.get(reply, 'Sin respuesta')
                values = (name, str(bit) if bit >= 0 else '?', str(reply) if reply >= 0 else '?', status)
            else:
                good = bit in (0, 1) and reply in (0, 1)
                result = f'{bit} ⊕ {reply} = {bit ^ reply}' if good else 'Sin par válido'
                values = (name, str(bit) if bit >= 0 else '?', str(reply) if reply >= 0 else '?', result)
                colors[lane, 3] = GREEN if good and bit ^ reply == 1 else AMBER
            rows.append(values)
        fill(self.primed, rows, colors)
        if not r['control']:
            for lane in range(2):
                for col in (1, 2):
                    item = self.primed.item(lane, col)
                    if item.text() in ('0', '1', '?'):
                        item.setFont(QFont('Consolas', 19, QFont.Weight.Bold))
        self.primed_note.setText('TX: el retorno de esta tabla ya fue observado por el emisor.' if r['sender'] else
            'RX: la K8 preparó esta respuesta. Para comprobar que llegó, observa la ronda TX del otro extremo.')

    def render_matrix(self, r, obs, app):
        cells = matrix_cells(r)
        if cells:
            self.matrix_title.setText(f'Bloque {r["block"]+1}/4 · ' + ('Matriz TX planeada' if r['sender'] else 'Matriz RX observada'))
            rows, colors = [], {}
            for row, name in enumerate(('IR', 'Sonido')):
                values = [name]
                for col in range(4):
                    c = cells[2*col+row]
                    values.append('?' if c['bit'] is None else str(c['bit']))
                    colors[row, col+1] = AMBER if c['fixed'] else GREEN if c['bit'] is not None else MUTED
                rows.append(values)
            fill(self.matrix, rows, colors)
            for row in range(2):
                for col in range(4):
                    c = cells[2*col+row]
                    item = self.matrix.item(row, col+1)
                    item.setFont(QFont('Consolas', 18, QFont.Weight.Bold))
                    item.setToolTip('Reconstruido por paridad' if c['fixed'] else 'Planeado en TX' if c['planned'] else 'Desconocido' if c['bit'] is None else 'Recibido')
            unknown = sum(c['bit'] is None for c in cells)
            self.recovery.setText(f'Casillas desconocidas en esta vista: {unknown}. '
                + ('Un bloque TX muestra lo que se planeó enviar; no demuestra recepción.' if r['sender'] else
                   'Las casillas ámbar fueron reconstruidas por el firmware; las demás desconocidas siguen como ?.'))
            sums = []
            for name, group in (('pIR', (0, 3, 4, 6)), ('pSND', (1, 2, 5, 7))):
                vals = [cells[p]['bit'] for p in group]
                sums.append(name + ': ' + ' ⊕ '.join('?' if n is None else str(n) for n in vals)
                            + (' = ' + str(vals[0]^vals[1]^vals[2]^vals[3]) if None not in vals else ' → faltan casillas'))
            self.equations.setText('pIR = i₁ ⊕ s₂ ⊕ i₃     ·     pSND = s₁ ⊕ i₂ ⊕ s₃\n' + '\n'.join(sums) + '\nDatos ⊕ paridad debe dar 0 en cada ecuación completa.')
        else:
            self.matrix_title.setText('Sonda de canales: sin matriz de usuario.' if r else 'Sin bloque de datos observado.')
            fill(self.matrix, [])
            self.equations.setText('pIR = i₁ ⊕ s₂ ⊕ i₃\npSND = s₁ ⊕ i₂ ⊕ s₃\nDatos ⊕ paridad debe dar 0 en cada ecuación completa.')
            self.recovery.setText('No se crea una matriz DATA para las rondas de sonda.')
        fill(self.defenses, [('1 · Barrido', 'Un paso perdido de tres', f'{obs.local_count if obs else 0} símbolos rescatados (2/3)'),
            ('2 · Primado', 'Confirma cada bit de la ronda', 'b ⊕ retorno = 1; consulta «2 · Ronda»'),
            ('3 · Matriz', 'Una incógnita por ecuación', f'{r.get("fec", app.get("FEC", 0))} bits rescatados por paridad')])

    def render_channels(self, r):
        if not r:
            self.channel_title.setText('Esperando una máscara de canales observada.')
            fill(self.channel_table, [])
            self.turbo.setText('Turbo: esperando telemetría.')
            self.capacity.setText('')
            self.channel_note.setText('')
            return
        mask = r['active'] if r['sender'] else (1 if r['turbo'] else r['mask'] if not r['control'] else None)
        self.channel_title.setText(MEDIA.get(mask, 'Ronda de control: sin máscara DATA en H1')
            + (' · dirección local → remota' if r['sender'] else ' · dirección remota → local'))
        rows = []
        for lane, name in enumerate(('IR', 'Sonido')):
            enabled = mask is not None and mask & (1 << lane)
            rows.append((name, 'Activo para DATA' if enabled else 'No indicado en este control' if mask is None else 'Suspendido / piloto',
                'Datos y validación' if enabled else 'Prueba de recuperación' if mask is not None else 'Consultar una ronda DATA'))
        fill(self.channel_table, rows)
        t = r['period_ms']
        self.turbo.setText(f'TURBO SOLO-IR ACTIVO · {2*t} → {t} ms por ronda (×2) · escalón IR {r["step_ms"]} ms' if r['turbo'] else
                           f'Ritmo observado: {t} ms/ronda · escalón {r["step_ms"]} ms. Turbo no está activo en esta ronda.')
        count = 1 if r['turbo'] else mask.bit_count() if mask is not None else None
        self.capacity.setText((f'Capacidad en fase DATOS: {count} bit(s)/ronda × {1000/max(1,t):.2f} rondas/s = {count*1000/max(1,t):.2f} bit/s. '
             'No es el caudal neto del chat: encabezados, paridades y controles también consumen rondas.') if count is not None else
             'La capacidad DATA se calcula en una ronda de datos, con su máscara de canales.')
        self.pilot.setText(f'Par de rondas Turbo: {t} + {t} = {2*t} ms. Ida acústica en la primera; retorno en la segunda.' if r['turbo'] else
                           'En Turbo, el piloto de sonido abarca dos rondas IR. En demostración «log» se conserva 1 Hz sin Turbo.')
        self.channel_note.setText('En RX la máscara viene de H1 en rondas DATA; el reloj Turbo también identifica Solo-IR. ACTIVE local describe la salida de esa K8 y puede ser diferente. El evento no incluye el contador instantáneo de pilotos buenos; se muestra la reincorporación cuando aparece en la máscara.')

    def render_frame(self, r):
        bits = frame_bits(r)
        self.crc_note.setStyleSheet('color:' + MUTED)
        if not r or not r['real']:
            self.frame_title.setText('Sonda: no es una trama del chat.' if r else 'Aún no hay una trama de usuario observada.')
            fill(self.frame_table, [])
            fill(self.blocks, [])
            self.crc_note.setText('Se necesita una trama de usuario para mostrar sus campos y comprobar el CRC.')
            return
        self.frame_title.setText(('TX planeada' if r['sender'] else 'RX reconstruida hasta este punto') + f' · bloque {r["block"]+1}/4')
        ctrl = bits[:4]
        fill(self.frame_table, [('Control · 4', ctrl, f'{r["frame_type"]}, secuencia {r["frame_seq"]}' if '?' not in ctrl else 'Aún incompleto'),
            ('DATA · 8', bits[4:12], f'Byte 0x{r["data"]:02X}' if '?' not in bits[4:12] else 'Byte aún incompleto'),
            ('CRC · 8', bits[12:20], CRC_NAMES[r['crc_kind']]),
            ('FIELD · 4', bits[20:], 'Patrón esperado: 1010')])
        contents = ('Control + DATA[7:6]', 'DATA[5:0]', 'CRC[7:2]', 'CRC[1:0] + FIELD')
        fill(self.blocks, [(b+1, bits[6*b:6*b+6], contents[b],
            'Planeado' if r['sender'] else 'Aceptado' if r['frame_mask'] & (1 << b) else 'En curso' if b == r['block'] else 'Pendiente') for b in range(4)])
        if r['sender']:
            note = f'CRC TX: 0x{r["crc_received"]:02X} · calculado: 0x{r["crc_calculated"]:02X}. Es una trama planeada; su recepción se verifica en la otra K8.'
        elif r['frame_mask'] != 15:
            note = 'Trama parcial: los ? no han sido aceptados. Todavía no corresponde declarar CRC válido o inválido.'
        else:
            valid = r['crc_received'] == r['crc_calculated'] and r['field'] == 10
            note = f'CRC recibido 0x{r["crc_received"]:02X} · calculado 0x{r["crc_calculated"]:02X} · ' + ('VÁLIDO; FIELD correcto.' if valid else 'ERROR; requiere recuperación del enlace.')
            self.crc_note.setStyleSheet(f'color:{GREEN if valid else AMBER};font-size:14px;font-weight:600;padding:6px;')
        self.crc_note.setText(note)
