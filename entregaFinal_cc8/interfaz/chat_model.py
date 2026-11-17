"""Borradores de ejemplo y conversaciones observadas desde cada extremo."""
from collections import deque
from datetime import datetime


TEXT_SAMPLES = (
    ('character', 'Carácter · A · 1 byte UTF-8', 'A'),
    ('dollar', 'Dólar · $ · 1 byte UTF-8', '$'),
    ('utf2', 'Acento · ñ · 2 bytes UTF-8', 'ñ'),
    ('utf3', 'Símbolo · € · 3 bytes UTF-8', '€'),
    ('emoji', 'Emoji · 😀 · 4 bytes UTF-8', '😀'),
    ('utf8', 'UTF-8 completo · Uñ€😀', 'Uñ€😀'),
    ('cp1252', 'Extended ASCII · ñ€', 'ñ€'),
    ('empty', 'Mensaje vacío', ''),
)
PALETTES = {
    'Emojis': ('😀', '😃', '😊', '😂', '😎', '🤔', '😭', '👍', '👋', '🚀', '🔥', '💡', '🎉', '🔊', '🔇', '📡', '🧪', '🔧'),
    'Signos': ('$', '€', '£', '¥', '°', '±', '×', '÷', '→', '←', '↔', '©', '®', '¿', '¡', 'Ω', '♥', '✓'),
    'Letras': ('ñ', 'Ñ', 'á', 'é', 'í', 'ó', 'ú', 'ü', 'Á', 'É', 'Í', 'Ó', 'Ú', 'Ü', 'ç', 'ø', 'α', 'β'),
}


def representable(value, encoding):
    try:
        value.encode(encoding, errors='strict')
        return True
    except UnicodeEncodeError:
        return False


class ChatHistory:
    """Una recepción solo aparece cuando esa K8 emite CHAT_RX, incluso si está emparejada."""
    def __init__(self):
        self.rows = {n: deque(maxlen=300) for n in 'AB'}

    def clear(self):
        for rows in self.rows.values():
            rows.clear()

    def consume(self, node, event):
        if node not in self.rows:
            return False
        stamp = event.get('time', datetime.now().astimezone().isoformat())[11:19]
        if event['kind'] == 'chat_sent':
            self.rows[node].append({'outgoing': True, 'item': event['item'], 'time': stamp,
                                    'source': event.get('source', 'observado')})
            return True
        if event['kind'] == 'chat':
            self.rows[node].append({'outgoing': False,
                'item': {'text': event['text'], 'received': True}, 'time': stamp,
                'source': event.get('source', 'observado')})
            return True
        return event['kind'] == 'chat_changed'

    def snapshot(self):
        return {n: [{'outgoing': row['outgoing'], 'time': row['time'], 'source': row['source'],
            'text': row['item']['text'], 'received': row['item'].get('received', False),
            'confirmed': row['item'].get('confirmed', False), 'error': row['item'].get('error', '')}
            for row in rows] for n, rows in self.rows.items()}
