# Contexto técnico del proyecto CC8

Documento autónomo para explicar el proyecto a otro chat y servir como base de documentación técnica. Describe la arquitectura, componentes, conexiones, trama y protocolo implementado en el firmware BUILD1105. El contenido se centra en los fundamentos de la entrega.

## 1. Objetivo y concepto del proyecto

El sistema comunica dos NUCLEO-F303K8 mediante infrarrojo y sonido, con un enlace de reloj en cada sentido. En la PC existe una aplicación de chat y observación del protocolo, además de una sala de chat mediante un servidor HTTP local.

El objetivo técnico es un protocolo de capa física híbrido:

- **Paralelo:** durante una misma fase DATOS, IR transporta un bit y sonido transporta otro bit diferente.
- **Secuencial:** las rondas sucesivas completan bloques, tramas de un byte y mensajes.
- **Validación durante la transmisión:** cada canal devuelve el complemento del bit recibido; además hay clasificación de barridos y reconstrucción por paridad.
- **Adaptación:** si falla un medio, el otro puede transportar sus posiciones pendientes. El medio suspendido sigue siendo observado para reincorporarlo.

La configuración tiene **dos medios de datos y un reloj por sentido**. Hay dos relojes cruzados porque cada equipo debe poder solicitar turno y devolver sincronización. Esa descripción indica los canales reales utilizados; no debe contarse el reloj como un tercer fenómeno de datos no convencional.

La comunicación es bidireccional. Ambos usuarios pueden dejar mensajes pendientes simultáneamente. El acceso útil se organiza por turnos de una trama de un byte, con retornos dentro de las rondas. Las identidades A/B permiten distinguir extremos y resolver empates; cualquiera puede iniciar una solicitud.

## 2. Arquitectura por capas

```text
Equipo A                                                  Equipo B
Navegador / interfaz Python                                Navegador / interfaz Python
             |                                                        |
        USB / ST-LINK                                             USB / ST-LINK
             |                                                        |
     NUCLEO-F303K8 A      <---- IR, sonido y relojes ---->     NUCLEO-F303K8 B
```

| Capa | Responsabilidad | Ubicación principal |
|---|---|---|
| Aplicación | Introducir texto, solicitar envío y presentar mensajes recibidos. | Interfaz Python/PySide6 y página del servidor HTTP local. |
| Presentación | Codificar/decodificar UTF-8 o Windows-1252; empaquetar, comprimir y reconstruir el texto. | Codificación en la aplicación; empaquetado y compresión en firmware. |
| Enlace | Tipos de trama, secuencias, CRC, ACK/NACK, duplicados y reparación. | Firmware de las NUCLEO. |
| Física y acceso | Señales GPIO, barridos, reloj, sincronización, medición, primados, matrices, pilotos y turnos. | Firmware, sensores y emisores. |

El USB permite que cada PC controle su NUCLEO y reciba el registro. La información entre las dos NUCLEO atraviesa los medios del proyecto.

### Una PC o dos PC

| Configuración | Funcionamiento |
|---|---|
| Una PC y dos K8 | Una aplicación abre ambos puertos COM y puede observar los dos extremos. |
| Dos PC y una K8 local por PC | Cada aplicación abre únicamente su puerto local; en una se elige A y en la otra B. La comunicación física sigue siendo entre las K8. |

El servidor web se ejecuta en la PC. El botón **Chat web** abre la dirección local elegida por la aplicación, normalmente `http://127.0.0.1:8765`. La aplicación permanece abierta. En dos PC, cada una tiene su servidor local; HTTP no sustituye el enlace físico entre tarjetas.

`Iniciar_CC8.cmd` prepara las dependencias y abre la interfaz. El firmware se carga por separado desde Keil µVision.

## 3. Componentes y condiciones físicas

Cada extremo utiliza:

| Componente | Función |
|---|---|
| NUCLEO-F303K8 | Procesamiento, temporización, generación de señales y recepción digital. |
| LED infrarrojo con resistencia de 330 ohm | Emisor del canal óptico. |
| Módulo sensor de flama, salida DO | Convierte la señal óptica en flancos digitales. |
| Módulo buzzer pasivo, entrada S | Emisor de los barridos acústicos. |
| Módulo micrófono KY-037, salida DO | Convierte la señal acústica en flancos digitales. |
| Circuito de transferencia de reloj | Lleva D11 del emisor hasta A6 del receptor. |
| Cable USB de datos | Alimentación de la NUCLEO y comunicación con su PC. |

