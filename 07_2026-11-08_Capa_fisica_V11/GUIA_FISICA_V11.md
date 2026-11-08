# Física K8 V11 — BUILD1103 preparada; BUILD1101 última carga verificada

La BUILD1103 incorpora los cuatro tipos de trama INICIO, CONTINUACIÓN, FIN y ÚNICA en Control=TTSS, sin agregar bits. Ver `TIPOS_TRAMA_V11.md`. Conserva `/clockmode direct|opto` de BUILD1102 con los mismos D11/A6. Direct es el valor al reiniciar. Para usar PC817 en ambos relojes, elegir `/clockmode opto` en ambas placas con STOP. Ver el cableado en `RELOJ_DIRECTO_PC817_V11.md`. Esta actualización todavía no se ha cargado en las placas y debe cargarse en ambas.

Se mantiene el armado PINMAP5 y el chat de terminal. Esta versión sustituye el control plano por barridos, incorpora demostración de 1 Hz y Turbo solo IR. El proyecto de Keil es `Fisica_K8_V11.uvprojx`. V10.1 se conserva por separado.

## Armado conservado

| Función | Pin de cada NUCLEO |
|---|---|
| Emisor IR | D9/PA8 → 330 Ω → ánodo del LED; cátodo a GND local |
| Sensor de flama | DO → D6/PB1; alimentación 3V3 local |
| Buzzer pasivo con módulo | S → A0/PA0; alimentación 3V3 local |
| KY-037 | DO → A1/PA1; alimentación 3V3 local |
| Reloj de salida | D11/PB5 → 330 Ω → A6/PA7 de la otra K8 |
| Reloj de entrada | A6/PA7 recibe D11 de la otra K8 |

Los GND son comunes. No unir las salidas 3V3 de las dos placas. D2, D12, A3 y D3 quedan sin función, como entradas analógicas sin pull. Los PC817 no participan en este armado.

A corresponde a COM3 y B a COM5. La selección 1/2 determina etiqueta, desempate y umbral inicial del micrófono; cualquiera puede iniciar una transmisión.

## Modos y tiempos

| Perfil | Comando, con STOP | Ronda normal | Solo IR con Turbo | Escalón de datos |
|---|---|---:|---:|---:|
| Demostración | `/rate log` o `/rate demo` | 1000 ms | No se activa | 75 ms |
| Rápido | `/rate max` | 800 ms | 400 ms | 60 ms / 30 ms |
| Alternativo | `/rate 1` | 1000 ms | 500 ms | 75 ms / 37 ms |
| Alternativo lento | `/rate 0.5` | 2000 ms | 1000 ms | 150 ms / 75 ms |

SYN y SFD conservan escalones de 75 ms, con flancos de reloj separados 75 ms: aproximadamente 13.33 Hz en ambos modos. La terminal anuncia `SYN_FAST`, `SFD_FAST` y después `DATA`, junto con `Q_MS`, `CLOCK_mHz` y `CHIRP_STEP_MS`.

En demostración, los inicios de las rondas se programan cada **1000 ticks de 1 ms**, sin sumar el tiempo de las operaciones de cada ronda. Ese valor procede del reloj interno HSI de la placa; no significa exactitud de laboratorio frente a un reloj externo. El handshake y los cambios de turno son intervalos separados de las rondas de datos.

`max` es un perfil configurado y probado; no es una medición automática del límite físico del buzzer. `/autocal` y acelerar FIELD por separado quedan pendientes, como se discutió.

## Qué ocurre al enviar

1. Las dos K8 escuchan en reposo. Una solicitud en cola inicia la negociación.
2. La solicitante envía SYN `1111` y un pequeño código de perfil mediante barridos ascendentes en banda baja. La otra contesta en banda alta descendente si está en `/start`.
3. Se intercambian SFD `0000` y su confirmación. Sin completar esta negociación no salen datos del chat.
4. Se transmite una trama de un byte, con su control, CRC y cierre. Después se libera el turno para que pueda pasar la otra K8.

Si solicitan simultáneamente, gana el primer flanco. Si coinciden dentro de la ventana de 2 ms, gana A. La otra conserva su mensaje pendiente y lo envía en su turno. No hay un maestro fijo.

El primer pulso de cada paquete del handshake tiene una duración reconocible: SYN 12 ms, aceptación 20 ms, SFD 28 ms y confirmación SFD 32 ms; los siguientes duran 37 ms. Esto permite encontrar el comienzo cuando una placa se inicia a mitad de una solicitud. **El paquete también debe pasar la validación de sus barridos**; ese pulso por sí solo no autoriza datos. Los relojes llevan sincronización y fases, no los bytes del chat.

## Cómo es una ronda

Cada ronda tiene cuatro partes, cada una formada por tres escalones:

```text
cabecera H0 → cabecera H1 → datos/control → devolución
```

En modo demostración ocupan 900 ms; quedan 100 ms de margen hasta el inicio siguiente. En rápido normal ocupan 720 ms y quedan 80 ms. En Turbo ocupan 360 ms y quedan 40 ms.

El encabezado repetido de 32 bits se reemplazó por **4 bits de control compacto**. Cada mitad del encabezado usa uno de cuatro barridos distinguibles, que representa un valor de 0 a 3. Los datos del mensaje siguen usando bits 0 y 1. Así también el control, las confirmaciones y los avisos de reparación viajan por barridos.

