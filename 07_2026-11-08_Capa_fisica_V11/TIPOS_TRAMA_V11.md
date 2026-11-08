# Tipos de trama — V11 BUILD1103

El campo Control conserva **4 bits**, ahora distribuidos así:

```text
           Control
      +------+------+
      |  TT  |  SS  |
      +------+------+
       tipo   secuencia
       2 bits  2 bits
```

| TT | Tipo | Función al recibir |
|---|---|---|
| `00` | INICIO | Abre un mensaje y entrega su primer byte. |
| `01` | CONTINUACIÓN | Entrega un byte de un mensaje que ya está abierto. |
| `10` | FIN | Entrega el último byte y cierra el mensaje. |
| `11` | ÚNICA | Abre y cierra una unidad de mensaje transportada en un solo byte. |

SS conserva la secuencia de 0 a 3, que continúa entre mensajes. El receptor no vuelve a entregar una trama ya recibida aunque se pierda su confirmación. Los ACK/NACK compactos y las reparaciones por bloques conservan su funcionamiento.

## Ejemplo del chat

Para `/send Hola`, el chat ya añadía su terminador de mensaje. Se transporta así:

```text
INICIO('H') → CONTINUACIÓN('o') → CONTINUACIÓN('l')
            → CONTINUACIÓN('a') → FIN(terminador)
```

El terminador no se añadió en esta actualización. Los tipos clasifican los bytes que ya existían.

Una llamada a `v11_enqueue` representa una unidad completa, previamente codificada y, si corresponde, comprimida. Se marcan su primer byte, los intermedios y el último. Si tiene un solo byte se marca ÚNICA. Un mensaje de un carácter visible no implica necesariamente una sola trama: puede usar varios bytes UTF-8 y el chat incluye su terminador. En el chat actual, un envío vacío con `/send ` transporta solo el terminador y utiliza ÚNICA.

## Validación y recuperación

- TT y SS forman parte del Control cubierto por el CRC-8. Los cuatro algoritmos existentes se conservan.
- El receptor solo aplica el tipo y entrega el byte después de reconstruir la trama y validar el CRC.
- CONTINUACIÓN y FIN requieren un mensaje abierto. INICIO y ÚNICA requieren que no haya otro abierto.
- Un tipo fuera de ese orden se rechaza sin entregar el byte; se devuelve el estado de trama inválida. Se registra internamente en `type_bad`, separado de los errores de CRC.
- La comprobación de duplicados ocurre antes de aplicar de nuevo el tipo: una repetición no reabre ni cierra dos veces el mensaje.
- El tipo queda guardado junto al byte en la cola y dentro del Control de la trama durante reintentos, reparaciones, cambios de medio y cambios de turno.

Las etiquetas de la cola ocupan memoria local y **no se transmiten como bytes adicionales**.

## Lo que se conserva

- SYN, SFD, Control(4), DATA(8), CRC(8) y FIELD.
- Número de tramas y rondas por byte, modos demostración/rápido y Turbo IR.
- Compatibilidad de reloj directo/PC817 de BUILD1102, con D11/A6 y el mismo PINMAP5.
- UTF-8/CP1252 y compresión de mensajes en sus capas actuales.
- Formato del LOG existente. Su ampliación queda para la siguiente definición del usuario.

TT es el tipo del campo Control de la **trama completa**. No es el indicador DATA/CTRL del encabezado compacto de cada ronda: son controles distintos.

## Estado de esta versión

BUILD1103 está preparada y compilada; todavía no se cargó en las K8. Debe cargarse en **ambas placas**: no mezclarla con BUILD1101/1102, que no interpretan los nuevos tipos. El proyecto sigue siendo `Fisica_K8_V11.uvprojx`.

Pruebas y evidencias: `output/pruebas/RESULTADO_TIPOS_TRAMA_V11_1103.md`. Estas pruebas usan firmware ARM y sensores simulados; la validación física del nuevo firmware queda pendiente.