Los módulos usan **3V3 y GND de su propia NUCLEO**. Los sensores se leen por DO; sus salidas analógicas AO quedan libres. El buzzer es un módulo con entrada de señal y alimentación, no un elemento desnudo conectado directamente al GPIO.

Cada LED apunta al sensor del otro equipo. Cada buzzer se coloca cerca del micrófono contrario. La luz ambiente, los comparadores, la orientación, el eco y la posición de los módulos afectan las mediciones. Como referencia de montaje se utilizaron distancias cortas: IR del orden de 1-2 cm y buzzer-micrófono del orden de 1-5 cm, separando los pares acústicos cuando es posible. Esas distancias son un punto de partida, no un alcance máximo certificado.

El potenciómetro del sensor ajusta su comparador físico. El comando `/threshold` modifica únicamente la detección de ocupación acústica previa a solicitar turno; no mueve ese potenciómetro ni cambia las tolerancias del clasificador de barridos.

## 4. GPIO y conexiones

| Pin NUCLEO | Pin MCU | Función |
|---|---|---|
| D9 | PA8 | Salida IR; TIM1 CH1, AF6. |
| D6 | PB1 | DO del receptor IR; TIM3 CH4, AF2. |
| A0 | PA0 | Señal S del buzzer; TIM2 CH1, AF1. |
| A1 | PA1 | DO del micrófono; EXTI1. |
| D11 | PB5 | Reloj transmitido. |
| A6 | PA7 | Reloj recibido; EXTI7. |
| D13 | PB3 | LED de usuario integrado, usado para identificación. |
| 3V3 / GND | — | Alimentación y referencia local. |
| Conexión interna ST-LINK | PA2 TX / PA15 RX | USART2, 115200 bit/s, 8N1, hacia la PC. |

### Circuito local, repetido en A y B

```text
D9 -- 330 ohm -- switch de interrupción -- ánodo LED IR
                                          cátodo -- GND local

D6 <---- DO del sensor de flama
A0 ----> S del módulo buzzer pasivo
A1 <---- DO del micrófono KY-037

VCC / + de los módulos ---- 3V3 local
GND / - de los módulos --- GND local
```

### Relojes del esquema actual

Se utilizan dos interfaces, U1 para A→B y U2 para B→A. Sus terminales son: 1 entrada positiva, 2 retorno de entrada, 3 emisor de salida y 4 colector de salida.

| Terminal | U1: reloj A→B | U2: reloj B→A |
|---|---|---|
| 1 | D11 de A mediante 330 ohm. | D11 de B mediante 330 ohm. |
| 2 | GND de A. | GND de B. |
| 3 | GND de B. | GND de A. |
| 4 | Directamente a A6 de B. | Directamente a A6 de A. |
| Pull-up de salida | 4.7 kohm desde el nodo 4/A6 a 3V3 de B. | 4.7 kohm desde el nodo 4/A6 a 3V3 de A. |

La salida queda alta en reposo y baja durante el pulso. El receptor normaliza esa polaridad a un evento lógico activo. No se unen las salidas 3V3 de ambas NUCLEO.

## 5. Trama lógica y variante de la base

La estructura conserva los campos de la base del proyecto:

```text
SYN → SFD → Control → DATA → CRC → FIELD
 4      4       4        8      8       4 bits
```

| Campo | Contenido | Función |
|---|---|---|
| SYN | `1111` | Sincronización inicial. |
| SFD | `0000` | Delimitar la entrada a las rondas de datos. |
| Control | `TTSS` | Tipo de trama y secuencia. |
| DATA | Un byte | Unidad de información de exactamente 8 bits. |
| CRC | CRC-8 | Detección de errores del cuerpo recibido. |
| FIELD | `1010` | Constante adicional que debe coincidir. |

Son 32 bits en la estructura lógica. El cuerpo de cada byte es:

```text
Control(4) + DATA(8) + CRC(8) + FIELD(4) = 24 bits
```

SYN/SFD se intercambian al abrir el turno de una trama. La realización física agrega CFG, aceptaciones, encabezados de ronda, primados y paridades. Por ello, esos 32 bits lógicos no equivalen a 32 pulsos de reloj.

### Cuatro tipos de trama

| TT | Tipo | Significado |
|---|---|---|
| `00` | INICIO | Primer byte de un mensaje codificado de varios bytes. |
| `01` | CONTINUACIÓN | Byte intermedio. |
| `10` | FIN | Último byte. |
| `11` | ÚNICA | Unidad codificada que ocupa un solo byte. |

SS avanza módulo 4. El receptor verifica la secuencia y los límites de mensaje. Existe además un bit alternante por ronda, independiente de SS, para reconocer repeticiones de trabajo.

### CRC implementados

El CRC se calcula sobre dos bytes: Control extendido con ceros a 8 bits y DATA. FIELD se verifica además contra `1010`.

| Selección | CRC-8 | Polinomio usado | Init | XOR final |
|---|---|---|---|---|
| 0 | SMBUS | `0x07`, no reflejado | `0x00` | `0x00` |
| 1 | AUTOSAR | `0x2F`, no reflejado | `0xFF` | `0xFF` |
| 2 | SAE-J1850 | `0x1D`, no reflejado | `0xFF` | `0xFF` |
| 3 | MAXIM-DOW | `0x8C` reflejado, equivalente al normal `0x31` | `0x00` | `0x00` |

Ambos extremos deben elegir el mismo algoritmo. El CRC se evalúa al completar el cuerpo y detecta errores; la reconstrucción durante la transmisión corresponde a otros mecanismos.

## 6. Presentación y transporte de mensajes

La aplicación permite UTF-8 con caracteres de 1, 2, 3 y 4 bytes, o Extended ASCII mediante Windows-1252. La representación es seleccionable y debe coincidir en ambos extremos.

Un carácter Unicode puede ocupar varias tramas; cada DATA sigue transportando un byte. El límite del mensaje es **185 bytes originales**, no 185 caracteres. La interfaz de entrada es de una línea y reserva los caracteres de control necesarios para el transporte.

El firmware empaqueta los bytes, agrega la delimitación del mensaje y usa escape cuando corresponde. La compresión es Heatshrink, con ventana de 256 bytes y anticipación de 16 bytes. Se intenta para entradas de al menos 8 bytes y se usa únicamente si reduce el paquete completo. Primero se reconstruye/descomprime el mensaje y después se interpreta su codificación de texto.

El cuerpo de 24 bits se divide en cuatro bloques de seis. Cada bloque se convierte en ocho posiciones mediante dos paridades. Las etapas de trabajo del enlace son:

| Etapa | Función |
|---|---|
| BEGIN | Abrir el bloque e identificarlo. |
| DATA | Transportar sus posiciones por los medios disponibles. |
| CHECK | Comprobar y aceptar el bloque o solicitar reparación. |
| REPAIR | Indicar una posición que se necesita reparar. |
| REPAIR_DATA | Enviar esa posición y volver a la comprobación. |

Las posiciones no confirmadas pueden repararse selectivamente. Si la reparación local no basta, puede repetirse un bloque. Un CRC inválido hace reparar bloques del cuerpo conservado, comenzando por el último y recorriendo otros si es necesario. No se vuelve a encolar todo el mensaje de chat.

La secuencia alternante y la respuesta guardada de una ronda permiten responder a duplicados sin volver a ejecutar su contenido. La secuencia de trama evita entregar dos veces el mismo byte.

## 7. Negociación, disponibilidad y arbitraje

### Escucha previa

Se observan los últimos 20 ms. La condición implementada es:

```text
libre = reloj entrante inactivo
        Y [(DO_IR alto Y flancos IR <= 1)
           O flancos de sonido < umbral]
```

El umbral acústico por defecto es 60 para A y 90 para B. La actividad se obtiene restando el contador de hace 20 ms al contador actual. Esta condición permite solicitar turno si uno de los medios parece disponible.

### Handshake