En una ronda de datos normal, IR y sonido pueden llevar un bit cada uno. El receptor devuelve el complemento de cada bit por el mismo medio: si se mandó 0, devuelve 1; si se mandó 1, devuelve 0. El emisor comprueba que el XOR sea 1.

Los controles usan respuestas de estado: 0 = aceptado, 1 = faltan bits del bloque, 2 = trama inválida (CRC o uso inválido del tipo de trama) y 3 = encabezado no aceptado. No se interpreta un estado de control como XOR de un bit de datos.

## Recuperación

- **Un escalón dañado:** si los otros dos tienen frecuencia, densidad y dirección coherentes, se reconstruye el símbolo localmente. Se cuenta en `LOCAL23_*`, sin suspender el medio.
- **Bits ausentes del bloque:** se intenta resolverlos con la paridad cruzada de 6 datos + 2 paridades. Se cuenta en `FEC`.
- **Un medio falla:** al primer primado incorrecto se suspende para datos; el otro absorbe la carga. Las sondas siguen comprobando el medio suspendido y tres respuestas válidas permiten restaurarlo.
- **ACK perdido:** una secuencia alternante y una respuesta guardada evitan avanzar dos veces al repetir una ronda.
- **Paridad insuficiente o CRC incorrecto:** se solicitan posiciones o se repite el bloque pequeño afectado. Se conservan los demás bloques; no se vuelve a poner todo el mensaje en la cola.
- **Ambos medios fallan:** se conservan la cola, la trama y los bloques recibidos. Si se pierde la conexión, se negocia otra vez y se retoma la reparación del bloque en curso.

El formato lógico se conserva: SYN(4), SFD(4), CONTROL(4), DATA(8), CRC(8), FIELD(4). Los últimos 24 bits se trabajan en cuatro bloques de seis datos con sus paridades. El control físico compacto y la negociación añaden señalización; no cambian el byte del chat.

La compresión Heatshrink, UTF-8, los cuatro CRC-8 y la supresión de bytes duplicados se conservan. El CRC comprueba el resultado; las reparaciones y la retransmisión local son mecanismos separados.

## Turbo y sonda de sonido

Solo se permite Turbo si se negoció `/irboost 1`, el perfil es rápido y únicamente IR permanece activo. En demostración siempre queda prohibido, incluso con `/irboost 1`.

```text
Ronda IR 1: cabeceras + dato IR + devolución IR; buzzer envía sonda lenta
Ronda IR 2: cabeceras + dato IR + devolución IR; buzzer devuelve esa sonda
            └── solo ahora se evalúa el resultado del sonido ──┘
```

Con `/rate max`, cada ronda IR dura 400 ms, mientras cada escalón de la sonda de sonido dura **120 ms**. Sonda y respuesta abarcan la pareja de rondas, de 800 ms. La primera ronda no cuenta como una prueba fallida del sonido. La restauración y la salida de Turbo se hacen al completar la pareja.

El IR también cambia a un conjunto de frecuencias adecuado para ventanas cortas. No se intenta hacer funcionar el sensor de flama a frecuencias de varios kHz. Duplicar el reloj no implica duplicar la velocidad neta del chat: también hay controles, paridad y negociación.

## Terminal

Abrir dos PowerShell en esta carpeta:

```powershell
.\terminal_fisica_v11.ps1 -PortName COM3
.\terminal_fisica_v11.ps1 -PortName COM5
```

Al reiniciar, seleccionar `1` en COM3 y `2` en COM5. En ambas, para demostrar:

```text
/stop
/rate log
/phylog 1
/start
```

Para rápido, sustituir `/rate log` por `/rate max`, siempre con STOP. Configurar el mismo perfil en ambas para que cada una use ese perfil cuando le toque iniciar.

Comandos útiles:

```text
/send Hola
/status
/probe             8 rondas sin mensaje
/samples           últimas tres frecuencias y conteos medidos por medio
/phylog 1          negociación, modo, rondas, primados, reconstrucción y paridad
/fault 2           apagar el emisor de sonido de esa K8
/fault 0           restaurar los emisores
/notch 1 3         omitir un escalón en ambos medios en el próximo dato
/stop              detener y conservar los pendientes
```

`/fault` es una inyección de fallo de transmisión para ensayos; no equivale a probar todas las interferencias físicas posibles. Los comandos manuales `/ir` y `/tone` son de diagnóstico con STOP y no representan la modulación del protocolo.

En los registros, `KIND=DATA` muestra XOR y `KIND=CTRL` muestra STATUS. `ACTIVE=1` significa solo IR, `2` solo sonido y `3` ambos. En Turbo el sonido aparece como `PILOT_PAIR`.

## Compilar, cargar y comprobar

```powershell
.\compilar_protocolo_v8.ps1 -Project Fisica_K8_V11
.\cargar_protocolo_v8.ps1 -Project Fisica_K8_V11
```

Después de cargar, pulsar RESET en ambas. El script identifica los ST-LINK por número de serie, por lo que no hace falta desconectar una para cargar la otra.

Las pruebas quedan en `output/pruebas`. `tests/enlace_v11_modelo.py` prueba la lógica ARM con fallos sintéticos. `tests/fisica_v11_motor_modelo.py` ejercita el firmware optimizado y los temporizadores con sensores simulados. `probar_fisica_v11.ps1` prueba las dos K8 reales por COM3/COM5 y deja emisores apagados y puertos cerrados al terminar. Los resultados físicos de esta sesión se resumen en `output/pruebas/RESULTADO_FISICA_V11.md`.
