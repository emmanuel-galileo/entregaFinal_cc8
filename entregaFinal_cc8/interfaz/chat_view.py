"""Dos perspectivas del chat y entrada accesible de símbolos ya soportados."""
from __future__ import annotations

import html
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout,
    QSplitter, QTextBrowser, QLineEdit, QPushButton, QComboBox, QDialog, QTabWidget, QGridLayout)
from .chat_model import ChatHistory, TEXT_SAMPLES, PALETTES, representable


class SymbolPicker(QDialog):
    picked = Signal(str)

    def __init__(self, encoding, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Emojis y símbolos')
        self.resize(460, 350)
        v = QVBoxLayout(self)
        tip = QLabel('Selecciona un símbolo para insertarlo en el borrador. Después pulsa Enviar.'
            + ('\nLos emojis requieren UTF-8; CP1252 solo admite sus propios caracteres.' if encoding == 'cp1252' else ''))
        tip.setWordWrap(True)
        v.addWidget(tip)
        tabs = QTabWidget()
        v.addWidget(tabs, 1)
        self.symbol_buttons = {}
        for title, chars in PALETTES.items():
            page = QWidget()
            grid = QGridLayout(page)
            for i, char in enumerate(chars):
                b = QPushButton(char)
                b.setFont(QFont('Segoe UI Emoji', 22))
                b.setStyleSheet('font-family:"Segoe UI Emoji";font-size:24px;')
                b.setMinimumSize(56, 54)
                allowed = representable(char, encoding)
                b.setEnabled(allowed)
                encoded = char.encode('utf-8')
                b.setToolTip(f'{char} · UTF-8: {len(encoded)} bytes · {encoded.hex(" ").upper()}'
                    + (' · requiere UTF-8 en esta aplicación' if not allowed else ''))
                b.clicked.connect(lambda checked=False, c=char: self.choose(c))
                self.symbol_buttons[char] = b
                grid.addWidget(b, i//6, i%6)
            tabs.addTab(page, title)
        close = QPushButton('Cerrar')
        close.clicked.connect(self.accept)
        v.addWidget(close)

    def choose(self, value):
        self.picked.emit(value)
        self.accept()


class ChatPane(QFrame):
    send_requested = Signal(str)

    def __init__(self, node, encoding):
        super().__init__()
        self.node, self.get_encoding = node, encoding
        self.setObjectName('card')
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 7, 8, 7)
        v.setSpacing(5)
        top = QHBoxLayout()
        title = QLabel(f'K8 {node}  →  {"B" if node == "A" else "A"}')
        title.setObjectName('section')
        top.addWidget(title)
        self.state = QLabel('Sin conexión')
        self.state.setObjectName('muted')
        top.addWidget(self.state, 1, Qt.AlignmentFlag.AlignRight)
        v.addLayout(top)
        self.chat = QTextBrowser()
        self.chat.setOpenExternalLinks(False)
        self.chat.setMinimumHeight(65)
        self.chat.setStyleSheet('QTextBrowser {background:#0b171f;padding:6px;}')
        v.addWidget(self.chat, 1)
        compose = QHBoxLayout()
        compose.setSpacing(5)
        self.input = QLineEdit()
        self.input.setPlaceholderText('Escribir desde ' + node + '…')
        self.input.setMinimumWidth(80)
        self.input.returnPressed.connect(lambda: self.send_requested.emit(node))
        self.input.textChanged.connect(self.update_bytes)
        compose.addWidget(self.input, 1)
        self.picker = QPushButton('Emoji')
        self.picker.setToolTip('Insertar emojis, signos o letras especiales')
        self.picker.clicked.connect(self.open_picker)
        compose.addWidget(self.picker)
        self.send = QPushButton('Enviar')
        self.send.setObjectName('primary')
        self.send.clicked.connect(lambda: self.send_requested.emit(node))
        compose.addWidget(self.send)
        v.addLayout(compose)
        samples = QHBoxLayout()
        samples.setSpacing(5)
        self.sample = QComboBox()
        self.sample.setMinimumWidth(90)
        for key, title, value in TEXT_SAMPLES:
            self.sample.addItem(title, value)
        self.sample.setToolTip('Selecciona un ejemplo y pulsa Cargar; luego Enviar. No se transmite automáticamente.')
        samples.addWidget(self.sample, 1)
        self.load = QPushButton('Cargar')
        self.load.setToolTip('Reemplaza el borrador por el ejemplo seleccionado; no envía todavía.')
        self.load.clicked.connect(self.load_sample)
        self.sample.currentIndexChanged.connect(lambda: self.load.setEnabled(representable(self.sample.currentData(), self.get_encoding())))
        samples.addWidget(self.load)
        self.count = QLabel('0 / 185 B')
        self.count.setObjectName('muted')
        samples.addWidget(self.count)
        v.addLayout(samples)
        self.update_bytes()

    def load_sample(self):
        self.input.setText(self.sample.currentData())
        self.input.setFocus()

    def open_picker(self):
        dialog = SymbolPicker(self.get_encoding(), self)
        dialog.picked.connect(self.input.insert)
        dialog.exec()
        self.input.setFocus()

    def update_bytes(self):
        encoding = self.get_encoding()
        for i, (_, _, value) in enumerate(TEXT_SAMPLES):
            self.sample.model().item(i).setEnabled(representable(value, encoding))
        self.load.setEnabled(representable(self.sample.currentData(), encoding))
        try:
            raw = self.input.text().encode(encoding, errors='strict')
            self.count.setText(f'{len(raw)} / 185 B')
            self.count.setStyleSheet('color:#ff8b96' if len(raw)>185 else 'color:#93aab9')
            self.count.setToolTip(f'{encoding} · {len(raw)} byte(s)\n' + raw.hex(' ').upper()
                + '\nUn carácter UTF-8 puede ocupar varios bytes DATA.')
        except UnicodeEncodeError:
            self.count.setText('Requiere UTF-8')
            self.count.setStyleSheet('color:#ff8b96')
            self.count.setToolTip('El borrador contiene un carácter que CP1252 no puede representar.')

    def render(self, rows):
        parts = []
        if not rows:
            parts.append('<p style="color:#829eae;text-align:center">Tu conversación desde K8 ' + self.node
                + '.<br>La recepción aparece cuando esta tarjeta entrega el mensaje.</p>')
        for row in rows:
            m, outgoing = row['item'], row['outgoing']
            status = (m.get('error') or ('Recibido en el otro extremo' if m.get('received') else
                'Tramas confirmadas' if m.get('confirmed') else 'En cola / transmitiendo')) if outgoing else 'Recibido por esta K8'
            peer = 'B' if self.node == 'A' else 'A'
            author = 'Tú (' + self.node + ') → ' + peer if outgoing else peer + ' → Tú (' + self.node + ')'
            if row['source'] == 'archivo importado':
                status += ' · archivo importado'
            value = html.escape(m['text']) if m['text'] else '<i>Mensaje vacío</i>'
            color, align = ('#145746', 'right') if outgoing else ('#263c4b', 'left')
            parts.append(f'<div align="{align}"><table width="90%" cellpadding="7" style="background:{color};margin:5px"><tr><td>'
                f'<span style="color:#9bd6cc;font-size:10px">{author}</span><br>'
                f'<span style="font-size:16px;color:#eff9f7">{value}</span><br>'
                f'<span style="color:#adcacb;font-size:10px">{row["time"]} · {html.escape(status)}</span></td></tr></table></div>')
        bar = self.chat.verticalScrollBar()
        follow = bar.value() >= bar.maximum()-15
        old = bar.value()
        self.chat.setHtml(''.join(parts))
        bar.setValue(bar.maximum() if follow else min(old, bar.maximum()))


class DualChat(QWidget):
    def __init__(self, session, encoding, send):
        super().__init__()
        self.session = session
        self.history = ChatHistory()
        self.local_nodes = ('A', 'B')
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 8, 0)
        v.setSpacing(5)
        self.split = QSplitter(Qt.Orientation.Vertical)
        self.panes = {}
        for node in 'AB':
            pane = ChatPane(node, encoding)
            pane.send_requested.connect(send)
            self.panes[node] = pane
            self.split.addWidget(pane)
            self.split.setCollapsible(0 if node == 'A' else 1, False)
        v.addWidget(self.split, 1)
        self.note = QLabel('Cada chat muestra lo observado en su K8. Cargar un ejemplo solo prepara el borrador.')
        self.note.setObjectName('muted')
        self.note.setWordWrap(True)
        v.addWidget(self.note)
        self.render()

    def set_local_nodes(self, nodes):
        self.local_nodes = tuple(nodes)
        for n, pane in self.panes.items():
            pane.setVisible(n in nodes)
        self.note.setText('Cada chat muestra lo observado en su K8. Cargar un ejemplo solo prepara el borrador.' if len(nodes)==2 else
            'Chat de tu K8 local. La otra PC presenta el chat del otro extremo.')

    def consume(self, node, event):
        if self.history.consume(node, event):
            self.render()

    def render(self):
        for n, pane in self.panes.items():
            pane.render(self.history.rows[n])

    def refresh_controls(self, busy=False, replay=False):
        inactive = any(self.session.states[n].app.get('RUN') != 1 for n in self.session.ready_nodes)
        for n, pane in self.panes.items():
            s = self.session.states[n]
            pane.send.setEnabled(n in self.local_nodes and s.ready and not inactive and not busy and not replay)
            pane.state.setText('Registro importado' if replay else 'Prueba en curso' if busy else
                'Chat activo' if s.ready and s.app.get('RUN')==1 else 'Activar chat' if s.ready else 'Sin conexión')
