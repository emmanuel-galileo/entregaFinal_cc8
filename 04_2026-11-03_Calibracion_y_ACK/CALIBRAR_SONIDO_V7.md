# Calibracion del sonido con V7.1

El protocolo de tramas mantiene su formato y tiempos. Esta version agrega tono continuo
y lectura directa del microfono para separar los problemas acusticos de las retransmisiones.
La V7 anterior, incluido su AXF probado, esta en `Respaldo_V7_validada_2026-11-02.zip`.

## Preparacion

Ambas K8 usan el mismo proyecto `Protocolo_K8_V7.uvprojx` y la misma imagen.
`/status` debe mostrar `BUILD=701` o `BUILD=702`; ambas versiones incluyen estos comandos.
Tras cargarlas, pulsar RESET en ambas. A=COM3, B=COM5 en el montaje actual.

Cerrar otras terminales si el asistente va a controlar los puertos.
Para hacerlo manualmente, abrir `terminal_protocolo_v7.ps1` en dos ventanas y elegir A/B.

## Comandos nuevos

Todos llevan Enter:

| Comando | Funcion |
|---|---|
| `/stop` | Detener protocolo y apagar emisores. |
| `/tone 1` | Tono continuo de 3000 Hz, solamente con protocolo detenido. |
| `/tone 0` | Apagar el tono manual. |
| `/mic` | Contar cambios de DO en los ultimos 20 ms. |
| `/monitor 1` | Mostrar esa lectura cada 200 ms. |
| `/monitor 0` | Detener el monitor. |

`/start` apaga el tono manual y el monitor antes de reanudar el protocolo.

## Orden del ajuste

1. `/stop` en ambas. `/fault 0` en ambas. Mantener las posiciones fijas.
2. Leer `/mic` con los dos buzzers apagados. Buscamos muy pocos cambios, idealmente cero.
3. Para B→A: dejar el buzzer A apagado, activar `/tone 1` en B y `/monitor 1` en A.
4. Ajustar solamente el potenciometro del KY-037 de A con movimientos pequenos.
   Anotar los giros para poder volver. Buscar una lectura sostenida y claramente separada
   del silencio. Un tono limpio de 3000 Hz produce aproximadamente 120 cambios en 20 ms,
   al contar ambos flancos; el numero exacto depende de la forma de la senal.
5. Alternar tono encendido/apagado. El ajuste debe servir para ambos estados, no solo
   hacer que se encienda el LED del modulo. DO puede permanecer estable en cualquiera
   de sus niveles cuando hay silencio: para este firmware cuentan los cambios.
6. Repetir A→B ajustando el KY-037 de B, dejando fijo el ajuste de A.
7. Medir cada microfono con su propio buzzer y despues con ambos buzzers. Si el buzzer
   local altera mucho la recepcion del remoto, revisar posicion y separacion acustica.
   El potenciometro fija un umbral; no identifica de donde viene el sonido.
8. Apagar tonos, detener monitores y repetir mensajes reales con los nuevos ajustes.

El ajuste por software `/threshold 60` cuenta cambios ya recibidos. El potenciometro
afecta la salida DO antes de que la K8 pueda contar esos cambios: son ajustes diferentes.
Mantener el umbral de software en 60 durante esta primera comparacion.

Referencia del umbral de DO y potenciometro: [Joy-IT KY-037](https://sensorkit.joy-it.net/en/sensors/ky-037).

## Prueba automatica

`calibrar_sonido_v7.ps1 -Stage Referencia -Seconds 4` mide silencio, solo B,
solo A, ambos y silencio final. Guarda muestras y resumenes en `output\pruebas`,
apaga tonos y cierra los dos puertos al terminar.
`-Stage Ambos -Seconds 8` repite solamente el caso de dos tonos simultaneos.
Si una prueba dejo datos pendientes, el script se detiene para conservarlos.
`-AllowPendingTestData` permite medir con ellos retenidos, sin borrarlos.
Despues de corregir el montaje, `-Stage Reanudar -AllowPendingTestData` intenta
entregarlos con ambas placas activas y las comprobaciones automaticas apagadas;
al terminar vuelve a detenerlas. No cambia la politica ACK ni reinicia secuencias.
Si hace falta rescatar pendientes por un medio concreto, `-RecoveryMode IR`
solicita modo IR en ambas placas antes de continuar, con ambos enlaces IR
despejados. `-RecoverySeconds 180` amplia el plazo del rescate. El modo inicial
por defecto es `Conservar`; no se cambia la seleccion de medios.

Primera referencia del 3 de noviembre, sin girar potenciometros:

| Estado | Microfono A | Microfono B |
|---|---|---|
| Silencio | 0 cambios/20 ms | 0 cambios/20 ms |
| Solo B encendido | 119–120 | 0 |
| Solo A encendido | 0 | 120 |
| Ambos encendidos | 0–160; 15/20 muestras superaron 60 | 0–172; 15/20 muestras superaron 60 |

Los microfonos detectan bien el tono remoto por separado. Las caidas aparecen al
sonar ambos. Esto apunta a interferencia, por lo que la siguiente comparacion mantiene
fijos los potenciometros y mejora la separacion: un par buzzer B/microfono A a 3–5 cm,
otro par buzzer A/microfono B a 3–5 cm, separados entre si unos 15–20 cm.
La comparacion permitira evaluar el efecto de la posicion sin cambiar otro ajuste.

Despues de acomodar los pares y ajustar el potenciometro de B, la prueba de sonido
y la tanda duplex de 16 caracteres por sentido pasaron sin errores ni retransmisiones.
La tanda con todos los automatismos recupero un error y mantuvo IR+sonido en ambos
sentidos. Conservar este ajuste. Ver [informe final](output/pruebas/RESULTADO_CALIBRACION_SONIDO_2026-11-03.md).