| Paso | Solicitud / respuesta | Condición |
|---|---|---|
| 1 | SYN=`1111` + CFG | Solicitante en banda baja ascendente. |
| 2 | SYN-ACK devuelve CFG | Receptor en banda alta descendente; debe coincidir con la propuesta. |
| 3 | SFD=`0000` | Solicitante delimita el inicio del cuerpo. |
| 4 | SFD-ACK devuelve CFG invertido | Debe coincidir con `CFG XOR 1111`. |

CFG tiene dos bits de perfil, uno de permiso de Turbo y uno de paridad. Se exige que el XOR de los cuatro bits sea cero. La negociación comunica la temporización antes de comenzar datos.

SYN/SFD emplean símbolos físicos de dos bits. SYN ocupa dos símbolos `3,3`; SFD ocupa dos símbolos `0,0`. El mismo sistema de barridos representa los demás campos y respuestas.

Si dos medios devuelven símbolos válidos contradictorios durante el inicio, el intercambio se rechaza. Un medio válido puede sostenerlo. Si no hay aceptación válida, no se envía el cuerpo de datos pendiente.

### Colisiones y espera

Si ambos piden transmitir, el reloj cruzado permite resolver la coincidencia. Dentro de una ventana de 2 ms gana A y B cede. B conserva su mensaje. Fuera del empate se utiliza la precedencia observada del primer flanco.

| Parámetro | Valor |
|---|---|
| Timeout de aceptación | 1100 ms por etapa supervisada por el MAC. |
| Backoff | `40 + ((PRNG >> 24) mod 101)` ms: entre 40 y 140 ms. |
| Falta de encabezados válidos durante turno | 5000 ms antes de perder el enlace y resincronizar. |
| Liberación | Tres pulsos cortos de 2 ms. |

El acceso vuelve a negociarse después de cada trama de un byte. A/B no fija quién será siempre transmisor o receptor; también determina los valores iniciales del umbral de escucha.

## 8. Rondas, fases y reloj

Una ronda, o quantum, tiene cuatro fases. Cada fase contiene un barrido de tres escalones:

| Fase | Contenido |
|---|---|
| H0 | Clase de ronda y secuencia alternante. |
| H1 | Máscara de medios o clase de operación de control. |
| DATOS | Bits de posiciones diferentes de la matriz, o argumento de control. |
| RETORNO | Complementos de bits o estados ACK/NACK. |

Son doce escalones por ronda, más el margen restante del período. H0/H1 se repiten en ambos medios; en DATOS los bits pueden ser diferentes.

| Perfil | Período de ronda | Duración del escalón | Turbo Solo-IR |
|---|---|---|---|
| Demostración / `log` | 1000 ms, 1 Hz | 75 ms | Deshabilitado. |
| Rápido / `max` | 800 ms, 1.25 Hz | 60 ms | Ronda de 400 ms; escalón IR de 30 ms. |
| `1` | 1000 ms | 75 ms | Ronda de 500 ms; escalón IR de 37 ms por división entera. |
| `0.5` | 2000 ms | 150 ms | Ronda de 1000 ms; escalón IR de 75 ms. |

En demostración, `12 × 75 = 900 ms` de fases dejan aproximadamente 100 ms de margen. **1 Hz significa una ronda cada segundo**, mientras que la portadora IR/acústica tiene otras frecuencias.

SYN y SFD conservan escalones de 75 ms en todos los perfiles: sus marcas avanzan aproximadamente a 13.33 Hz. El primer pulso de cada paquete identifica la etapa:

| Etapa | Anchura del primer pulso |
|---|---|
| SYN | 12 ms. |
| SYN-ACK | 20 ms. |
| SFD | 28 ms. |
| SFD-ACK | 32 ms. |

Se admite tolerancia de 2 ms para reconocer esas marcas. Los pulsos de escalones posteriores duran 37 ms. El marcado ayuda a alinear los tres escalones con el paquete correcto.

## 9. Barridos de frecuencia: representación de información

Cada símbolo se representa con tres frecuencias sucesivas. La banda baja es ascendente y la alta descendente. La banda corresponde al rol del turno: ida del solicitante o retorno del receptor.

