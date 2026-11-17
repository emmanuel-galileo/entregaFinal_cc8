from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path
import csv
import json
import sys
import time

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QTimer, QSettings, QUrl
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPen, QDesktopServices
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QLineEdit, QSplitter, QTabWidget, QTableView, QTableWidget,
    QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QHeaderView, QGroupBox, QGridLayout,
    QTextBrowser, QPlainTextEdit, QCheckBox, QSpinBox, QMessageBox, QFileDialog,
    QProgressBar, QScrollArea, QFrame, QAbstractItemView)

from .protocol import (BoardState, LogEntry, CRC_NAMES, FRAME_TYPES, MAC_NAMES, STAGES, TAGS,
                       PROFILES, matrix_word, export_session)
from .session import Session
from .tasks import TestRunner, CATALOG, BASIC, FULL, test_rate
from .webserver import WebChat
from .physical_view import PhysicalView, matrix_cells, frame_bits
from .chat_view import DualChat
from .interference import InterferencePanel


STYLE = '''
QWidget { background:#101b24; color:#dfebef; font-family:"Segoe UI"; font-size:12px; }
QMainWindow { background:#101b24; }
QLabel#title { font-size:23px; font-weight:700; }
QLabel { background:transparent; }
QLabel#muted { color:#93aab9; }
QLabel#section { color:#6fdfbd; font-weight:700; font-size:14px; }
QLabel#physicalStory { background:#17392f; border:1px solid #28745d; border-radius:8px; padding:12px; color:#adf3d5; font-size:16px; font-weight:600; }
QFrame#card, QGroupBox { background:#172630; border:1px solid #304653; border-radius:9px; }
QGroupBox { margin-top:16px; padding-top:12px; font-weight:600; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 5px; color:#9ab3c2; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextBrowser { background:#0c161e; border:1px solid #34505e; border-radius:6px; padding:6px; selection-background-color:#197b67; }
QComboBox { min-height:21px; }
QPushButton { background:#263d4b; border:1px solid #3a596a; border-radius:6px; padding:7px 12px; font-weight:600; }
QPushButton:hover { background:#34596b; }
QPushButton:pressed { background:#1b715e; }
QPushButton:disabled { color:#627b89; background:#1b2b35; border-color:#293e49; }
QPushButton#primary { background:#177d64; border-color:#26aa83; color:#f0fffa; }
QPushButton#danger { background:#65333a; border-color:#9a4d55; }
QPushButton#primary:disabled { background:#163b32; border-color:#284c40; color:#718f86; }
QPushButton#danger:disabled { background:#34242a; border-color:#49343d; color:#927e87; }
QTabWidget::pane { border:1px solid #304653; border-radius:7px; }
QTabBar::tab { background:#1c303d; padding:9px 13px; border-bottom:2px solid #1c303d; }
QTabBar::tab:selected { color:#6fdfbd; border-bottom-color:#41cfa5; background:#172630; }
QTreeWidget, QTableView, QTableWidget { background:#0e1a22; alternate-background-color:#172832; gridline-color:#263e4b; border:0; selection-background-color:#235b68; }
QHeaderView::section { background:#203644; color:#b8d0dc; padding:6px; border:0; }
QTreeWidget::item { padding:5px; }
QScrollArea { border:0; }
QProgressBar { background:#0b161e; border:1px solid #324e5c; border-radius:5px; text-align:center; min-height:18px; }
QProgressBar::chunk { background:#248f76; border-radius:4px; }
QCheckBox { spacing:7px; }
QSplitter::handle { background:#28404e; width:4px; height:4px; }
QToolTip { color:#edf7fa; background:#294653; border:1px solid #5b7c8c; padding:5px; }
'''


def button(text, callback, primary=False, danger=False):
    b = QPushButton(text)
    if primary:
        b.setObjectName('primary')
    if danger:
        b.setObjectName('danger')
    b.clicked.connect(callback)
    return b


def label(text='', muted=False):
    w = QLabel(text)
    w.setWordWrap(True)
    if muted:
        w.setObjectName('muted')
    return w


class LogModel(QAbstractTableModel):
    HEADERS = ('Hora', 'K8', 'Origen', 'Evento', 'Explicación')

    def __init__(self):
        super().__init__()
        self.rows = []

    def rowCount(self, parent=QModelIndex()):
        return len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 5

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self.rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return (item.time[11:23], item.node, item.origin, item.category, item.text)[index.column()]
        if role == Qt.ItemDataRole.ForegroundRole:
            return QColor({'error': '#ff8b96', 'warning': '#edc16a', 'success': '#75d8a8'}.get(item.severity, '#c3d7e2'))
        if role == Qt.ItemDataRole.ToolTipRole:
            return item.text + ('\n\nSerie: ' + item.raw if item.raw else '')

    def append(self, value):
        if len(self.rows) >= 10000:
            self.beginRemoveRows(QModelIndex(), 0, 0)
            self.rows.pop(0)
            self.endRemoveRows()
        self.beginInsertRows(QModelIndex(), len(self.rows), len(self.rows))
        self.rows.append(value)
        self.endInsertRows()

    def clear(self):
        self.beginResetModel()
        self.rows.clear()
        self.endResetModel()


