# V8.1: planificacion y compresion

Proyecto separado: `Protocolo_K8_V8.uvprojx`, BUILD=801. Cargado y probado en
ambas placas el 4 de noviembre de 2026. V7.2 se conserva intacta,
incluido su AXF, y en `Respaldo_V7_2_validada_antes_V8_20261103.zip`.
El mismo firmware V8 se carga en ambas placas. Ambos extremos deben usar V8
antes de intercambiar mensajes comprimidos.

## Planificador

- Se conserva la trama fisica, los cuatro CRC, la ventana de dos, secuencias
  modulo cuatro, tono de 3000 Hz y todos los tiempos de simbolo y reloj.
- Un probe pendiente ya no bloquea DATA mientras se espera su resultado.
  Un cambio de modo sigue bloqueando DATA hasta confirmar el acuerdo.
- Con ambos medios sanos, comprobar cada 32 DATA nuevos o tras 2 segundos
  sin actividad de datos. Actividad es fin de TX DATA, confirmacion de un
  pendiente o entrega de nuevos bytes. Duplicados recibidos no renuevan el plazo.
- Con un medio apartado, o una primera comprobacion fallida, se conserva
  el plazo de 2 segundos entre comprobaciones para detectar su recuperacion.
- NACK y timeout adelantan comprobaciones. Se conservan fallo=2,
  reincorporacion=3 y timeout=3 segundos desde fin de transmision.
- La comprobacion ordinaria puede ceder a la segunda DATA de una ventana
  con un limite de una trama adicional; las comprobaciones urgentes tienen prioridad.
- LINK/NACK urgentes y ACK vencidos se priorizan tambien sin agrupacion.
- `/schedule 0|1` compara el planificador anterior y el nuevo dentro del mismo
  firmware. Requiere placas detenidas y sin pendientes. `/ack 0|1` conserva
  la comparacion de confirmaciones individuales y agrupadas.

## Compresion por mensaje

Dependencia: [heatshrink de Atomic Object](https://github.com/atomicobject/heatshrink),
commit `7d419e1fa4830d0b919b9b6a91fe2fb786cf3280`, licencia ISC conservada en
`third_party/heatshrink/LICENSE`. Configuracion estatica, ventana 256 bytes,
lookahead 16 y sin indice. Sin malloc/free.

`/compress 0|1` controla el intento de compresion de los siguientes mensajes.
El receptor acepta ambas formas automaticamente. Maximo 185 bytes originales.
Se elige compresion solo si reduce el numero real de bytes, incluidos encabezado,
escapes y terminador. Los mensajes normales que no ahorran se envian como antes:

```text
texto + LF
```

Los comprimidos usan este sobre dentro del flujo DATA:

```text
ESC 'C' original_len packed_len packed_bytes LF
```

Dentro del sobre, LF se codifica como `ESC 0` y ESC como `ESC 1`, incluyendo
los campos de longitud. Asi el unico LF sin escapar termina el mensaje.
Un original que empieza con ESC o contiene LF se puede transportar sin
compresion mediante el mismo sobre con etiqueta `R` y ambas longitudes iguales.
No se agregan campos a la trama fisica: cada byte sigue en DATA de 8 bits,
protegido por el CRC de la trama y las retransmisiones Selective Repeat.

El receptor verifica limites y longitudes, descomprime dentro de un buffer
de 185 bytes y muestra el texto solo al completar el mensaje. Ante un sobre
invalido descarta hasta LF y registra APP_ERR. La compresion no sustituye CRC.

## Comprobaciones antes de medir hardware

Compilacion: cero errores y advertencias, Code=25356, RO=3452,
RW=16, ZI=5064 bytes. Cabe en la licencia Keil de 32 KiB y en la NUCLEO.

Los informes separan emulacion de resultados reales:

- `resultado_logica_v8.json`: logica C Cortex-M4, perdidas, CRC incorrectos,
  cambios de medio, ventanas, 96 desfases/retardos y compresion sobre el enlace.
- `resultado_codec_v8.json`: mas de un millon de comprobaciones, limites,
  texto, UTF-8, CP1252, LF/ESC, buffers protegidos y entradas malformadas.
- `resultado_temporizacion_v8.json`: 36 casos ideales del AXF y comandos reales,
  incluida compresion y reconstruccion UTF-8. Sensores ideales; memcpy modelado.

Ejemplos del C real, contando todo lo transmitido:

| Texto original | Sin compresion | Automatico |
|---|---:|---:|
| Hola (4 bytes) | 5 | 5 |
| Frase de 76 bytes sin repeticiones suficientes | 77 | 77 |
| Frase de 82 bytes sobre IR y sonido | 83 | 74 |
| Frase de 77 bytes con una repeticion | 78 | 53 |
| si repetido, 35 bytes | 36 | 12 |

Estos son tamaños de mensajes, no mediciones del tiempo en las placas.
Las pruebas fisicas comparan `/schedule 0|1`, `/compress 0|1` y `/ack 0|1`,
y verifican APP_ERR=0, texto exacto y colas vacias antes de cerrar los puertos.

## Mediciones reales

Pasaron 19 etapas y una comprobacion adicional con diagnostico ya en curso:
38 mensajes exactos, sin duplicados y APP_ERR=0. Se incluyeron cuatro CRC,
UTF-8 comprimido y normal, CP1252, ACK perdido, fallos de cada medio con
mensajes comprimidos y reincorporacion en ambos sentidos.

- Dos mensajes simultaneos de 16 bytes, ACK agrupado y automaticos activos:
  planificador anterior 34.47 s, nuevo 19.90 s hasta la ultima confirmacion.
- Texto repetitivo de 35 bytes A->B: 36 -> 12 bytes DATA y 37.45 -> 12.44 s
  hasta mostrar el texto. B->A: 38.38 -> 12.15 s.
- Se mantienen los parametros fisicos. Los fallos de esta campana V8 se
  provocaron por software; no se volvieron a aplicar las perturbaciones manuales
  del informe V7.2. Repetirlas en el montaje definitivo.

Ver [informe y trazas](output/pruebas/RESULTADO_V8_1_2026-11-04.md).

## Conversar por terminal

Abrir una ventana por placa desde esta carpeta:

```powershell
.\terminal_protocolo_v8.ps1 -PortName COM3
.\terminal_protocolo_v8.ps1 -PortName COM5
```

Si acaba de reiniciarse, elegir 1 para A y 2 para B. Con las identidades ya
seleccionadas no volver a enviar esos numeros. En ambas ventanas:

```text
/auto 1
/start
```

Enviar `/send Hola` desde cualquiera. `/trace 0` reduce los registros de tramas
para conversar; `/trace 1` los muestra para diagnosticar. `/stop` en ambas
apaga emisores; ESC cierra cada terminal. `-TextEncoding CP1252` debe usarse
en ambas ventanas si se quiere esa codificacion; el modo habitual es UTF-8.

La sesion de pruebas queda con emisores detenidos y automaticos apagados para
mantener el montaje en silencio, y planificador, ACK agrupado y compresion activados.