En la fase DATOS cada canal aporta un bit, usando símbolos 0/1. Los símbolos 2/3 se aprovechan en encabezados y controles. La existencia de cuatro símbolos de control no agrega cuatro bits de usuario por canal.

### Banco normal

| Símbolo | IR bajo, Hz | IR alto, Hz | Sonido bajo, Hz | Sonido alto, Hz |
|---|---|---|---|---|
| 0 / `00` | 80,100,120 | 400,350,300 | 2700,2800,2900 | 4100,4000,3900 |
| 1 / `01` | 80,120,160 | 400,300,200 | 2700,2900,3000 | 4100,3900,3700 |
| 2 / `10` | 80,140,180 | 400,330,260 | 2700,3000,3100 | 4100,3800,3600 |
| 3 / `11` | 80,160,200 | 400,280,220 | 2700,3100,3200 | 4100,3700,3500 |

Los bits 0 y 1 conservan la misma dirección dentro de una banda; se distinguen por su patrón de saltos. Ambos valores se emiten mediante barridos activos.

### Banco IR de Turbo

| Símbolo | IR bajo, Hz | IR alto, Hz |
|---|---|---|
| 0 | 200,240,300 | 400,350,300 |
| 1 | 200,280,340 | 400,320,260 |
| 2 | 200,300,360 | 400,300,240 |
| 3 | 200,320,380 | 400,280,220 |

La frecuencia mínima IR sube para conservar suficientes períodos medibles cuando se acortan los escalones. El sonido mantiene su banco de frecuencias.

### Generación de las portadoras

Los temporizadores trabajan con contador de 1 MHz:

```text
f_contador = 8 MHz / (PSC + 1), con PSC = 7
P = redondear(1 000 000 / f_deseada)
ARR = P - 1
CCR1 ≈ P/2 al emitir
```

El PWM tiene aproximadamente 50% de ciclo útil. La frecuencia real queda cuantizada por el período entero: por ejemplo, 2700 Hz usa unas 370 cuentas y genera aproximadamente 2702.7 Hz.

## 10. Medición, filtrado y reconstrucción local

### Capturas independientes

IR se captura con TIM3 CH4 en PB1. El micrófono se observa por interrupciones en PA1, midiendo períodos de flancos ascendentes. El contador temporal tiene resolución de 1 µs.

```text
f_medida = cantidad_de_períodos × 1 000 000 / suma_de_períodos_en_µs
```

En sonido se estima la frecuencia con períodos compatibles con la banda esperada. El conteo de densidad conserva los flancos crudos, para que ese filtrado no oculte actividad irregular.

### Ventana útil

| Duración del escalón | Guarda inicial |
|---|---|
| 100 ms o más | 25 ms. |
| Desde 50 hasta menos de 100 ms | 12 ms. |
| Menos de 50 ms | 5 ms. |

También se excluyen los últimos 4 ms:

```text
T_útil_ms = T_escalón_ms - guarda_ms - 4
```

Esto evita mezclar el transitorio inicial y el cambio al escalón siguiente. El filtro digital de entrada IR usa ocho muestras con divisor 32: a 8 MHz son aproximadamente 32 µs. Si hay desbordamiento de captura, esa ventana se invalida.

Se rechazan períodos generales fuera de 100-55000 µs. Para la medición acústica se aplica además un intervalo entre 90% del menor período esperado y 110% del mayor período esperado para esa banda/escalón.

### Densidad de flancos

```text
N_esperado = redondear(f_medida × T_útil_ms / 1000)
|N_real - N_esperado| <= techo(0.35 × N_esperado) + 2
```

Se requieren al menos tres períodos y tres flancos esperados. En IR se limita además la cantidad de períodos inválidos a `2 + parte_entera(N_real/10)`.

### Clasificación del patrón

| Criterio | Condición |
|---|---|
| Frecuencia | Error relativo respecto al patrón no mayor que 1.2%. |
| Dirección | Crecimiento mayor que 1.5% en banda baja o disminución mayor que 1.5% en banda alta. |
| Salto entre escalones válidos | Error relativo de la diferencia de frecuencia no mayor que 45%. |
| Identificación | Debe coincidir un único patrón. |

