# Plan de armado: dos NUCLEO-F303K8

Fecha: 24 de octubre de 2026.
Actualizacion del diagnostico: 31 de octubre de 2026, version V5 con tono unico de 2400 Hz.

Este documento contiene la lista de componentes y los esquemas del montaje.
No define todavía las tramas ni el programa completo de chat.

Este armado aplica las aclaraciones del auxiliar reportadas por el usuario:
para tres canales se permiten dos medios no convencionales más el reloj
cableado; el reloj debe pasar por optoacoplador. El usuario confirmó también
que el auxiliar autorizó usar terminales en lugar del Web Server del PDF base.

Con la compra adicional de la sección 3 no se identifica otro componente
obligatorio para este montaje. Esto es una evaluación de los materiales
previstos, no una certificación del proyecto terminado: siguen pendientes la
prueba del reloj entre ambas NUCLEO, las mediciones del enlace y el protocolo
completo. IR y sonido ya pasaron pruebas funcionales con una sola NUCLEO.

## 1. Qué vamos a construir

Dos estaciones iguales, A y B. Cada estación tendrá un emisor y un receptor
infrarrojos, un buzzer pasivo, un micrófono KY-037 y un circuito receptor de reloj
con PC817. Primero se prueba en protoboard y después se pasa a una placa
perforada de 9 x 15 cm por estación.

La propuesta usa **dos enlaces de reloj**, uno A -> B y otro B -> A. Cada equipo
podrá generar su reloj cuando le corresponda transmitir. Si el auxiliar acepta
un único reloj maestro compartido, se puede reducir a un PC817, pero este armado
deja preparados ambos sentidos. Dos PC817 es una decisión de este diseño, no una
cantidad que el auxiliar haya especificado.

En cada sentido habrá tres canales: infrarrojo, sonido y reloj por optoacoplador.
Los conductores de retorno del reloj no son canales adicionales de datos.

```text
ESTACIÓN A                                      ESTACIÓN B

LED infrarrojo A          -- luz ----------->    Sensor de flama B
Buzzer pasivo A           -- sonido ------->    Micrófono KY-037 B
Salida de reloj A         -- PC817 A->B ---->    Entrada de reloj B

Sensor de flama A         <--------- luz --     LED infrarrojo B
Micrófono KY-037 A        <------ sonido --     Buzzer pasivo B
Entrada de reloj A        <---- PC817 B->A --    Salida de reloj B
```

## 2. Componentes que ya tenemos

Cantidades basadas en el último carrito y lo confirmado durante las pruebas.

| Componente | Disponibles | Uso en el montaje final |
| --- | ---: | --- |
| NUCLEO-F303K8 con ST-LINK | 2 | Una por estación |
| LED infrarrojo de 940 nm | 4 | 2 instalados y 2 de repuesto |
| Sensor de flama con DO | 2 | Uno por estación |
| Módulo buzzer **pasivo**, con driver | 3 | 2 instalados y 1 de repuesto |
| Sensor de sonido KY-037 | 3 | 2 instalados y 1 de repuesto |
| Resistencia 330 ohm, 1/4 W | 6 | 2 para LED IR y 2 para los PC817; quedan 2 |
| Placa perforada de una cara, 9 x 15 cm | 2 | Una por estación |
| Tira hembra de 40 contactos, paso 2.54 mm | 3 | Bases para NUCLEO y módulos |
| Tira macho de 40 contactos, paso 2.54 mm | 1 | Conectores según el armado |
| Jumpers macho-hembra de 20 cm | 20 | Conexión de módulos |
| Kit de 65 jumpers macho-macho | 1 | Pruebas en protoboard |
| Alambre, cautín y estaño | Ya disponibles | Soldadura y cableado final |
| LED rojos y módulos LDR | 2 de cada uno | Reserva; no son necesarios en este esquema |

También se necesitan dos cables USB de datos para conectar las NUCLEO a sus
terminales. Ya se está utilizando uno en las pruebas; disponer del segundo al
reunir ambas estaciones. Los teclados del otro proyecto no intervienen aquí.
Usar los protoboards que tenga disponible el equipo para las pruebas.

Las pruebas de infrarrojo y sonido con una NUCLEO ya funcionan, según lo
confirmado por el usuario. Falta probar el reloj con optoacoplador y el conjunto
entre las dos estaciones.

