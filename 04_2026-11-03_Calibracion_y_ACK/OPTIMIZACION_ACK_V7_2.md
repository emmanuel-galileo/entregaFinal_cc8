# ACK agrupado — V7.2

BUILD=702. Se conserva V7.1 calibrada, con AXF, fuentes y pruebas, en
`Respaldo_V7_1_calibrada_2026-11-03.zip`.

## Cambio aprobado

Con ventana de dos, se fusionan confirmaciones pendientes de dos secuencias
adyacentes. Un ACK DATA=00000011 confirma SS y SS+1. Los campos, CRC, bits por
medio, tono de 3000 Hz, reloj, pausa, timeout y comprobaciones permanecen iguales.

Si ambos usuarios envian, un ACK individual pendiente puede ceder el turno a la
segunda trama propia de la ventana. Durante esa transmision puede llegar la segunda
trama del otro extremo y quedar confirmada en el mismo ACK.

## Limites

- Solo se permite una trama propia adicional por ACK pendiente.
- El programa no inicia esa trama si su duracion y pausa excederian el presupuesto
  de 1200 ms desde que se preparo el ACK. Una trama ya en el aire termina normalmente.
- Sin datos propios, el ACK sale inmediatamente; no se introduce una espera fija.
- Final LF, duplicados y ACK de dos tramas salen sin ceder el turno.
- NACK y respuestas LINK no ceden el turno a DATA. Un ACK vencido tambien se atiende
  para evitar que el trafico de control lo postergue indefinidamente.
- La fusion de NACK puede confirmar la trama buena y pedir repetir la mala. Un dato
  ya recibido no vuelve a solicitarse si la respuesta pendiente puede actualizarse.
- Al fusionar se recalcula CRC y se conservan el instante y la cesion del ACK original.

## Comparacion controlada

`/ack 0` selecciona la politica anterior y `/ack 1` la agrupada. Requiere protocolo
detenido, colas vacias y ninguna transaccion pendiente. Ambas politicas usan el mismo
firmware y formato; el menu informa GROUP_ACK.

El script `probar_protocolo_v7.ps1` admite `-GroupAck 0|1`.
Para comparar ambos envios, usar mensajes de 15 caracteres mas LF: 16 bytes por
sentido, que completan cuatro vueltas de secuencia y conservan el mismo numero
inicial al pasar de una politica a la otra sin RESET.

Para pruebas automaticas usar tambien `-PrimeProbe`: hace una comprobacion valida
en cada sentido antes de activar `/auto 1`, de modo que el contador de DATA nuevos
y la referencia temporal de las comprobaciones empiecen de forma comparable.

## Emulacion

El C real compilado para Cortex-M4 paso 150076 comprobaciones. Incluye perdida de
ACK, CRC incorrecto, desorden, limites de espera, fin de mensaje, ventanas que dan
varias vueltas, los nueve pares de modos y estres con fallos reproducibles.

Con 17 bytes por sentido (incluido LF), sin errores fisicos:

| Caso | ACK individual | ACK agrupado |
|---|---|---|
| Un sentido | 18.29 s, 17 ACK | 18.29 s, 17 ACK |
| Ambos sentidos | 29.87 s, 34 ACK | 21.55 s, 18 ACK |
| Ambos con comprobaciones automaticas | 46.51 s, 34 ACK | 38.19 s, 18 ACK |

Estos tiempos incluyen confirmaciones finales y pertenecen al modelo. No son
mediciones de las K8 reales. La comparacion fisica usa latencia de mensaje y
contadores de ACK, CRC, retransmisiones y timeout para evaluar el resultado.

## Referencia fisica

El primer intento con ACK individual no recibio sonido A->B. Se encontro que la
posicion habia cambiado, confirmado por el usuario. Se conservaron los mensajes
pendientes y se recupero la disposicion antes de comparar politicas. Los intentos
fallidos se conservan en los registros y no se usan como linea base de rendimiento.

Despues de recuperar la posicion y el mensaje pendiente, las tandas reales de
16 bytes por sentido pasaron sin CRC incorrectos, reintentos ni timeout:

| Comprobaciones | Individual | Agrupado | ACK enviados en total |
|---|---:|---:|---|
| Desactivadas | 28.21 s | 19.92 s | 32 -> 16 |
| Automaticas | 42.78 s | 34.37 s | 32 -> 16 |

Tiempo desde el primer envio hasta la ultima confirmacion de ambos mensajes,
observado por USB serie. Reduccion aproximada del 29% y 20% respectivamente
en estas parejas de tandas. Tambien pasaron CRC incorrecto intencional y ACK
perdido, con recuperacion del mensaje y descarte de duplicados.
Ver [mediciones y registros](output/pruebas/RESULTADO_ACK_V7_2_2026-11-03.md).