La comprobación de dirección evita convertir una contradicción físicamente válida en un borrado conveniente. Se combinan densidad, frecuencia y patrón; una señal aparentemente ascendente no basta para aceptarla.

### Reconstrucción 2 de 3

Si un escalón queda inutilizable, los otros dos pueden determinar el símbolo:

```text
m = (f_j - f_i) / (t_j - t_i)
```

Los tiempos son los centros de las ventanas válidas. Si falta el escalón intermedio, el salto temporal comprende dos intervalos.

La implementación calcula la pendiente para observación y comprueba las frecuencias y el salto esperado de los escalones válidos contra el banco de patrones. Si la coincidencia es única, reconstruye localmente el símbolo. Ese éxito no suspende el canal.

| Situación | Resultado |
|---|---|
| Un escalón perdido y dos compatibles con un único patrón | Reconstrucción local. |
| Dos o tres escalones perdidos | Símbolo inválido. |
| Silencio, dirección contradictoria o salto incompatible | Símbolo inválido. |
| Más de un patrón compatible | Se rechaza por ambigüedad. |

El mismo método de barrido se utiliza para datos, encabezados, sincronización, retornos y pilotos.

## 11. Primados y matriz: validación durante la transmisión

### Bit y primado

El receptor devuelve el complemento del bit recibido:

| Bit | Retorno esperado | Validación |
|---|---|---|
| 0 | 1 | `0 XOR 1 = 1`. |
| 1 | 0 | `1 XOR 0 = 1`. |

El emisor comprueba el retorno que recibe. Así conoce qué posiciones quedaron confirmadas durante las rondas. Un retorno inválido actualiza la salud del canal y conserva el trabajo necesario para la recuperación.

En controles, las respuestas se interpretan como estados:

| Valor | Significado |
|---|---|
| 0 | ACK. |
| 1 | Bloque no reconstruible: reparar. |
| 2 | Trama, CRC o estado inválido. |
| 3 | Sin aceptación válida. |

H0 indica si se trata de datos o control, de modo que el significado del retorno depende de la clase de ronda.

### Codificación matricial

Cada bloque de seis bits se convierte en ocho posiciones:

| Fila lógica | Ronda 1 | Ronda 2 | Ronda 3 | Paridad |
|---|---|---|---|---|
| IR | i1 | i2 | i3 | pIR |
| Sonido | s1 | s2 | s3 | pSND |

```text
pIR  = i1 XOR s2 XOR i3
pSND = s1 XOR i2 XOR s3
```

El orden de distribución de los seis bits de entrada es `i1, s2, i3, s3, i2, s1`. Las ecuaciones cruzan las filas, por lo que los dos bits de una misma ronda pertenecen a grupos de paridad distintos.

Una incógnita de una ecuación se obtiene haciendo XOR de sus otros tres miembros. Si se pierden ambos bits de una ronda, puede recuperarse uno con cada ecuación. Si hay dos incógnitas en una misma ecuación, la paridad sola no alcanza.

Ejemplo:

```text
Antes de la pérdida:
IR      [1, 0, 0, 1]
Sonido  [1, 0, 1, 0]

Si se pierde la ronda 1:
i1 = pIR  XOR s2 XOR i3 = 1 XOR 0 XOR 0 = 1
s1 = pSND XOR i2 XOR s3 = 0 XOR 0 XOR 1 = 1
```

El receptor mantiene máscaras de posiciones conocidas y reconstruidas. No convierte automáticamente una posición ausente en cero. Si no puede reconstruir, solicita reparación; el CRC verifica finalmente el cuerpo completo.

Las filas son lógicas: cuando un medio falla, el otro puede transportar posiciones de ambas filas sin cambiar las ecuaciones.

## 12. Suspensión, redistribución y recuperación de canales

| Evento | Comportamiento |
|---|---|
| Retorno físico inválido/incoherente | Retira el medio de la máscara activa y reinicia su contador de aciertos. |
| Medio suspendido | El otro medio transporta las posiciones de usuario pendientes. |
| Comprobación/piloto correcto | Incrementa los aciertos consecutivos del medio observado. |
| Comprobación incorrecta | Vuelve a cero la cuenta de aciertos. |
| Tres comprobaciones correctas consecutivas | Reincorpora el medio. |