## 3. Compra adicional mínima para los relojes

| Componente | Cantidad a comprar | Precio publicado de referencia | Total |
| --- | ---: | ---: | ---: |
| **PC817 DIP-4, salida fototransistor** | 2 | Q4.00 | Q8.00 |
| **Resistencia 4.7 kΩ, 1/4 W** | 2 | Q0.50 | Q1.00 |
| Resistencia 330 ohm, 1/4 W | 0 si conservamos las seis compradas | Se reutilizan 2 | Q0.00 |
| **Compra mínima estimada** | | | **Q9.00, sin envío** |

Publicaciones consultadas el 24 de octubre de 2026:

- [PC817 en Electrónica DIY, SKU K166](https://www.electronicadiy.com/products/optoacoplador-pc817).
- [Resistencias por unidad Kilo-Ohms: elegir **4.7K**](https://www.electronicadiy.com/products/copia-de-resistencias-por-unidad-kilo-ohms-1-4w).

Los precios son los publicados; la ficha no permite asegurar el inventario de
la sucursal. Un tercer PC817 sería un repuesto opcional de Q4 adicionales.

Pedir específicamente **PC817 de cuatro patas para protoboard**. Una línea de la
tienda dice “PhotoTriac”, pero la descripción y la hoja de datos del PC817
corresponden a un **fototransistor**. No sustituirlo por MOC3021 ni por un optotriac.
Los módulos grandes anunciados para entradas desde 3.6 V no son la opción
seleccionada para nuestras señales de 3.3 V.

## 4. Qué hace el optoacoplador

Dentro del PC817 hay un LED infrarrojo y un fototransistor enfrentados. La NUCLEO
transmisora enciende el LED interno; su luz activa el fototransistor del lado
receptor. Así pasa el estado del reloj entre ambos circuitos.

**El PC817 no genera el reloj:** lo generará un temporizador de la NUCLEO. No
hace falta comprar un generador de reloj adicional para este diseño.

El PC817 tampoco tiene un pin VCC: su entrada se conecta como un LED con una
resistencia en serie; la salida utiliza una resistencia hacia 3.3 V del receptor.

| Pin PC817 | Función |
| ---: | --- |
| 1 | Ánodo del LED interno |
| 2 | Cátodo del LED interno |
| 3 | Emisor del fototransistor |
| 4 | Colector del fototransistor |

Identificar el pin 1 por la marca del encapsulado y el dibujo de su fabricante.
Con la orientación correcta, las parejas enfrentadas son 1-4 y 2-3. En
protoboard, colocar el integrado atravesando la ranura central.

Referencia: [hoja de datos de Sharp, diagrama de conexiones en página 2](https://global.sharp/products/device/lineup/data/pdf/datasheet/PC817XxNSZ1B_e.pdf).

## 5. Asignación de pines en ambas NUCLEO

Se mantiene el cableado que ya funcionó para infrarrojo y sonido.

| Función | Pin de la NUCLEO | Dirección |
| --- | --- | --- |
| LED infrarrojo propio | **D1 / PA9** | Salida |
| DO del sensor de flama propio | **A0 / PA0** | Entrada |
| Señal del buzzer pasivo propio | **D9 / PA8** | Salida PWM |
| DO del KY-037 propio | **A1 / PA1** | Entrada |
| Reloj hacia la otra estación | **D2 / PA12** | Salida propuesta |
| Reloj recibido desde la otra estación | **A2 / PA3** | Entrada propuesta |
| Alimentación local de módulos | **3V3** | Alimentación |
| Tierra local | **GND** | Referencia |

PA2 y PA15 quedan reservados para la terminal USB a través del ST-LINK. PA3
queda disponible para este reloj porque el COM virtual recibe por PA15.
Se evitan A4/A5 y D4/D5 por sus puentes de conexión en esta placa.

**Estado del programa:** V5 incluye menu A/B, IR, tono fijo de 2400 Hz/silencio,
salida de reloj por PA12 y lectura/conteo por PA3. Se confirmo V5 instalada en
ambas placas y se probaron IR y sonido con `b`, con respuesta en ambos sentidos.
Ambos relojes ya respondieron a HIGH/LOW y pulsos a 1/10/50/100/200 Hz despues
de intercambiar los PC817. Falta validar patrones de datos sincronizados y
medir errores; el programa no implementa todavia el chat completo.

Antes de usar D2 como salida de reloj, comprobar que no haya un puente entre
D2 y GND de la demostracion original (CN3 pines 5 y 4). Si existe, retirarlo
con los USB desconectados. JP1/IDD es distinto y debe quedar puesto.

## 6. Esquema local de cada estación

Repetir estas conexiones en A y en B. El subíndice X significa la estación local.
Cada estación alimenta sus módulos desde su propia NUCLEO.

### Emisor infrarrojo

```text
D1 / PA9_X ---- R_IR 330 ohm ---- ÁNODO LED IR
                                CÁTODO LED IR ---- GND_X
```

El ánodo suele ser la pata larga; el cátodo suele ser la pata corta y el lado
plano del encapsulado. La señal se envía desde **D1**, no desde A0.

### Receptor infrarrojo

```text
Sensor de flama_X           NUCLEO_X
VCC ---------------------- 3V3_X
GND ---------------------- GND_X
DO ----------------------- A0 / PA0_X
AO                         Libre
```

### Emisor de sonido

```text
Módulo buzzer PASIVO_X      NUCLEO_X
VCC / + ------------------ 3V3_X
GND / - ------------------ GND_X
S / Señal ---------------- D9 / PA8_X
```

Este esquema usa el módulo de tres pines con transistor incorporado que ya se
probó, no el buzzer suelto conectado directamente a un GPIO.

### Receptor de sonido

```text
KY-037_X                   NUCLEO_X
+ / VCC ------------------ 3V3_X
G / GND ------------------ GND_X
DO ----------------------- A1 / PA1_X
AO                         Libre
```

Conectar según las etiquetas de cada módulo: el orden físico de sus pines
puede variar. Los pines **AO** de ambos sensores quedan libres en este armado.

## 7. Esquema del reloj A -> B

El PC817 de este enlace se puede montar en la placa B. Su entrada recibe dos
conductores desde A; su salida se conecta únicamente a la alimentación y GPIO de B.

```text
LADO TRANSMISOR A                 PC817 A->B              LADO RECEPTOR B

D2 / PA12_A -- R_CLK_A 330 ohm --- pin 1 (ánodo)
GND_A -------------------------- pin 2 (cátodo)

                                 pin 4 (colector) -------+---- A2 / PA3_B
                                                        |
                                                   R_PU_B 4.7 kΩ
                                                        |
                                                      3V3_B

                                 pin 3 (emisor) ------------- GND_B
```

La unión entre pin 4, A2/PA3_B y un extremo de 4.7 kΩ es **un mismo nodo**.
El otro extremo de 4.7 kΩ va a 3V3_B. La resistencia no va en serie entre pin 4
y el GPIO.

## 8. Esquema del reloj B -> A

Repetir el circuito en espejo, con el segundo PC817 montado en la placa A.

```text
LADO TRANSMISOR B                 PC817 B->A              LADO RECEPTOR A

D2 / PA12_B -- R_CLK_B 330 ohm --- pin 1 (ánodo)
GND_B -------------------------- pin 2 (cátodo)

                                 pin 4 (colector) -------+---- A2 / PA3_A
                                                        |
                                                   R_PU_A 4.7 kΩ
                                                        |
                                                      3V3_A

                                 pin 3 (emisor) ------------- GND_A
```

### Niveles esperados

| Salida de reloj del transmisor | LED interno | Entrada de reloj del receptor |
| --- | --- | --- |
| LOW | Apagado | HIGH por la resistencia de 4.7 kΩ |
| HIGH | Encendido | LOW por el fototransistor |

Este circuito **invierte el reloj**. El firmware deberá considerar esa inversión
al elegir los flancos de recepción. Un punto inicial propuesto es TX en LOW y
RX en HIGH durante el reposo.

Con 330 ohm se esperan aproximadamente 6 mA en el LED interno; el pull-up de
4.7 kΩ exige alrededor de 0.7 mA al fototransistor cuando conduce. Son valores
iniciales de diseño: se comprobarán los niveles y los flancos en el montaje real.

### Alimentación y tierras

- No unir **3V3_A** con **3V3_B**: cada regulador alimenta su propia estación.
- En el enlace A -> B, el retorno GND_A llega al pin 2 del opto y no se une
  mediante ese cable al GND_B del pin 3. Aplicar lo mismo en sentido contrario.
- Si ambas NUCLEO usan USB del mismo PC, sus tierras pueden quedar unidas por
  el PC. El reloj sigue atravesando el opto, pero no se debe afirmar que todo el
  sistema tiene aislamiento galvánico completo.
- Para probar un PC817 con una sola NUCLEO se puede usar la misma alimentación
  y tierra en ambos lados: verifica funcionamiento, no aislamiento.

## 9. Orden de armado en protoboard

1. Con USB desconectado, conservar o reconstruir las conexiones IR y sonido ya
   probadas. Cada pata de un LED, resistencia o integrado debe quedar en el grupo
   de agujeros que indica el esquema, sin cortocircuitar sus extremos.
2. Añadir un PC817 con su resistencia de 330 ohm y su pull-up de 4.7 kΩ.
   Primero se podrá probar en una NUCLEO: D2 -> entrada del opto; salida -> A2.
3. Cargar V5 y seleccionar 1 = K8 A o 2 = K8 B. Comprobar el reloj con `h`
   (TX HIGH, RX LOW) y `c` (TX LOW, RX HIGH). Despues `k` inicia pulsos de 1 Hz;
   `f` permite subir la frecuencia. Activar las lecturas del receptor con `v`.
4. Reunir las dos NUCLEO y armar A -> B y B -> A, etiquetando los cuatro
   conductores: CLK_A, RETORNO_A, CLK_B y RETORNO_B.
5. Orientar LED IR A hacia sensor de flama B, y LED IR B hacia sensor de flama A.
   Evitar que los receptores queden apuntando principalmente al LED de su propia
   estación. Comenzar con distancias cortas y soportes que mantengan la alineación.
6. Colocar buzzer A frente a micrófono B y buzzer B frente a micrófono A, sin
   contacto entre módulos. Repetir el ajuste de sensibilidad para el nuevo montaje.
7. Validar cada sentido por separado antes de trasladar el circuito a perforada.

Con una sola NUCLEO se prueban los componentes usando sus propios emisores y
receptores. Para la disposición final, los receptores deben escuchar o mirar a
la **otra** estación.

## 10. Traslado a placa perforada

Por cada placa de 9 x 15 cm:

- Una NUCLEO desmontable sobre dos bases hembra de **15 contactos**.
- Un LED IR con 330 ohm, un sensor de flama, un buzzer pasivo y un KY-037.
- Un PC817 para recibir el reloj remoto y un pull-up local de 4.7 kΩ.
- Una resistencia de 330 ohm para enviar el reloj hacia el PC817 de la otra placa.
- Conectores identificados para reloj y retorno de cada sentido.

Dos tiras hembra de 40 contactos permiten obtener las cuatro bases de 15 para
las dos NUCLEO. La tercera se reserva para módulos y conexiones, considerando
que al cortar una tira hembra puede perderse un contacto por corte.

Dejar accesible el USB, RESET y los potenciómetros. No soldar permanentemente
las NUCLEO. En las placas de pads individuales, las conexiones se hacen con
alambre o puentes de soldadura: los agujeros vecinos no están unidos como en
protoboard. Separar claramente el retorno remoto que llega al LED del PC817 de
la tierra local de su fototransistor.

Los separadores o “patitas” son opcionales para sostener las placas y evitar
que las soldaduras apoyen sobre la mesa.

## Referencias

- [ST: manual de NUCLEO-32, conectores F303K8 y COM virtual](https://www.st.com/resource/en/user_manual/dm00231744-stm32-nucleo32-boards-mb1180-stmicroelectronics.pdf).
- [Sharp: PC817, funcionamiento y pinout](https://global.sharp/products/device/lineup/data/pdf/datasheet/PC817XxNSZ1B_e.pdf).
- [PC817 en la tienda donde se compraron los componentes](https://www.electronicadiy.com/products/optoacoplador-pc817).
- [Resistencias de 4.7 kΩ en esa tienda](https://www.electronicadiy.com/products/copia-de-resistencias-por-unidad-kilo-ohms-1-4w).
- [Buzzer pasivo con transistor incorporado](https://www.electronicadiy.com/products/modulo-buzzer).
- [KY-037 adquirido](https://www.electronicadiy.com/products/sensor-de-sonido-ky-038).
