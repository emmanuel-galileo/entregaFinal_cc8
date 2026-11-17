"""Controles de las inyecciones existentes, utilizables sin detener el chat."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QCheckBox, QComboBox, QPushButton)

MASK_NAMES = {0: 'ninguno', 1: 'IR', 2: 'sonido', 3: 'IR y sonido'}
ONE_SHOTS = (
    ('Omitir un escalón una vez', 'notch'),
    ('Dejar en silencio DATOS de una ronda', 'erase'),
    ('Invertir bits una vez', 'flip'),
    ('Alterar CRC del próximo byte que se prepare', 'badcrc'),
    ('Omitir el próximo ACK', 'dropack'),
)


def note(value):
    w = QLabel(value)
    w.setWordWrap(True)
    return w


class InterferencePanel(QDialog):
    def __init__(self, session, intervention, parent=None):
        super().__init__(parent)
        self.session = session
        self.intervention = intervention
        self.local_nodes = ('A', 'B')
        self.replay = False
        self.pending_fault = {}
        self.pending_once = {}
        self.setWindowTitle('Interrupciones en vivo · por software')
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.resize(700, 650)
        self.setMinimumWidth(680)
        v = QVBoxLayout(self)
        v.addWidget(note('Envía un mensaje y usa estos controles mientras avanza. No mandan STOP ni cambian el reloj. Afectan las salidas físicas mediante órdenes de software.'))
        row = QHBoxLayout()
        row.addWidget(note('Emisores que quieres alterar'))
        self.node = QComboBox()
        self.node.addItem('A → B · LED y buzzer de A', 'A')
        self.node.addItem('B → A · LED y buzzer de B', 'B')
        self.node.currentIndexChanged.connect(self.refresh)
        row.addWidget(self.node, 1)
        v.addLayout(row)
        persistent = QGroupBox('Bloqueo sostenido · permanece hasta que lo restaures')
        persistent.setMinimumHeight(145)
        pv = QVBoxLayout(persistent)
        row = QHBoxLayout()
        self.ir = QCheckBox('Apagar IR')
        self.sound = QCheckBox('Silenciar buzzer')
        self.ir.clicked.connect(self.apply_checks)
        self.sound.clicked.connect(self.apply_checks)
        row.addWidget(self.ir)
        row.addWidget(self.sound)
        self.restore = QPushButton('Restaurar IR + sonido')
        self.restore.setObjectName('primary')
        self.restore.clicked.connect(lambda: self.set_fault(0))
        row.addWidget(self.restore)
        pv.addLayout(row)
        self.confirmation = note('Sin estado confirmado de la K8.')
        pv.addWidget(self.confirmation)
        pv.addWidget(note('Restaurar permite volver a emitir. El protocolo reincorpora el canal tras tres pilotos correctos.'))
        v.addWidget(persistent)
        punctual = QGroupBox('Fallo puntual · la transmisión continúa')
        punctual.setMinimumHeight(220)
        qv = QVBoxLayout(punctual)
        self.action = QComboBox()
        for title, key in ONE_SHOTS:
            self.action.addItem(title, key)
        self.action.currentIndexChanged.connect(self.refresh_options)
        qv.addWidget(self.action)
        row = QHBoxLayout()
        self.channel = QComboBox()
        for title, mask in (('IR', 1), ('Sonido', 2), ('Ambos medios', 3)):
            self.channel.addItem(title, mask)
        self.channel.setCurrentIndex(1)
        row.addWidget(self.channel, 1)
        self.step = QComboBox()
        for i, title in enumerate(('Primera frecuencia', 'Segunda frecuencia', 'Tercera frecuencia')):
            self.step.addItem(title, i)
        self.step.setCurrentIndex(1)
        row.addWidget(self.step, 1)
        self.arm = QPushButton('Aplicar una vez')
        self.arm.clicked.connect(self.apply_once)
        row.addWidget(self.arm)
        qv.addLayout(row)
        self.explanation = note('')
        self.explanation.setMinimumHeight(42)
        qv.addWidget(self.explanation)
        self.feedback = note('La K8 confirma la orden y los eventos de ronda muestran cuándo se aplica.')
        self.feedback.setMinimumHeight(30)
        qv.addWidget(self.feedback)
        v.addWidget(punctual)
        self.test_note = note('Si intervienes una prueba automática, queda registrada como prueba con intervención manual. Sus pasos pueden restaurar las salidas al avanzar o terminar.')
        v.addWidget(self.test_note)
        v.addWidget(note('Para la demostración de interferencia totalmente física utiliza el switch o el ruido del teléfono. Estos botones son inyecciones por software.'))
        close = QPushButton('Cerrar panel · el bloqueo conserva su estado')
        close.clicked.connect(self.close)
        v.addWidget(close)
        self.session.event.connect(self.observe)
        self.session.connected.connect(self.connection_changed)
        self.refresh_options()
        self.refresh()

    def connection_changed(self, node, connected):
        self.pending_fault.pop(node, None)
        self.pending_once.pop(node, None)
        self.refresh()

    def set_context(self, nodes, replay=False):
        self.local_nodes, self.replay = tuple(nodes), replay
        if self.node.currentData() not in nodes:
            self.node.setCurrentIndex(self.node.findData(nodes[0]))
        self.node.setEnabled(len(nodes)>1)
        self.refresh()

    def send(self, command):
        n = self.node.currentData()
        if self.replay:
            raise ValueError('Un registro importado no controla las tarjetas. Conecta las K8 para intervenir en vivo.')
        if n not in self.local_nodes or n not in self.session.ready_nodes:
            raise ValueError('Conecta la K8 seleccionada a esta aplicación.')
        self.session.send(n, command, origin='software')
        self.intervention(n, command)
        return n

    def apply_checks(self):
        self.set_fault(int(self.ir.isChecked()) | (int(self.sound.isChecked()) << 1))

    def set_fault(self, mask):
        try:
            n = self.send('/fault ' + str(mask))
            self.pending_fault[n] = mask
            self.refresh()
        except (ValueError, OSError) as exc:
            self.confirmation.setText(str(exc))

    def apply_once(self):
        action, mask = self.action.currentData(), self.channel.currentData()
        command = f'/notch {self.step.currentData()} {mask}' if action == 'notch' else (
            f'/{action} {mask}' if action in ('erase', 'flip') else '/' + action)
        try:
            n = self.send(command)
            self.pending_once[n] = {'action': action, 'mask': mask, 'accepted': False}
            self.feedback.setText(f'{n}: orden enviada; esperando confirmación de la K8. {command}')
        except (ValueError, OSError) as exc:
            self.feedback.setText(str(exc))

    def refresh_options(self):
        action = self.action.currentData()
        self.step.setVisible(action == 'notch')
        self.channel.setVisible(action in ('notch', 'erase', 'flip'))
        explanations = {
            'notch': 'En el próximo envío de una trama de esta K8, omite una frecuencia de la fase DATOS de una ronda (también puede ser una ronda de control). Observa el rescate 2/3 en Barridos del receptor.',
            'erase': 'Deja en silencio la fase DATOS de una ronda, en el medio elegido. Si buscas recuperar datos con la matriz, aplícalo después de BEGIN, cuando avance una ronda DATOS.',
            'flip': 'Altera el símbolo de la fase DATOS de una ronda. Los primados y la matriz permiten observar la detección y la reparación.',
            'badcrc': 'Se arma para el próximo byte que el programa prepare. No modifica retroactivamente un CRC ya enviado; puede aplicarse en el siguiente mensaje.',
            'dropack': 'Omite una confirmación de bloque de esta K8. El emisor debe detectar su ausencia y reintentar.',
        }
        self.explanation.setText(explanations.get(action, ''))

    def refresh(self):
        n = self.node.currentData()
        s = self.session.states[n]
        enabled = n in self.local_nodes and n in self.session.ready_nodes and not self.replay
        for w in (self.ir, self.sound, self.restore, self.arm):
            w.setEnabled(enabled)
        actual = s.timing.get('FAULT')
        requested = self.pending_fault.get(n)
        mask = requested if requested is not None else actual or 0
        for w, bit in ((self.ir, 1), (self.sound, 2)):
            w.blockSignals(True)
            w.setChecked(bool(mask & bit))
            w.blockSignals(False)
        self.confirmation.setText('Registro importado: los controles están desactivados.' if self.replay else
            f'{n}: solicitado bloquear {MASK_NAMES[requested]}; esperando estado de la K8.' if requested is not None else
            f'{n}: bloqueo confirmado por la K8: {MASK_NAMES[actual]}.' if actual is not None and s.ready else 'Sin estado confirmado de la K8.')
        if s.ready and s.app.get('RUN') != 1 and not self.replay:
            self.confirmation.setText(self.confirmation.text() + ' Chat detenido: queda preparado para próximos envíos; no controla el tono fijo de diagnóstico.')

    def observe(self, node, event):
        line = event.get('line', '')
        if event['kind'] == 'reboot':
            self.pending_fault.pop(node, None)
            self.pending_once.pop(node, None)
        if line.startswith('TIMING PROFILE='):
            if self.session.states[node].timing.get('FAULT') == self.pending_fault.get(node):
                self.pending_fault.pop(node, None)
            if self.node.currentData() == node:
                self.refresh()
        pending = self.pending_once.get(node)
        if not pending:
            return
        armed = {'notch': 'NOTCH_ARMED', 'erase': 'ERASE_ARMED', 'flip': 'FLIP_ARMED',
                 'badcrc': 'BADCRC_ARMED', 'dropack': 'DROP_ACK_ARMED'}[pending['action']]
        if line.endswith(armed):
            pending['accepted'] = True
            if self.node.currentData() == node:
                self.feedback.setText(f'{node}: orden aceptada y armada. Se aplicará en la siguiente ocasión correspondiente, sin detener el mensaje.')
        key = {'notch': 'notch', 'erase': 'erased', 'flip': 'flipped'}.get(pending['action'])
        if key and event['kind'] == 'round' and event['sender'] and event.get(key, 0) & pending['mask']:
            if self.node.currentData() == node:
                self.feedback.setText(f'{node}: inyección aplicada en la ronda {event["round"]}. Observa los barridos y la recuperación en la K8 receptora.')
            self.pending_once.pop(node, None)