La máscara de datos es `01` para IR, `10` para sonido y `11` para ambos. Con dos medios se avanzan dos posiciones por ronda DATOS; con uno se avanza una. Los encabezados y argumentos de control se transmiten redundantemente por los medios disponibles.

Una copia válida del encabezado permite continuar. Si las dos copias son válidas pero contradictorias, se rechazan. Los pilotos permiten observar un canal aunque esté suspendido para carga útil.

Si fallan ambos medios no hay avance de datos. Se conserva el trabajo y se busca recuperar el enlace. El diseño necesita su reloj: no implementa un reloj autónomo de respaldo ante su pérdida permanente.

## 13. Turbo Solo-IR y piloto acústico

Turbo se habilita cuando la configuración lo permite y la máscara activa queda únicamente en IR.

```text
Con ambos medios: capacidad de la fase DATOS = 2/T_base
Solo IR con Turbo: T_nuevo = T_base/2
Capacidad de esa fase = 1/(T_base/2) = 2/T_base
```

En rápido normal, `T_base=800 ms`. Turbo usa rondas de 400 ms y escalones IR de 30 ms. El perfil demostración conserva siempre sus rondas de 1000 ms, incluso al perder sonido.

### Piloto del sonido sobre dos rondas

El sonido suspendido sigue siendo comprobado sin obligarlo a usar los escalones IR de 30 ms:

```text
T_escalón_piloto = 2 × T_escalón_base
T_par_de_rondas_Turbo = 2 × T_nuevo = T_base

En rápido: escalón del piloto = 120 ms; par de rondas = 800 ms
```

En la primera ronda del par se envía el piloto; en la segunda el otro extremo devuelve su complemento. Los cambios de Turbo se coordinan con ese par para no cortar una comprobación a la mitad.

### Señalización mediante la anchura del reloj

| Ronda | Anchura de pulso | Ejemplo con base de 800 ms |
|---|---|---|
| Normal | `T_base/20` | 40 ms. |
| Turbo, primera ronda del par | `T_base/40` | 20 ms. |
| Turbo, segunda ronda del par | `T_base/40 + 4 ms` | 24 ms. |

El receptor reconoce Turbo por un ancho menor que tres cuartas partes del pulso normal. Distingue la segunda ronda con el umbral `T_base/40 + 2 ms`. Así conoce el período y la fase del piloto sin un cambio unilateral de velocidad.

Al recuperar el sonido, se vuelve a la temporización base y a la distribución entre dos medios.

## 14. Capacidad y fundamento temporal

Es necesario distinguir la capacidad de la fase DATOS del caudal de bytes de usuario.

En condiciones normales, cada bloque necesita BEGIN + cuatro rondas DATOS + CHECK: seis rondas. Cuatro bloques completan el cuerpo de 24 bits:

```text
T_cuerpo = 4 bloques × 6 rondas × Tq = 24Tq
Caudal DATA del cuerpo = 8/(24Tq) = 1/(3Tq) bit/s
```

| Perfil | Capacidad de la fase DATOS | Caudal DATA del cuerpo, antes de negociación |
|---|---|---|
| 1 Hz | 2 bit/s. | Aproximadamente 0.333 bit/s. |
| Rápido, 800 ms | 2.5 bit/s. | Aproximadamente 0.417 bit/s. |

La negociación, delimitación de mensajes y reparaciones agregan tiempo. Un carácter UTF-8 multibyte necesita varias tramas. La compresión reduce el tiempo cuando reduce la cantidad de bytes realmente enviados.

Para medir un escalón se necesita una cantidad suficiente de períodos:

```text
T_útil >= 3/f_mínima

IR normal rápido:
T_útil = 60 - 12 - 4 = 44 ms
80 Hz × 0.044 s = 3.52 ciclos

IR Turbo:
T_útil = 30 - 5 - 4 = 21 ms
200 Hz × 0.021 s = 4.2 ciclos
```

Esto fundamenta los perfiles configurados. No equivale a certificar una frecuencia máxima física universal, porque también intervienen los comparadores, el buzzer, el entorno y el montaje.

## 15. Observación del protocolo

