"""Interpretación de eventos; no transmite mensajes entre equipos."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
import json
import re
from typing import Any

CRC_NAMES = ('SMBUS', 'AUTOSAR', 'SAE-J1850', 'MAXIM-DOW')
FRAME_TYPES = ('INICIO', 'CONTINUACIÓN', 'FIN', 'ÚNICA')
STAGES = ('INICIO DE BLOQUE', 'DATOS', 'COMPROBACIÓN', 'SOLICITUD DE REPARACIÓN', 'BIT DE REPARACIÓN')
TAGS = ('SYN / SFD', 'ENCABEZADO 1', 'ENCABEZADO 2', 'DATOS', 'PRIMADO', 'SONDA PILOTO')
PROFILES = {'log': 0, 'max': 1, '1': 2, '0.5': 3}
MAC_NAMES = {0: 'En escucha', 1: 'Esperando turno', 2: 'Solicitando enlace', 3: 'Esperando aceptación',
             4: 'Recibiendo SYN', 5: 'Aceptando enlace', 6: 'Esperando datos', 7: 'Transmitiendo',
             8: 'Recibiendo', 9: 'Liberando turno'}
HS_NAMES = {'READY': 'Escucha pasiva', 'SYN_TX': 'Solicita transmitir: SYN', 'SYN_RX': 'Detectó una solicitud',
            'FIRST_EDGE_WIN': 'Ganó por el primer flanco', 'TIE_WIN_A': 'A ganó el desempate',
            'TIE_YIELD_B': 'B cedió el turno', 'SYN_ACK_TX': 'Acepta recibir: SYN-ACK',
            'ESTABLISHED': 'Enlace establecido', 'TIMEOUT': 'No hubo respuesta a tiempo',
            'REJECT': 'Barrido de inicio rechazado', 'RELEASE': 'Libera el turno',
            'BUSY_BACKOFF': 'Medio ocupado: espera antes de solicitar'}


def crc8(kind: int, data: bytes) -> int:
    poly = (0x07, 0x2F, 0x1D, 0x8C)[kind]
    crc = 255 if kind in (1, 2) else 0
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = ((crc >> 1) ^ (poly if crc & 1 else 0)) if kind == 3 else (
                (crc << 1) ^ (poly if crc & 128 else 0)) & 255
    return crc ^ (255 if kind in (1, 2) else 0)


def matrix_word(data: int) -> int:
    word = sum(((data >> (5 - n)) & 1) << p for n, p in enumerate((0, 3, 4, 5, 2, 1)))
    return word | (((word ^ (word >> 3) ^ (word >> 4)) & 1) << 6) | (
        (((word >> 1) ^ (word >> 2) ^ (word >> 5)) & 1) << 7)


def fields(line: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in re.findall(r'([A-Za-z_][A-Za-z_0-9]*)=([^\s]+)', line):
        result[key.upper()] = int(value) if re.fullmatch(r'-?\d+', value) else value
    return result


def decode_packet(line: str) -> dict[str, Any]:
    payload = line.removeprefix('@CC8 ').strip()
    if not re.fullmatch(r'[0-9A-Fa-f]{96}', payload):
        raise ValueError('Evento incompleto o mal formado')
    w = [int(payload[i:i + 8], 16) for i in range(0, 96, 8)]
    if w[11] >> 28 != 1:
        raise ValueError('Formato de evento no compatible')
    event: dict[str, Any] = {'tick': w[1], 'packet': payload, 'origin': 'firmware'}
    if w[0] & 255 == 1:
        event.update(kind='sweep', tag=(w[0] >> 8) & 255, lane=(w[0] >> 16) & 1,
                     band=(w[0] >> 17) & 1, turbo=bool(w[0] & (1 << 18)),
                     reconstructed=bool(w[0] & (1 << 19)), valid=(w[0] >> 20) & 7,
                     reason=(w[0] >> 24) & 255,
                     hz=[w[n] & 65535 for n in (2, 3, 4)],
                     edges=[w[n] >> 16 for n in (2, 3, 4)],
                     windows=[w[5] & 65535, w[5] >> 16, w[6] & 65535],
                     symbol=(w[6] >> 16) - 1,
                     slope=w[7] - (1 << 32) if w[7] & (1 << 31) else w[7],
                     round=w[8])
    elif w[0] & 255 == 2:
        sender = bool(w[0] & (1 << 8))
        event.update(kind='round', sender=sender, control=bool(w[0] & (1 << 9)),
                     turbo=bool(w[0] & (1 << 10)), active=(w[0] >> 11) & 3,
                     real=bool(w[0] & (1 << 13)), sequence=(w[0] >> 14) & 1,
                     done=bool(w[0] & (1 << 15)), stage=(w[0] >> 16) & 15,
                     mask=(w[0] >> 20) & 3, block=(w[0] >> 24) & 3,
                     crc_kind=(w[0] >> 28) & 3, round=w[2], frame=w[3] & 0xFFFFFF,
                     known=w[4] & 255, values=(w[4] >> 8) & 255,
                     fixed=(w[4] >> 16) & 255, frame_mask=w[4] >> 24,
                     bits=[(w[5] & 255) - (not sender), ((w[5] >> 8) & 255) - (not sender)],
                     replies=[(w[6] & 255) - 1, ((w[6] >> 8) & 255) - 1],
                     indices=[(w[6] >> 16) & 255, w[6] >> 24],
                     step_ms=w[7] & 65535, period_ms=w[7] >> 16,
                     fec=w[8], bad=w[9], byte_count=w[10],
                     headers=[w[11] & 255, (w[11] >> 8) & 255],
                     erased=(w[11] >> 16) & 3, flipped=(w[11] >> 18) & 3,
                     notch=(w[11] >> 20) & 3, notch_step=(w[11] >> 24) & 15)
        frame = event['frame']
        control, data = (frame >> 20) & 15, (frame >> 12) & 255
        event.update(frame_type=FRAME_TYPES[control >> 2], frame_seq=control & 3,
                     data=data, crc_received=(frame >> 4) & 255,
                     crc_calculated=crc8(event['crc_kind'], bytes((control, data))), field=frame & 15)
    else:
        raise ValueError('Tipo de evento desconocido')
    return event


@dataclass
class LogEntry:
    node: str
    category: str
    text: str
    severity: str = 'info'
    origin: str = 'observado'
    raw: str = ''
    time: str = field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec='milliseconds'))


@dataclass
class BoardState:
    node: str
    connected: bool = False
    ready: bool = False
    version: str = ''
    build: int = 0
    app: dict = field(default_factory=dict)
    hardware: dict = field(default_factory=dict)
    timing: dict = field(default_factory=dict)
    mac: dict = field(default_factory=dict)
    local: dict = field(default_factory=dict)
    clock: dict = field(default_factory=dict)
    rate: dict = field(default_factory=dict)
    last_round: dict = field(default_factory=dict)
    sweeps: dict = field(default_factory=dict)
    messages: deque = field(default_factory=lambda: deque(maxlen=1000))
    rounds: deque = field(default_factory=lambda: deque(maxlen=2000))
    local_events: int = 0
    received_packets: int = 0
    malformed_packets: int = 0
    event_format: int = 0
    quiet_mic: int | None = None
    mic: int | None = None
    last_hs: tuple = ()
    seen_frames: set = field(default_factory=set)

    @property
    def idle(self) -> bool:
        return self.ready and self.app.get('QUEUED', 1) == 0 and self.app.get('PENDING', 1) == 0 and self.mac.get('STATE') == 0

    @property
    def active(self) -> int:
        return self.app.get('ACTIVE', 0)

    def consume(self, raw: str) -> tuple[dict, list[LogEntry]]:
        line = re.sub(r'^\[[AB?]\]\s*', '', raw).rstrip('\r\n')
        entries: list[LogEntry] = []
        event: dict = {'kind': 'line', 'line': line}
        if line.startswith('@CC8 '):
            try:
                event = decode_packet(line)
            except ValueError as exc:
                self.malformed_packets += 1
                return {'kind': 'malformed'}, [LogEntry(self.node, 'Registro', str(exc), 'warning', raw=raw)]
            self.received_packets += 1
            if event['kind'] == 'sweep':
                self.sweeps[(event['tag'], event['lane'])] = event
                if event['reconstructed']:
                    self.local_events += 1
                    entries.append(LogEntry(self.node, 'Recuperación',
                        f"{'IR' if event['lane'] == 0 else 'Sonido'}: reconstruyó el símbolo {event['symbol']} con 2 de 3 escalones.", 'success', raw=raw))
            else:
                previous = self.last_round
                self.last_round = event
                self.rounds.append(event)
                self.app['ACTIVE'] = event['active'] if event['sender'] else self.app.get('ACTIVE', event['active'])
                self.app['TX' if event['sender'] else 'RX'] = event['byte_count']
                self.app.update(FEC=event['fec'], BAD=event['bad'])
                stage = STAGES[event['stage']] if event['stage'] < len(STAGES) else 'ENCABEZADO INVÁLIDO'
                direction = 'TX' if event['sender'] else 'RX'
                bits = ' · '.join('sonido: sonda en dos rondas' if event['turbo'] and lane == 1 else f'{name}: {value if value >= 0 else "inválido"}' for lane, (name, value) in enumerate(zip(('IR', 'sonido'), event['bits'])))
                entries.append(LogEntry(self.node, 'Ronda', f"Ronda {event['round']} · {direction} · bloque {event['block'] + 1} · {stage}. {bits}.", raw=raw))
                if event['real'] and not event['control']:
                    parts = []
                    for lane, name in enumerate(('IR', 'sonido')):
                        if event['turbo'] and lane == 1:
                            parts.append('Sonido: piloto y retorno abarcan dos rondas')
                            continue
                        bit, reply = event['bits'][lane], event['replies'][lane]
                        if bit in (0, 1) and reply in (0, 1):
                            verb = 'recibió' if event['sender'] else 'preparó para devolver'
                            parts.append(f"{name}: bit {bit}; {verb} primado {reply}; XOR={bit ^ reply}")
                        else:
                            parts.append(f'{name}: sin par bit/primado válido')
                    entries.append(LogEntry(self.node, 'Primado', ' · '.join(parts)))
                frame_key = (event['sender'], event['byte_count'])
                if event['real'] and event['stage'] == 2 and event['done'] and frame_key not in self.seen_frames:
                    self.seen_frames.add(frame_key)
                    entries.append(LogEntry(self.node, 'Trama', f"{event['frame_type']} · secuencia {event['frame_seq']} · DATA 0x{event['data']:02X} · CRC 0x{event['crc_received']:02X} · {'confirmada por el enlace' if event['sender'] else 'aceptada por el receptor'}.", 'success'))
                if previous and previous['sender'] == event['sender'] and previous['active'] != event['active'] and event['sender']:
                    media = {0: 'ninguno disponible', 1: 'solo IR', 2: 'solo sonido', 3: 'IR y sonido'}[event['active']]
                    entries.append(LogEntry(self.node, 'Canales', f'Medios de salida: {media}.', 'success' if event['active'] == 3 else 'warning'))
                if event['turbo'] and not previous.get('turbo'):
                    entries.append(LogEntry(self.node, 'Velocidad', f"Turbo solo IR: {event['period_ms']} ms por ronda; sonido conserva su piloto en dos rondas.", 'warning'))
                if event['stage'] == 2 and event['real']:
                    if not event['sender'] and event['frame_mask'] == 15:
                        good = event['crc_received'] == event['crc_calculated'] and event['field'] == 10
                        entries.append(LogEntry(self.node, 'CRC', f"CRC recibido {event['crc_received']:02X} · calculado {event['crc_calculated']:02X} · {'válido' if good else 'inválido: se solicita reparación'}.", 'success' if good else 'error'))
                    r = event['replies']
                    valid = [v for v in r if 0 <= v < 3]
                    status = 'ACK: bloque aceptado' if 0 in valid and all(v == 0 for v in valid) else 'NACK: reparar bloque/trama' if any(v in (1, 2) for v in valid) else 'Sin confirmación válida: se conserva el trabajo'
                    entries.append(LogEntry(self.node, 'Confirmación', status, 'success' if status.startswith('ACK') else 'warning'))
                if event['fixed'] and (event['fec'] > previous.get('fec', 0)):
                    entries.append(LogEntry(self.node, 'Matriz', f"La paridad reconstruyó bits del bloque {event['block'] + 1}; total recuperados: {event['fec']}.", 'success'))
            return event, entries
        f = fields(line)
        version = re.search(r'VERSION[ =]+(ESTACION|PROTO).*?BUILD[ =]?(\d+)', line)
        if version:
            self.version, self.build = version.group(1), int(version.group(2))
        if line.startswith('STATUS VERSION='):
            self.app.update(f)
            event['kind'] = 'status'
        elif re.fullmatch(r'RUN=[01](?:;.*)?', line):
            running = int(line[4])
            self.app['RUN'] = running
            event.update(kind='run', running=bool(running))
            entries.append(LogEntry(self.node, 'Chat', 'Chat activo: activación confirmada por la K8.' if running else 'Chat detenido por la K8; los mensajes pendientes se conservan.', 'success' if running else 'info', raw=raw))
        elif line.startswith('DEVICE VERSION='):
            self.hardware.update(f)
            self.ready = f.get('NODE') == (0 if self.node == 'A' else 1)
            event['kind'] = 'device'
        elif line.startswith('TIMING PROFILE='):
            self.timing.update(f)
        elif line.startswith('LOCAL23_DATA='):
            self.local.update(f)
        elif line.startswith('CLOCK_RX_RAW='):
            self.clock.update(f)
        elif line.startswith('PHY_HS EVENT='):
            self.mac.update(f)
            signature = (f.get('EVENT'), f.get('STATE'), f.get('REQ'), f.get('FRAMES'))
            if signature != self.last_hs:
                self.last_hs = signature
                entries.append(LogEntry(self.node, 'Enlace', HS_NAMES.get(f.get('EVENT'), line), 'warning' if f.get('EVENT') in ('TIMEOUT', 'REJECT') else 'info', raw=raw))
        elif line.startswith('PHY_RATE PHASE='):
            if self.rate != f:
                text = 'Reposo pasivo; el próximo SYN/SFD utiliza escalones rápidos de 75 ms.' if self.mac.get('STATE') == 0 else f"Fase {f.get('PHASE')} · {f.get('MODE')} · {f.get('Q_MS')} ms por ronda · escalón {f.get('CHIRP_STEP_MS')} ms."
                entries.append(LogEntry(self.node, 'Velocidad', text, raw=raw))
            self.rate = f
        elif line.startswith('CHAT_RX '):
            text = line[len('CHAT_RX '):]
            self.messages.append(text)
            event.update(kind='chat', text=text)
            entries.append(LogEntry(self.node, 'Chat', 'Mensaje recibido y reconstruido.', 'success', raw=raw))
        elif line == 'CHAT_RX':
            self.messages.append('')
            event.update(kind='chat', text='')
        elif line.startswith('QUEUED_MSG '):
            event.update(kind='queued', **{k.lower(): v for k, v in f.items()})
            entries.append(LogEntry(self.node, 'Chat', f"En cola: {f.get('PLAIN', '?')} bytes originales → {f.get('BYTES', '?')} bytes a transmitir; compresión {'sí' if f.get('COMP') else 'no'}.", raw=raw))
        elif line.startswith('MIC20='):
            self.mic = f.get('MIC20')
            event.update(kind='mic', count=self.mic, threshold=f.get('THRESHOLD'))
        elif line.startswith('EVENTS='):
            self.event_format = f.get('FORMAT', 0) if f.get('EVENTS') else 0
        elif line.startswith(('UNKNOWN', 'CRC_BUSY', 'RATE_BUSY', 'STOP_FIRST', 'QUEUE_FULL', 'MESSAGE_TOO_LONG', 'INPUT_TOO_LONG', 'CHAT_RX_ERROR')):
            entries.append(LogEntry(self.node, 'Comando', line, 'error', raw=raw))
            event['kind'] = 'rejected'
        return event, entries


def export_session(path, entries, raw_records, tests, truncated=False):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'format': 'cc8-session-1', 'exported': datetime.now().astimezone().isoformat(),
                   'truncated': bool(truncated), 'events': [vars(e) for e in entries], 'raw': list(raw_records), 'tests': list(tests)},
                  f, ensure_ascii=False, indent=2)