class LogFilter(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.query = ''
        self.category = 'Todo'

    def filterAcceptsRow(self, row, parent):
        item = self.sourceModel().rows[row]
        return (self.category == 'Todo' or item.category == self.category) and self.query.casefold() in (
            item.text + ' ' + item.category + ' ' + item.node + ' ' + item.origin).casefold()


class SweepPlot(QWidget):
    def __init__(self):
        super().__init__()
        self.sweep = None
        self.setMinimumHeight(130)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor('#0c161e'))
        if not self.sweep:
            p.setPen(QColor('#819aaa'))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Los barridos medidos aparecerán al recibir eventos.')
            return
        s = self.sweep
        hz = s['hz']
        low, high = max(0, min(hz) - 50), max(hz) + 50
        if high <= low:
            high = low + 1
        points = [(40 + i * (self.width() - 80) / 2, self.height() - 28 - (h - low) * (self.height() - 60) / (high - low)) for i, h in enumerate(hz)]
        for i, (x, y) in enumerate(points):
            color = QColor('#53d7ad' if s['valid'] & (1 << i) else '#ed9c70')
            p.setPen(QPen(color, 3))
            if i:
                p.drawLine(int(points[i-1][0]), int(points[i-1][1]), int(x), int(y))
            p.setBrush(color)
            p.drawEllipse(int(x)-4, int(y)-4, 8, 8)
            p.drawText(int(x)-30, max(18, int(y)-12), f'{hz[i]} Hz')
            p.setPen(QColor('#9bb2c0'))
            p.drawText(int(x)-24, self.height()-7, f'Paso {i+1}')


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('CC8 · Chat y laboratorio del protocolo')
        self.resize(1380, 880)
        self.setMinimumSize(1024, 700)
        self.settings = QSettings('CC8', 'Laboratorio')
        self.session = Session()
        self.runner = TestRunner(self.session)
        self.dirty = True
        self.paused_scroll = False
        self.replay_queue = deque()
        self.replay_timer = QTimer(self)
        self.replay_timer.setInterval(100)
        self.replay_timer.timeout.connect(self.replay_tick)
        self.replay_mode = False
        self.build_ui()
        self.web = WebChat(self.session, lambda: self.runner.running, self.runner.cancel)
        self.interference = InterferencePanel(self.session, self.runner.note_intervention, self)
        self.session.entry.connect(self.on_entry)
        self.session.updated.connect(lambda _: setattr(self, 'dirty', True))
        self.session.event.connect(self.on_event)
        self.session.connected.connect(lambda *_: self.refresh_connections())
        self.runner.changed.connect(self.update_tests)
        self.runner.prompt.connect(self.show_prompt)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(180)
        self.refresh_timer.timeout.connect(self.render)
        self.refresh_timer.start()
        self.refresh_ports()
        self.mode_changed()

    def guard(self, callback):
        try:
            return callback()
        except Exception as exc:
            QMessageBox.warning(self, 'CC8', str(exc))

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 12, 16, 12)
        title = QHBoxLayout()
        name = label('CC8  /  Protocolo en vivo')
        name.setObjectName('title')
        name.setWordWrap(False)
        title.addWidget(name)
        title.addStretch()
        self.expand_protocol = QPushButton('Ampliar protocolo')
        self.expand_protocol.setCheckable(True)
        self.expand_protocol.toggled.connect(self.set_controls_compact)
        self.expand_protocol.setToolTip('Oculta la configuración para dar espacio a la explicación; no cambia el enlace.')
        title.addWidget(self.expand_protocol)
        self.mode = QComboBox()
        self.mode.addItems(('Una PC · dos K8', 'Dos PC · una K8 local'))
        self.mode.currentIndexChanged.connect(self.mode_changed)
        title.addWidget(self.mode)
        self.local_node = QComboBox()
        self.local_node.addItems(('Mi K8 es A', 'Mi K8 es B'))
        self.local_node.currentIndexChanged.connect(self.mode_changed)
        title.addWidget(self.local_node)
        title.addWidget(button('Chat web', lambda: QDesktopServices.openUrl(QUrl(self.web.url)), primary=True))
        layout.addLayout(title)
        self.connection_area = QHBoxLayout()
        self.cards = {}
        for node in ('A', 'B'):
            card = QFrame()
            card.setObjectName('card')
            v = QVBoxLayout(card)
            top = QHBoxLayout()
            badge = label('K8 ' + node)
            badge.setWordWrap(False)
            top.addWidget(badge)
            port = QComboBox()
            port.setMinimumWidth(190)
            top.addWidget(port, 1)
            connect = button('Conectar', lambda checked=False, n=node: self.guard(lambda: self.toggle_connection(n)), primary=True)
            top.addWidget(connect)
            v.addLayout(top)
            status = label('Desconectada · selecciona su puerto COM', True)
            v.addWidget(status)
            self.cards[node] = {'widget': card, 'port': port, 'connect': connect, 'status': status}
            self.connection_area.addWidget(card)
        layout.addLayout(self.connection_area)
        self.mode_note = label('', True)
        layout.addWidget(self.mode_note)
        self.controls_box = QWidget()
        controls = QHBoxLayout(self.controls_box)
        controls.setContentsMargins(0, 0, 0, 0)
        self.rate = QComboBox()
        for text, value in (('Demostración · 1 Hz', 'log'), ('Rápido · 1.25 Hz + Turbo IR', 'max'), ('1 Hz con Turbo', '1'), ('0.5 Hz con Turbo', '0.5')):
            self.rate.addItem(text, value)
        self.crc = QComboBox()
        self.crc.addItems(CRC_NAMES)
        self.encoding = QComboBox()
        self.encoding.addItem('UTF-8', 'utf-8')
        self.encoding.addItem('Extended ASCII · CP1252', 'cp1252')
        self.compression = QCheckBox('Compresión automática')
        self.compression.setChecked(True)
        for widget in (self.rate, self.crc, self.encoding, self.compression):
            controls.addWidget(widget)
        self.apply_button = button('Aplicar configuración', lambda: self.guard(self.apply_configuration))
        controls.addWidget(self.apply_button)
        self.start_button = button('Activar chat', lambda: self.guard(lambda: self.control_all('/start')), primary=True)
        self.stop_button = button('Detener', lambda: self.guard(self.stop), danger=True)
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        controls.addWidget(button('Puertos', self.refresh_ports))
        layout.addWidget(self.controls_box)
        split = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(split, 1)
        self.dual_chat = DualChat(self.session, lambda: self.encoding.currentData(),
            lambda node: self.guard(lambda: self.send_chat(node)))
        # Keep the programmatic send entry point used by the existing diagnostic scripts.
        self.sender = QComboBox()
        self.sender.addItems(('Enviar desde A', 'Enviar desde B'))
        self.input = self.dual_chat.panes['A'].input
        self.send_button = self.dual_chat.panes['A'].send
        self.byte_count = self.dual_chat.panes['A'].count
        self.chat = self.dual_chat.panes['A'].chat
        self.encoding.currentIndexChanged.connect(self.count_bytes)
        split.addWidget(self.dual_chat)
        self.tabs = QTabWidget()
        self.physical = PhysicalView(self.session)
        self.tabs.addTab(self.physical, 'En vivo')
        self.tabs.addTab(self.make_protocol(), 'Detalle PHY')
        self.tabs.addTab(self.make_tests(), 'Pruebas')
        self.tabs.addTab(self.make_logs(), 'Registro')
        split.addWidget(self.tabs)
        split.setSizes((390, 950))
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setCollapsible(0, False)
        split.setCollapsible(1, False)
        self.split = split
        self.guide_bar = QHBoxLayout()
        self.interference_button = button('Interrumpir en vivo…', self.show_interference)
        self.interference_button.setToolTip('Apagar medios u omitir escalones sin STOP; abre un panel que permite seguir viendo la transmisión.')
        self.guide_bar.addWidget(self.interference_button)
        self.quick_tests = []
        for title, key, chapter in (('Chat · 1 Hz', 'presentacion', 1),
                ('Rescate 2/3', 'local23', 2), ('Matriz', 'parity', 3),
                ('CRC → reparación', 'badcrc', 5), ('Turbo IR ×2', 'sound_a', 4)):
            b = button(title, lambda checked=False, k=key, c=chapter: self.guard(lambda: self.demonstrate(k, c)))
            b.setToolTip('Usa las dos K8 locales. ' + ('Interrupción de sonido por software; modo rápido.' if key == 'sound_a' else
                'Inyección por software; datos a 1 Hz.' if key != 'presentacion' else 'Mensajes por los medios físicos a 1 Hz.'))
            self.quick_tests.append(b)
            self.guide_bar.addWidget(b)
        self.live_cancel = button('Cancelar prueba', self.runner.cancel, danger=True)
        self.guide_bar.addWidget(self.live_cancel)
        layout.addLayout(self.guide_bar)
        self.live_progress = label('Conecta → aplica configuración → activa el chat → envía un mensaje. Las vistas numeradas explican el recorrido.', True)
        layout.addWidget(self.live_progress)
        self.footer = label('Listo · conecta las K8 para comenzar.', True)
        layout.addWidget(self.footer)
        self.render_chat()

    def make_tests(self):
        widget = QWidget()
        v = QVBoxLayout(widget)
        v.addWidget(label('Pruebas a 1 Hz para leer cada ronda; SYN y SFD siguen rápidos. Solo las dos pruebas de Turbo usan modo rápido. Demostración: unos 2 minutos. Cancelar conserva los mensajes pendientes.', True))
        self.tests = QTreeWidget()
        self.tests.setHeaderLabels(('Prueba', 'Duración', 'Resultado'))
        self.test_items = {}
        groups = {}
        for key, group, title, duration in CATALOG:
            if group not in groups:
                groups[group] = QTreeWidgetItem(self.tests, (group, '', ''))
                groups[group].setForeground(0, QColor('#6fd9b5'))
            item = QTreeWidgetItem(groups[group], (title, duration, 'Pendiente'))
            item.setData(0, Qt.ItemDataRole.UserRole, key)
            rate = test_rate(key)
            item.setToolTip(0, title + (' · Rápido + Turbo IR: comprueba aceleración' if rate == 'max' else ' · Modelo local con resultados pausados' if rate is None else ' · Datos a 1 Hz, sin Turbo; SYN y SFD rápidos'))
            self.test_items[key] = item
        self.tests.expandAll()
        self.tests.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tests.setColumnWidth(1, 68)
        self.tests.setColumnWidth(2, 105)
        v.addWidget(self.tests, 1)
        row = QHBoxLayout()
        self.run_one = button('Ejecutar selección', lambda: self.guard(self.run_selected), primary=True)
        self.run_demo = button('Demostración · 2 min', lambda: self.guard(lambda: self.runner.start(('presentacion',))), primary=True)
        self.run_basic = button('Tanda básica', lambda: self.guard(lambda: self.runner.start(BASIC)))
        self.run_full = button('Completa · larga', lambda: self.guard(lambda: self.runner.start(FULL)))
        self.cancel_button = button('Cancelar', self.runner.cancel, danger=True)
        for b in (self.run_demo, self.run_one, self.run_basic, self.run_full, self.cancel_button):
            row.addWidget(b)
        v.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        v.addWidget(self.progress)
        self.test_progress = label('Selecciona una prueba o una tanda. Las duraciones son aproximadas.', True)
        v.addWidget(self.test_progress)
        self.prompt_box = QGroupBox('Acción física del operador')
        pv = QVBoxLayout(self.prompt_box)
        self.prompt_label = label()
        pv.addWidget(self.prompt_label)
        pv.addWidget(button('Acción realizada', self.runner.acknowledge, primary=True))
        self.prompt_box.hide()
        v.addWidget(self.prompt_box)
        manual = QGroupBox('Diagnóstico y calibración · no son interrupciones en vivo')
        grid = QGridLayout(manual)
        self.manual_node = QComboBox()
        self.manual_node.addItems(('A', 'B'))
        grid.addWidget(self.manual_node, 0, 0)
        self.manual_command = QComboBox()
        for title, cmd in (('Leer micrófono', '/mic'), ('Ver mediciones', '/samples'), ('Sonda · 8 rondas', '/probe'),
            ('Identificar · LED encendido', '/identify 1'), ('Identificar · LED apagado', '/identify 0'),
            ('IR encendido · con STOP', '/ir 1'), ('IR apagado · con STOP', '/ir 0'),
            ('Tono encendido · con STOP', '/tone 1'), ('Tono apagado · con STOP', '/tone 0'),
            ('Reloj alto · con STOP', '/clock 1'), ('Reloj bajo · con STOP', '/clock 0')):
            self.manual_command.addItem(title, cmd)
        grid.addWidget(self.manual_command, 0, 1)
        self.manual_execute = button('Ejecutar', lambda: self.guard(self.manual))
        grid.addWidget(self.manual_execute, 0, 2)
        self.threshold = QSpinBox()
        self.threshold.setRange(1, 500)
        self.threshold.setValue(60)
        self.manual_node.currentTextChanged.connect(lambda n: self.threshold.setValue(60 if n == 'A' else 90))
        self.threshold.setToolTip('Flancos en 20 ms para considerar libre el medio antes de solicitar el enlace.')
        grid.addWidget(label('Umbral de actividad de sonido'), 1, 0)
        grid.addWidget(self.threshold, 1, 1)
        grid.addWidget(button('Ajustar umbral', lambda: self.guard(lambda: self.session.send(self.manual_node.currentText(), f'/threshold {self.threshold.value()}'))), 1, 2)
        v.addWidget(manual)
        v.addWidget(label('Para apagar un medio u omitir una frecuencia mientras se envía un mensaje, usa «Interrumpir en vivo…» en la barra inferior.', True))
        return widget

    def make_protocol(self):
        area = QScrollArea()
        area.setWidgetResizable(True)
        content = QWidget()
        area.setWidget(content)
        v = QVBoxLayout(content)
        row = QHBoxLayout()
        row.addWidget(label('Observar K8'))
        self.focus = QComboBox()
        self.focus.addItems(('A', 'B'))
        self.focus.currentIndexChanged.connect(lambda _: setattr(self, 'dirty', True))
        row.addWidget(self.focus)
        row.addStretch()
        self.freeze_view = QCheckBox('Congelar vista')
        self.freeze_view.toggled.connect(lambda _: setattr(self, 'dirty', True))
        row.addWidget(self.freeze_view)
        v.addLayout(row)
        self.overview = label('Esperando datos de la K8…')
        v.addWidget(self.overview)
        self.counters = label('', True)
        v.addWidget(self.counters)
        frame = QGroupBox('Trama observada')
        fv = QVBoxLayout(frame)
        self.frame_bits = label('Control · DATA · CRC · FIELD')
        self.frame_bits.setFont(QFont('Consolas', 13))
        fv.addWidget(self.frame_bits)
        self.frame_meaning = label('Los valores aparecen desde los eventos del firmware.', True)
        self.frame_meaning.setMinimumHeight(65)
        fv.addWidget(self.frame_meaning)
        fv.addWidget(label('SYN 1111 → SFD 0000 → Control 4 → DATA 8 → CRC 8 → FIELD 1010', True))
        v.addWidget(frame)
        primed = QGroupBox('Validación durante la transmisión: bit y primado')
        pr = QVBoxLayout(primed)
        self.primed = QTableWidget(2, 4)
        self.primed.setHorizontalHeaderLabels(('Canal', 'Bit / símbolo', 'Retorno', 'Comprobación'))
        self.primed.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.primed.setFixedHeight(105)
        self.primed.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        pr.addWidget(self.primed)
        self.primed_note = label('El emisor comprueba bit XOR primado = 1; los controles usan estados ACK/NACK.', True)
        pr.addWidget(self.primed_note)
        v.addWidget(primed)
        self.matrix_group = QGroupBox('Matriz de 6 bits + 2 paridades')
        mv = QVBoxLayout(self.matrix_group)
        self.matrix = QTableWidget(2, 4)
        self.matrix.setHorizontalHeaderLabels(('Ronda 1', 'Ronda 2', 'Ronda 3', 'Paridad'))
        self.matrix.setVerticalHeaderLabels(('Fila IR', 'Fila sonido'))
        self.matrix.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.matrix.setFixedHeight(110)
        self.matrix.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        mv.addWidget(self.matrix)
        mv.addWidget(label('pIR = i1 ⊕ s2 ⊕ i3     ·     pSND = s1 ⊕ i2 ⊕ s3', True))
        self.matrix_note = label('Gris: desconocido · verde: recibido/planeado · ámbar: reconstruido por paridad.', True)
        mv.addWidget(self.matrix_note)
        v.addWidget(self.matrix_group)
        sweeps = QGroupBox('Barrido de tres escalones · mediciones reales')
        sv = QVBoxLayout(sweeps)
        selector = QHBoxLayout()
        self.sweep_lane = QComboBox()
        self.sweep_lane.addItems(('IR', 'Sonido'))
        self.sweep_tag = QComboBox()
        self.sweep_tag.addItems(TAGS)
        self.sweep_tag.setCurrentIndex(3)
        self.sweep_lane.currentIndexChanged.connect(lambda _: setattr(self, 'dirty', True))
        self.sweep_tag.currentIndexChanged.connect(lambda _: setattr(self, 'dirty', True))
        selector.addWidget(self.sweep_lane)
        selector.addWidget(self.sweep_tag, 1)
        sv.addLayout(selector)
        self.plot = SweepPlot()
        sv.addWidget(self.plot)
        self.sweep_table = QTableWidget(3, 4)
        self.sweep_table.setHorizontalHeaderLabels(('Hz medidos', 'Flancos', 'f × ventana', 'Validez'))
        self.sweep_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.sweep_table.setFixedHeight(130)
        self.sweep_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        sv.addWidget(self.sweep_table)
        self.sweep_note = label('Cada observación incluye frecuencia, densidad y pendiente.', True)
        sv.addWidget(self.sweep_note)
        v.addWidget(sweeps)
        self.last_round = label('', True)
        v.addWidget(self.last_round)
        v.addStretch()
        return area

    def make_logs(self):
        w = QWidget()
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        self.log_category = QComboBox()
        self.log_category.addItems(('Todo', 'Chat', 'Enlace', 'Trama', 'Ronda', 'Primado', 'CRC', 'Confirmación', 'Matriz', 'Recuperación', 'Canales', 'Velocidad', 'Inyección', 'Prueba', 'Resultado', 'Operador', 'Conexión'))
        self.log_search = QLineEdit()
        self.log_search.setPlaceholderText('Buscar en el registro…')
        row.addWidget(self.log_category)
        row.addWidget(self.log_search, 1)
        self.pause_log = QCheckBox('Pausar desplazamiento')
        row.addWidget(self.pause_log)
        v.addLayout(row)
        self.log_model = LogModel()
        self.log_filter = LogFilter()
        self.log_filter.setSourceModel(self.log_model)
        self.log_table = QTableView()
        self.log_table.setModel(self.log_filter)
        self.log_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.log_table.setAlternatingRowColors(True)
        self.log_table.setWordWrap(False)
        self.log_table.verticalHeader().setDefaultSectionSize(27)
        for column, width in enumerate((85, 35, 110, 95)):
            self.log_table.setColumnWidth(column, width)
        self.log_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.log_table.selectionModel().selectionChanged.connect(self.show_log_detail)
        v.addWidget(self.log_table, 1)
        self.log_detail = QPlainTextEdit()
        self.log_detail.setReadOnly(True)
        self.log_detail.setMaximumHeight(115)
        self.log_detail.setPlaceholderText('Selecciona un evento para ver su explicación y el dato serie original.')
        v.addWidget(self.log_detail)
        row = QHBoxLayout()
        row.addWidget(button('Exportar JSON', lambda: self.guard(self.export_json)))
        row.addWidget(button('Exportar CSV', lambda: self.guard(self.export_csv)))
        row.addWidget(button('Abrir registro', lambda: self.guard(self.open_replay)))
        self.replay_button = button('Reproducir / pausar', self.toggle_replay)
        row.addWidget(self.replay_button)
        row.addWidget(button('Paso', self.replay_step))
        row.addWidget(button('Limpiar vista', self.clear_log_view))
        v.addLayout(row)
        v.addWidget(label('Limpiar o pausar la vista no detiene la comunicación. La exportación conserva eventos y datos serie de la sesión.', True))
        self.log_category.currentTextChanged.connect(self.filter_logs)
        self.log_search.textChanged.connect(self.filter_logs)
        return w

    def mode_changed(self):
        if not hasattr(self, 'cards'):
            return
        dual = self.mode.currentIndex() == 0
        local = 'A' if self.local_node.currentIndex() == 0 else 'B'
        if hasattr(self, 'session') and any(n != local for n in self.session.nodes) and not dual:
            self.mode.blockSignals(True)
            self.mode.setCurrentIndex(0)
            self.mode.blockSignals(False)
            QMessageBox.information(self, 'Conexiones', 'Desconecta la otra K8 antes de cambiar al modo de una placa local.')
            dual = True
        self.local_node.setVisible(not dual)
        for n, card in self.cards.items():
            card['widget'].setVisible((dual or n == local) and not self.expand_protocol.isChecked())
        if hasattr(self, 'sender'):
            self.sender.setEnabled(dual)
            if not dual:
                self.sender.setCurrentIndex(0 if local == 'A' else 1)
                self.manual_node.setCurrentText(local)
                self.focus.setCurrentText(local)
            self.physical.set_local_nodes(('A', 'B') if dual else (local,))
            self.dual_chat.set_local_nodes(('A', 'B') if dual else (local,))
            self.mode_note.setText('Una PC observa A y B: pruebas automáticas completas y recepción verificada en ambos extremos.' if dual else f'Dos PC: esta ventana controla solo {local}. En la otra PC elige {"B" if local == "A" else "A"}, la misma versión, codificación y CRC, y activa el chat. Los mensajes viajan por los medios físicos.')
            self.refresh_connections()

    def set_controls_compact(self, compact):
        self.controls_box.setVisible(not compact)
        self.mode_note.setVisible(not compact)
        dual = self.mode.currentIndex() == 0
        local = 'A' if self.local_node.currentIndex() == 0 else 'B'
        for n, card in self.cards.items():
            card['widget'].setVisible(not compact and (dual or n == local))
        self.expand_protocol.setText('Mostrar controles' if compact else 'Ampliar protocolo')

    def refresh_ports(self):
        available = self.session.available_ports()
        for node, card in self.cards.items():
            if self.session.states[node].connected:
                continue
            old = card['port'].currentData() or self.settings.value('port_' + node, '')
            card['port'].clear()
            for name, desc in available:
                card['port'].addItem(name + ' · ' + desc, name)
            index = card['port'].findData(old)
            if index < 0:
                candidates = [i for i, (_, desc) in enumerate(available) if 'STLink' in desc or 'ST-LINK' in desc]
                index = candidates[0 if node == 'A' else min(1, len(candidates)-1)] if candidates else 0
            card['port'].setCurrentIndex(index)

    def toggle_connection(self, node):
        if self.runner.running:
            raise ValueError('Cancela la prueba antes de cambiar conexiones.')
        if self.replay_timer.isActive():
            self.replay_timer.stop()
            self.replay_queue.clear()
        self.replay_mode = False
        if self.session.states[node].connected:
            self.session.disconnect_board(node)
        else:
            port = self.cards[node]['port'].currentData()
            if not port:
                raise ValueError('Selecciona un puerto COM.')
            self.settings.setValue('port_' + node, port)
            self.physical.history.reset(node)
            self.physical.resume()
            self.session.connect_board(node, port)
        self.refresh_connections()

    def refresh_connections(self):
        if not hasattr(self, 'run_basic'):
            return
        for node, card in self.cards.items():
            s = self.session.states[node]
            card['connect'].setText('Desconectar' if s.connected else 'Conectar')
            card['port'].setEnabled(not s.connected)
        both = set(self.session.ready_nodes) == {'A', 'B'}
        self.run_basic.setEnabled(both and not self.runner.running)
        self.run_demo.setEnabled(both and not self.runner.running)
        self.run_full.setEnabled(both and not self.runner.running)
        self.dual_chat.refresh_controls(self.runner.running, self.replay_mode)
        self.apply_button.setEnabled(bool(self.session.ready_nodes) and not self.runner.running)
        self.manual_execute.setEnabled(bool(self.session.ready_nodes) and not self.runner.running)
        self.refresh_buttons()
        self.dirty = True

    def apply_configuration(self):
        if not self.session.ready_nodes:
            raise ValueError('Conecta e identifica al menos una K8.')
        if self.session.unconfirmed or not all(self.session.states[n].idle for n in self.session.ready_nodes):
            raise ValueError('Espera a que terminen los mensajes antes de cambiar configuración.')
        self.session.set_encoding(self.encoding.currentData())
        for n in self.session.ready_nodes:
            for cmd in ('/stop', '/rate ' + self.rate.currentData(), '/crc ' + str(self.crc.currentIndex()), '/compress ' + str(int(self.compression.isChecked())), '/status'):
                self.session.send(n, cmd)
        self.session.log('Local', 'Configuración', 'Configuración solicitada. Activa el chat después de que las placas la confirmen; en dos PC aplica los mismos valores en la otra ventana.')
        self.count_bytes()

    def control_all(self, command):
        if self.runner.running:
            raise ValueError('La prueba en ejecución controla las placas; cancélala antes de cambiar el estado.')
        if not self.session.ready_nodes:
            raise ValueError('Conecta las K8 que pertenecen a esta ventana.')
        self.session.send_all(command)
        if command == '/start':
            self.session.send_all('/status')
            self.session.log('Local', 'Chat', 'Activación solicitada: esperando la confirmación de cada K8.')

    def stop(self):
        if self.runner.running:
            self.runner.cancel()
        self.session.send_all('/stop')

    def manual(self):
        if self.runner.running:
            raise ValueError('Cancela la prueba antes de enviar controles manuales.')
        n = self.manual_node.currentText()
        if n not in self.session.ready_nodes:
            raise ValueError('Esa K8 no está conectada a esta ventana.')
        command = self.manual_command.currentData()
        if command.startswith(('/ir ', '/tone ', '/clock ', '/identify ')) and self.session.states[n].app.get('RUN') != 0:
            raise ValueError('Este control de diagnóstico requiere Detener. Para alterar una transmisión en marcha utiliza Interrumpir en vivo, que no envía STOP.')
        self.session.send(n, command)

    def show_interference(self):
        self.interference.set_context(self.dual_chat.local_nodes, self.replay_mode)
        self.interference.show()
        self.interference.raise_()
        self.interference.activateWindow()

    def send_chat(self, node=None):
        if self.runner.running:
            raise ValueError('La tanda usa mensajes de prueba. Espera a que termine o cancélala.')
        if self.replay_mode:
            raise ValueError('Esta vista está reproduciendo un registro. Conecta las K8 para volver al chat en vivo.')
        if self.encoding.currentData() != self.session.encoding:
            raise ValueError('Pulsa Aplicar configuración para confirmar la codificación antes de enviar.')
        composer = self.input if node is None else self.dual_chat.panes[node].input
        node = node or ('A' if self.sender.currentIndex() == 0 else 'B')
        if node not in self.dual_chat.local_nodes:
            raise ValueError('Esta ventana solo puede enviar desde su K8 local.')
        inactive = [n for n in self.session.ready_nodes if self.session.states[n].app.get('RUN') != 1]
        if self.session.states[node].app.get('RUN') != 1 or inactive:
            raise ValueError('Falta confirmar la activación de K8 ' + ', '.join(inactive or [node]) + '. Pulsa Activar chat y espera a que indique Chat activo.')
        self.session.queue_message(node, composer.text())
        composer.clear()

    def count_bytes(self):
        for pane in self.dual_chat.panes.values():
            pane.update_bytes()

    def on_entry(self, value):
        self.log_model.append(value)
        if not self.pause_log.isChecked():
            self.log_table.scrollToBottom()

    def filter_logs(self):
        self.log_filter.query = self.log_search.text()
        self.log_filter.category = self.log_category.currentText()
        self.log_filter.beginFilterChange()
        self.log_filter.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def clear_log_view(self):
        self.log_model.clear()
        self.log_detail.clear()

    def show_log_detail(self):
        selected = self.log_table.selectionModel().selectedRows()
        if selected:
            idx = self.log_filter.mapToSource(selected[0])
            item = self.log_model.rows[idx.row()]
            self.log_detail.setPlainText(f'{item.time} · K8 {item.node} · {item.origin}\n{item.text}\n\n{item.raw}')

    def on_event(self, node, event):
        self.physical.consume(node, event)
        self.dual_chat.consume(node, event)
        self.dirty = True

    def render_chat(self):
        self.dual_chat.render()

    def render(self):
        if not self.dirty:
            return
        self.dirty = False
        for node, card in self.cards.items():
            s = self.session.states[node]
            active = {0: 'sin medio validado', 1: 'IR', 2: 'sonido', 3: 'IR + sonido'}[s.active]
            chat_state = 'Chat activo' if s.app.get('RUN') == 1 else 'Chat detenido' if s.app.get('RUN') == 0 else 'Chat sin confirmar'
            card['status'].setText(f'{s.version or "Identificando…"}  BUILD{s.build or "—"} · {chat_state} · {MAC_NAMES.get(s.mac.get("STATE"), "esperando estado")} · salida: {active}\nTX {s.app.get("TX", 0)}  /  RX {s.app.get("RX", 0)}  ·  pendientes {s.app.get("QUEUED", 0)}' if s.connected or self.replay_mode else 'Desconectada · selecciona su puerto COM')
        self.refresh_buttons()
        self.physical.refresh()
        if not self.freeze_view.isChecked():
            self.render_protocol()
        self.footer.setText(('REGISTRO IMPORTADO · ' if self.replay_mode else '') + ('Prueba en ejecución · ' + self.runner.current if self.runner.running else 'Escucha del protocolo') + f' · {len(self.session.entries)} eventos · {len(self.session.raw)} registros serie' + (' · parte del historial fue recortada por el límite de memoria' if self.session.records_truncated else ''))
        faults = [n + ':' + {1:'IR', 2:'sonido', 3:'ambos'}[s.timing['FAULT']] for n, s in self.session.states.items() if s.timing.get('FAULT') in (1,2,3)]
        if faults:
            self.footer.setText(self.footer.text() + ' · Bloqueo software confirmado: ' + ', '.join(faults))

    def refresh_buttons(self):
        both = set(self.session.ready_nodes) == {'A', 'B'}
        local_ready = self.session.ready_nodes
        self.start_button.setText('Chat activo' if local_ready and all(self.session.states[n].app.get('RUN') == 1 for n in local_ready) else 'Activar chat')
        self.start_button.setEnabled(bool(local_ready) and not self.runner.running and not self.replay_mode)
        self.run_basic.setEnabled(both and not self.runner.running and not self.replay_mode)
        self.run_demo.setEnabled(both and not self.runner.running and not self.replay_mode)
        self.run_full.setEnabled(both and not self.runner.running and not self.replay_mode)
        self.run_one.setEnabled(not self.runner.running)
        self.cancel_button.setEnabled(self.runner.running)
        self.dual_chat.refresh_controls(self.runner.running, self.replay_mode)
        self.apply_button.setEnabled(bool(self.session.ready_nodes) and not self.runner.running)
        self.manual_execute.setEnabled(bool(self.session.ready_nodes) and not self.runner.running)
        self.interference.set_context(self.dual_chat.local_nodes, self.replay_mode)
        for b in self.quick_tests:
            b.setEnabled(both and not self.runner.running and not self.replay_mode)
        self.live_cancel.setEnabled(self.runner.running)
        for w in (self.rate, self.crc, self.encoding, self.compression, self.mode, self.local_node):
            w.setEnabled(not self.runner.running)

    def render_protocol(self):
        s = self.session.states[self.focus.currentText()]
        r = s.last_round
        phase = 'REPOSO' if s.mac.get('STATE') == 0 else s.rate.get('PHASE', '—')
        self.overview.setText(f'K8 {s.node} · {MAC_NAMES.get(s.mac.get("STATE"), "sin conexión")} · fase {phase} · {r.get("period_ms", s.timing.get("Q_MS", "—"))} ms/ronda')
        self.counters.setText(f'Paridad: {s.app.get("FEC", 0)} bits · reconstrucciones 2/3: {s.local_events} · CRC inválidos: {s.app.get("BAD", 0)} · reintentos: {s.app.get("RETRY", 0)} · duplicados reconocidos: {s.app.get("DUP", 0)}\nEventos perdidos en K8: {s.hardware.get("EVENT_DROP", 0)} · paquetes no interpretables: {s.malformed_packets}')
        if r:
            for row, name in enumerate(('IR', 'Sonido')):
                bit, reply = r['bits'][row], r['replies'][row]
                verdict = 'Piloto en dos rondas' if r['turbo'] and row == 1 else ('ACK' if reply == 0 else 'NACK / reparar' if reply in (1, 2) else 'Sin confirmar') if r['control'] else f'XOR = {bit ^ reply}' if bit in (0, 1) and reply in (0, 1) else 'No válido'
                values = (name, 'Piloto' if r['turbo'] and row == 1 else str(bit) if bit >= 0 else '?', str(reply) if reply >= 0 else '?', verdict)
                for col, text in enumerate(values):
                    self.primed.setItem(row, col, QTableWidgetItem(text))
            self.primed_note.setText('Retorno observado por el emisor.' if r['sender'] else 'Retorno preparado por el receptor; su llegada se verifica en el emisor.')
        if r and r['real']:
            frame = r['frame']
            visible_bits = frame_bits(r)
            self.frame_bits.setText('   |   '.join((visible_bits[:4], visible_bits[4:12], visible_bits[12:20], visible_bits[20:])))
            view = 'TX planeada' if r['sender'] else 'RX reconstruida hasta este punto'
            complete = r['done'] if r['sender'] else r['frame_mask'] == 15
            self.frame_meaning.setText(f'{view} · CRC {CRC_NAMES[r["crc_kind"]]} · ' +
                (f'{r["frame_type"]}, secuencia {r["frame_seq"]}, DATA 0x{r["data"]:02X}. CRC {r["crc_received"]:02X}, calculado {r["crc_calculated"]:02X}.' if '?' not in visible_bits else
                 'Los ? todavía no han sido aceptados; no se declara un resultado final de CRC.'))
            cells = matrix_cells(r)
            for row in range(2):
                for col in range(4):
                    pos = 2 * col + row
                    fixed = cells[pos]['fixed']
                    seen = cells[pos]['bit'] is not None
                    item = QTableWidgetItem(str(cells[pos]['bit']) if seen else '?')
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setForeground(QColor('#f4c771' if fixed else '#69d8ac' if seen else '#6e8797'))
                    item.setToolTip(('Reconstruido por el firmware' if fixed else 'Planeado para transmitir' if r['sender'] else 'Recibido' if seen else 'No disponible') + f' · posición física {pos}')
                    self.matrix.setItem(row, col, item)
            self.matrix_group.setTitle(f'Matriz · bloque {r["block"] + 1} · {"TX planeada" if r["sender"] else "RX observada"}')
            self.matrix_note.setText('Gris: desconocido · verde: recibido/planeado · ámbar: reconstruido. Las filas son posiciones lógicas; un solo medio puede transportar ambas al redistribuir datos.')
            stage = STAGES[r['stage']] if r['stage'] < len(STAGES) else 'Encabezado inválido'
            self.last_round.setText(f'Ronda {r["round"]} · {stage} · {r["period_ms"]} ms · bits/símbolos {r["bits"]} · primados/estado {r["replies"]}\nLos encabezados de ronda y las respuestas también se representan por barridos.')
        elif r:
            self.frame_bits.setText('SONDA DE CANAL · sin byte de usuario')
            self.frame_meaning.setText('Esta ronda comprueba los medios con pilotos y sus respuestas. No corresponde a una trama DATA del chat.')
            self.matrix_group.setTitle('Sonda de medios · sin matriz de datos de usuario')
            self.matrix.clearContents()
            self.last_round.setText(f'Ronda de sonda {r["round"]} · {r["period_ms"]} ms · pilotos {r["bits"]} · respuestas {r["replies"]}')
        sweep = s.sweeps.get((self.sweep_tag.currentIndex(), self.sweep_lane.currentIndex()))
        self.plot.sweep = sweep
        self.plot.update()
        if sweep:
            for row in range(3):
                expected = sweep['hz'][row] * sweep['windows'][row] / 1000
                values = (str(sweep['hz'][row]), str(sweep['edges'][row]), f'{expected:.1f} en {sweep["windows"][row]} ms', 'válido' if sweep['valid'] & (1 << row) else 'no válido')
                for col, text in enumerate(values):
                    self.sweep_table.setItem(row, col, QTableWidgetItem(text))
            self.sweep_note.setText(f'Banda {"baja ascendente" if sweep["band"] == 0 else "alta descendente"} · símbolo {sweep["symbol"] if sweep["symbol"] >= 0 else "inválido"} · pendiente {sweep["slope"]} Hz/s\n' + ('Reconstruido localmente con dos escalones válidos.' if sweep['reconstructed'] else 'Validación completa.' if sweep['symbol'] >= 0 else 'No se obtuvo un símbolo válido; el protocolo conserva o repara el trabajo.'))

    def run_selected(self):
        selected = self.tests.currentItem()
        key = selected.data(0, Qt.ItemDataRole.UserRole) if selected else None
        if key:
            self.runner.start((key,))
        else:
            raise ValueError('Selecciona una prueba dentro de un grupo.')

    def demonstrate(self, key, chapter):
        if set(self.session.ready_nodes) != {'A', 'B'}:
            raise ValueError('Esta demostración automática necesita ambas K8 en esta PC. Con una K8 local, envía mensajes y observa el protocolo en cada PC.')
        if self.replay_mode:
            raise ValueError('Termina la reproducción y conecta las K8 para ejecutar una demostración.')
        self.tabs.setCurrentWidget(self.physical)
        self.expand_protocol.setChecked(True)
        self.physical.node.setCurrentText('A' if key == 'sound_a' else 'B')
        self.physical.resume()
        self.physical.chapters.setCurrentIndex(chapter)
        self.runner.start((key,))

    def update_tests(self):
        self.encoding.setCurrentIndex(self.encoding.findData(self.session.encoding))
        for key, result in self.runner.results.items():
            item = self.test_items[key]
            text = {'running': 'En curso', 'passed': 'PASA', 'failed': 'INCOMPLETA', 'cancelled': 'Cancelada'}[result['status']]
            if result.get('manual_interventions'):
                text += ' · manual'
            item.setText(2, text)
            item.setForeground(2, QColor('#6bd9ab' if result['status'] == 'passed' else '#f3b977' if result['status'] in ('running', 'cancelled') else '#f18e9a'))
            item.setToolTip(2, result.get('reason', '') + '\n' + result.get('origin', ''))
        self.progress.setRange(0, 0 if self.runner.running else 1)
        status = self.runner.results.get(self.runner.current, {}).get('status')
        self.progress.setValue(1 if status == 'passed' and not self.runner.running else 0)
        self.progress.setFormat('En ejecución' if self.runner.running else 'Finalizado' if status == 'passed' else 'Cancelada' if status == 'cancelled' else 'Prueba incompleta' if status == 'failed' else 'Pendiente')
        elapsed = int(time.monotonic() - self.runner.started) if self.runner.running else 0
        self.test_progress.setText((f'{elapsed // 60:02d}:{elapsed % 60:02d} · ' if self.runner.running else '') + self.runner.progress)
        origin = self.runner.results.get(self.runner.current, {}).get('origin', '')
        self.live_progress.setText(self.test_progress.text() + (' · ' + origin if origin else ''))
        self.refresh_buttons()
        self.dirty = True

    def show_prompt(self, text):
        self.prompt_box.setVisible(bool(text))
        self.prompt_label.setText(text)
        if text:
            self.tabs.setCurrentIndex(2)

    def export_json(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Guardar sesión completa', 'cc8_sesion.json', 'Sesión JSON (*.json)')
        if path:
            export_session(path, self.session.entries, self.session.raw, self.session.results, self.session.records_truncated)
            self.session.log('Local', 'Archivo', 'Sesión guardada en ' + path)

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Guardar registro legible', 'cc8_registro.csv', 'CSV (*.csv)')
        if path:
            with open(path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(('Hora', 'K8', 'Origen', 'Evento', 'Nivel', 'Explicación', 'Dato serie'))
                writer.writerows((e.time, e.node, e.origin, e.category, e.severity, e.text, e.raw) for e in self.session.entries)

    def open_replay(self):
        if self.session.nodes or self.runner.running:
            raise ValueError('Desconecta las K8 antes de reproducir un archivo. La reproducción es una vista separada de la comunicación en vivo.')
        path, _ = QFileDialog.getOpenFileName(self, 'Abrir sesión o registro de pruebas', '', 'Registros (*.json *.jsonl)')
        if not path:
            return
        events = []
        if path.endswith('.jsonl'):
            chunks = {'A': '', 'B': ''}
            for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
                record = json.loads(line)
                node = record.get('node')
                if record.get('kind') == 'RX' and node in chunks:
                    chunks[node] += record['text']
                    while '\n' in chunks[node]:
                        first, chunks[node] = chunks[node].split('\n', 1)
                        events.append((node, first.rstrip('\r'), record.get('utc')))
        else:
            data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
            if data.get('format') == 'cc8-session-1':
                events = [(r['node'], r['text'], r.get('time')) for r in data.get('raw', []) if r.get('direction') == 'RX' and r['node'] in ('A', 'B')]
            elif 'history' in data:
                for node in ('A', 'B'):
                    events.extend((node, line) for line in data['history'].get(node, '').splitlines())
                self.session.log('Archivo', 'Reproducción', 'El resumen contiene historiales separados por placa; no permite reconstruir el intercalado temporal original.', 'warning', 'archivo importado')
            elif 'passed' in data:
                self.session.log('Archivo', 'Evidencia importada', f"Resultado guardado: {data.get('passed')}. Alcance: {data.get('scope', 'modelo o prueba anterior')}. No se ha ejecutado nuevamente.", origin='archivo importado', raw=json.dumps(data, ensure_ascii=False))
                return
        if not events:
            raise ValueError('No hay líneas serie reproducibles en ese archivo.')
        self.session.states = {n: BoardState(n) for n in ('A', 'B')}
        self.physical.history.reset()
        self.physical.resume()
        self.session.sent = {'A': deque(), 'B': deque()}
        self.dual_chat.history.clear()
        self.dual_chat.render()
        self.replay_queue = deque(events)
        self.replay_mode = True
        self.session.log('Archivo', 'Reproducción', f'{len(events)} líneas importadas. Reproducción acelerada; las marcas de la K8 se conservan en cada evento.', origin='archivo importado')
        self.replay_timer.start()
        self.dirty = True

    def replay_tick(self):
        for _ in range(4):
            if not self.replay_queue:
                self.replay_timer.stop()
                return
            node, line, *stamp = self.replay_queue.popleft()
            self.session.receive(node, line, origin='archivo importado', recorded_time=stamp[0] if stamp else None)

    def toggle_replay(self):
        if self.replay_timer.isActive():
            self.replay_timer.stop()
        elif self.replay_queue:
            self.replay_timer.start()

    def replay_step(self):
        self.replay_timer.stop()
        if self.replay_queue:
            node, line, *stamp = self.replay_queue.popleft()
            self.session.receive(node, line, origin='archivo importado', recorded_time=stamp[0] if stamp else None)
            self.dirty = True
            self.render()

    def closeEvent(self, event):
        self.runner.cancel()
        self.session.close()
        self.web.close()
        event.accept()


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    load_fonts()
    app.setApplicationName('CC8')
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    window = Window()
    window.show()
    return app.exec()


def load_fonts():
    for filename in ('segoeui.ttf', 'consola.ttf', 'seguisym.ttf', 'seguiemj.ttf'):
        path = Path('C:/Windows/Fonts') / filename
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))


if __name__ == '__main__':
    sys.exit(main())