El firmware genera eventos de barridos y rondas con frecuencias medidas, flancos, ventanas, símbolos, primados, posiciones de matriz, CRC, estado de canales y temporización. Las interrupciones los almacenan en un anillo de 16 posiciones, 15 utilizables, de 12 palabras de 32 bits por evento. El bucle principal los envía a la aplicación.

| Vista | Información fundamental |
|---|---|
| Chat | Mensajes en cola, confirmación del enlace y recepción del texto. |
| Protocolo | Trama, bit/primado, matriz, reconstrucciones, barridos, densidad y pendiente. |
| Registro | Negociación, rondas, CRC, ACK/NACK, reparaciones, medios activos y velocidad. |

La aplicación distingue TX planeada de RX observada. La vista del emisor muestra el retorno recibido; la del receptor muestra lo que preparó para devolver. Congelar la vista solo detiene su actualización visual. El JSON de sesión conserva eventos y líneas serie; el CSV conserva el registro legible.

Los contadores de eventos perdidos, errores de UART, desbordamientos y plazos temporales sirven para advertir si la observación quedó incompleta. La adquisición física no depende de la velocidad con que se redibuja la gráfica.

## 16. Archivos fundamentales y compatibilidad

La carpeta principal de entrega se llama `entregaFinal_cc8`.

| Archivo / carpeta | Contenido |
|---|---|
| `src/main.c` | Comandos de aplicación, envío y recepción de mensajes. |
| `src/hw.c` | Inicialización GPIO, temporizadores, UART y parámetros físicos. |
| `src/timing.inc` | Sincronización, rondas, handshake, pilotos y Turbo. |
| `src/capture.inc` | Captura de flancos, ventanas y medición de frecuencias. |
| `src/codec.c` | Bancos de frecuencias, clasificación y reconstrucción local. |
| `src/link.c` | Bloques, primados, secuencias, salud de canales y reparación. |
| `src/base/codec.c` | CRC, formación de trama, paridad y reconstrucción matricial. |
| `src/base/mac.c` | Acceso al medio, colisiones, arbitraje y temporizadores de solicitud. |
| `src/chat_codec.c` | Empaquetado y compresión. |
| `interfaz/` y `app.py` | Interfaz, interpretación de eventos, sesión local y servidor web. |

Existen dos proyectos con el mismo protocolo y los mismos GPIO. La diferencia relevante de compatibilidad es la polaridad de recepción del reloj:

| Proyecto | Definición del firmware |
|---|---|
| `ESTACION.uvprojx` | `APP_RX_ACTIVE_LOW=0`: reloj recibido activo en alto. |
| `PROTO.uvprojx` | `APP_RX_ACTIVE_LOW=1`: reloj recibido activo en bajo. |

El esquema objetivo descrito en la sección 4 tiene recepción activa en bajo. Los nombres de proyecto son etiquetas de distribución y no deben intercambiarse por la apariencia del soporte físico. Elegir identidad A/B es una operación diferente de elegir la polaridad del reloj.

## 17. Puntos que debe conservar una explicación del proyecto

1. La trama lógica y el protocolo físico son niveles diferentes: describir SYN/DATA/CRC no explica por sí solo cómo se transmiten y recuperan los bits.
2. El paralelismo real está en los bits diferentes que llevan IR y sonido dentro de la misma ronda, y en su procesamiento conjunto mediante la matriz.
3. La validación durante la transmisión incluye clasificación del barrido, primados y paridades; el CRC es una verificación posterior del cuerpo.
4. La matriz recupera borrados localizados bajo sus límites algebraicos; no corrige cualquier combinación de errores desconocidos.
5. El protocolo adapta la máscara de canales, conserva trabajo pendiente y repara posiciones/bloques antes de entregar el byte.
6. Turbo duplica la frecuencia de las rondas IR y mantiene el piloto acústico sobre dos rondas; el modo demostración permanece a 1 Hz.
7. Los tiempos y tolerancias se fundamentan en ventanas de medición, cantidad de períodos y condiciones reales del montaje.
8. La aplicación web y la conexión USB sirven para interactuar y observar; el enlace de datos entre tarjetas sigue siendo físico.
