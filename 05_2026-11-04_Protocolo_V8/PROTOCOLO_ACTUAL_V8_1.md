**Protocolo de comunicacion del proyecto — V8.1**

Este documento describe la version actual implementada en las dos NUCLEO-F303K8.

**1. Que hace el sistema**

El sistema permite conversar entre dos terminales usando dos placas, llamadas A y B. Ambas pueden enviar y recibir al mismo tiempo: es una comunicacion full duplex.

Cada terminal se comunica por USB con su placa. Los mensajes entre las placas viajan por infrarrojo y sonido. Tambien hay dos enlaces de reloj por cable, uno para cada sentido, mediante los PC817. El reloj indica cuando debe leer el receptor cada paso de la transmision.

El mismo programa se carga en ambas placas. Elegir A o B identifica la terminal; ambas tienen las mismas capacidades.

**2. Como representan los bits los medios**

| Medio | Bit 0 | Bit 1 |
|---|---|---|
| Infrarrojo | LED IR apagado | LED IR encendido |
| Sonido | Silencio | Tono de 3000 Hz |

Cuando ambos medios funcionan, cada uno aporta un bit por intervalo en el cuerpo de una trama de datos:

| IR | Sonido | Pareja transmitida |
|---|---|---|
| 0 | 0 | 00 |
| 0 | 1 | 01 |
| 1 | 0 | 10 |
| 1 | 1 | 11 |

Por ejemplo, un byte `01001000` se puede repartir en `01 / 00 / 10 / 00`. En cada pareja, el primer bit viaja por IR y el segundo por sonido. Asi se transportan dos bits nuevos por intervalo.

**3. Como es una trama**

Un mensaje se divide en unidades pequenas llamadas tramas. Su formato logico es:

```text
SYN | SFD | CONTROL | DATA | CRC
 4     4       4        8      8 bits
```

| Campo | Valor o contenido | Funcion |
|---|---|---|
| SYN | 1111 | Permite reconocer el comienzo. |
| SFD | 0000 | Marca el final de la secuencia inicial. |
| CONTROL | Tipo y numero de secuencia | Indica como interpretar la trama. |
| DATA | Un byte | Lleva texto, datos comprimidos o informacion de control. |
| CRC | Comprobacion de 8 bits | Ayuda a detectar errores en CONTROL y DATA. |

Son 28 bits logicos. Con ambos medios sanos, DATA y CRC de las tramas de texto se reparten entre IR y sonido. SYN, SFD y CONTROL se repiten por ambos medios.

Las tramas ACK, NACK y LINK se mandan completas por ambos medios. Asi, una respuesta puede seguir llegando si uno deja de funcionar.

CONTROL se divide en `TT SS`:

| TT | Tipo | Significado |
|---|---|---|
| 00 | DATA | Transporta un byte del mensaje. |
| 01 | ACK | Confirma datos recibidos correctamente. |
| 10 | NACK | Solicita repetir un dato pendiente. |
| 11 | LINK | Comprueba los medios o acuerda un cambio. |

En DATA, ACK y NACK, SS identifica una secuencia entre 0 y 3. Los numeros se reutilizan en orden: `0, 1, 2, 3, 0...`. En LINK, esos bits relacionan una solicitud con su respuesta.

Por ejemplo, una trama DATA con la letra H, secuencia 0 y CRC SMBUS es:

```text
1111 | 0000 | 0000 | 01001000 | 11111111
 SYN    SFD   CTRL       H         CRC
```

**4. Confirmaciones y retransmisiones**

Se usa Selective Repeat con una ventana de dos: el emisor puede tener hasta dos tramas de datos pendientes de confirmacion. El receptor guarda las correctas y entrega los bytes en orden, aunque tenga que esperar uno anterior.

Si falta una trama, se solicita repetir esa trama. Si se pierde su confirmacion, el emisor vuelve a intentarlo tras un timeout de 3 segundos desde el fin de su transmision. El receptor reconoce el duplicado, vuelve a confirmarlo y evita entregar otra vez el mismo byte al chat.

El ACK agrupado permite confirmar dos secuencias consecutivas con una sola respuesta. Su DATA se interpreta asi:

```text
0000 RR AA
```

AA indica cuales de las dos secuencias se confirman; RR indica cuales se solicita repetir, tomando SS como primera secuencia. Por ejemplo:

- SS=0 y DATA=`00000011`: confirma las secuencias 0 y 1.
- SS=0 y DATA=`00000110`: pide repetir 0 y confirma que 1 ya llego.

La agrupacion aprovecha confirmaciones pendientes; no introduce una espera fija en todos los mensajes. Los NACK, los duplicados y el final del mensaje se atienden sin ceder el turno a otra trama DATA.

**5. Que hace el CRC**

El emisor calcula un valor a partir de CONTROL y DATA. El receptor repite el calculo y compara el resultado con el CRC recibido. Si no coincide, la trama se considera incorrecta.

El CRC detecta errores; la recuperacion se realiza mediante NACK, temporizadores y retransmisiones. Tambien se rechazan tramas con inicio o longitud invalidos.

Se pueden elegir CRC-8 SMBUS, AUTOSAR, SAE-J1850 o MAXIM-DOW. Ambas placas deben usar la misma variante. La habitual es SMBUS. Esta seleccion se configura manualmente con las placas detenidas y sin pendientes.

**6. Comprobacion y cambio de medios**

Se envia una trama LINK con el patron conocido `00111100`: una parte A=`0011` y su complemento A'= `1100`. Se transmite completo por los dos medios y se comprueba por separado cual entrego correctamente esa trama.

El receptor responde si funcionaron ambos medios, solo IR o solo sonido. La frecuencia de estas comprobaciones es:

- Con ambos medios sanos: cada 32 tramas DATA nuevas o despues de 2 segundos sin actividad de datos.
- Ante NACK o timeout: se adelanta una comprobacion.
- Con un medio apartado: se mantienen comprobaciones cada 2 segundos para detectar su regreso.

Son plazos de programacion: una trama que ya esta transmitiendose termina antes de iniciar otra. Las 32 DATA se cuentan sobre los bytes del enlace, incluidos los comprimidos.

Dos comprobaciones consecutivas fallidas apartan el medio afectado. Si falla IR, el mensaje continua por sonido; si falla sonido, continua por IR. Con un solo medio, todos los bits de DATA y CRC pasan por ese medio, por lo que el envio es mas lento.

El cambio se acuerda: el receptor prepara el nuevo modo y lo confirma; el emisor empieza a usarlo cuando recibe esa confirmacion. Los datos pendientes se conservan. Cada sentido tiene su propio estado: A->B puede estar usando solo sonido mientras B->A conserva ambos medios.

Para reincorporar un medio se necesitan tres comprobaciones buenas consecutivas y un nuevo acuerdo de modo.

Estos mensajes LINK usan el campo DATA de la siguiente manera:

| Contenido | DATA |
|---|---|
| Solicitar modo | 0000 MMMM |
| Confirmar modo | 0001 MMMM |
| Comprobar medios | 00111100 |
| Informar resultado | 0010 MMMM |

MMMM=0000 significa ambos; 0001, solo IR; 0010, solo sonido. SS permite reconocer la respuesta correspondiente a la solicitud pendiente.

**7. Compresion y reconstruccion del mensaje**

Antes de dividir el texto en tramas, se intenta comprimir con heatshrink, sin perdida de contenido. Solo se usa el resultado si ocupa menos bytes contando encabezado, escapes y terminador. En caso contrario, se envia normalmente.

El mensaje normal termina con LF, un marcador de final:

```text
texto + LF
```

Un mensaje comprimido lleva una pequena envoltura:

```text
ESC + C + longitud original + longitud comprimida + contenido + LF
```

ESC indica que viene un formato especial y C significa comprimido. Para evitar que un byte del contenido se confunda con el final, dentro de esa envoltura LF se representa como `ESC 0` y ESC como `ESC 1`. Si hace falta envolver un mensaje sin comprimir porque empieza con ESC o contiene LF, se usa la etiqueta R.

Cada byte de esa envoltura sigue viajando en tramas DATA normales, con CRC y retransmisiones. El receptor reconstruye los bytes, verifica las longitudes, descomprime cuando corresponde y muestra el mensaje completo una sola vez.

El limite actual es 185 bytes originales por mensaje. Se admite UTF-8, incluidos caracteres que ocupan varios bytes, o ASCII extendido CP1252 si ambas terminales usan esa codificacion. Por eso 185 bytes no siempre equivalen a 185 caracteres.

**8. Tiempos y mejoras de V8.1**

| Parametro | Valor |
|---|---|
| Tono para representar sonido=1 | 3000 Hz |
| Intervalo de SYN y SFD | 20 ms |
| Intervalo de CONTROL, DATA y CRC | 40 ms |
| Separacion minima entre tramas | 80 ms |
| Timeout de confirmacion | 3 segundos |
| Ventana de datos | 2 tramas |

DATA y CRC suman 16 bits: ocupan ocho intervalos usando ambos medios o 16 intervalos usando uno. Una trama DATA usando ambos medios dura 640 ms; usando uno, 960 ms. ACK, NACK y LINK duran 960 ms.

La separacion de 80 ms se agrega entre tramas. El receptor cierra la captura al pasar 60 ms sin un nuevo inicio de simbolo. Cada direccion tiene su propio reloj, por lo que esa pausa no detiene la transmision contraria.

V8.1 permite avanzar datos mientras espera una respuesta de comprobacion. Al acordar un cambio de medio, mantiene detenidos los datos de esa direccion hasta recibir confirmacion. Tambien aprovecha ACK agrupados y evita comprobaciones ordinarias innecesarias durante actividad sana, conservando las urgentes y las de recuperacion.

En las pruebas, dos mensajes simultaneos de 16 bytes quedaron confirmados en 19.9 s frente a 34.5 s con el planificador anterior. Un texto repetitivo de 35 bytes paso de 36 a 12 bytes DATA y de 37.5 a 12.4 s para mostrarse en A->B. El ahorro de compresion depende del contenido.

**9. Ejemplo de recuperacion**

1. A empieza a enviar un mensaje a B.
2. Se tapa IR mientras el mensaje esta en curso.
3. Una trama incorrecta o una comprobacion permite detectar el problema.
4. El protocolo acuerda continuar por sonido y repite los datos pendientes.
5. Al destapar IR, las comprobaciones verifican que volvio a funcionar.
6. Tras tres resultados buenos, acuerdan usar ambos medios otra vez.
7. B muestra el texto completo, sin repetir partes que ya habia recibido.

**10. Uso y limites actuales**

En ambas terminales se activa la comprobacion automatica y se inicia el protocolo:

```text
/auto 1
/start
```

Para conversar se usa `/send Hola`. `/status` muestra el estado, `/menu` las opciones y `/stop` detiene los emisores conservando pendientes en RAM. `/compress 0|1` desactiva o activa el intento de compresion para los siguientes mensajes. La configuracion habitual usa planificador nuevo, ACK agrupado y compresion automatica.

La conexion local entre terminal y placa usa 115200 baudios, 8 bits, sin paridad y un bit de parada (8N1). Los tiempos de IR y sonido son los de la tabla anterior. La codificacion de texto se configura igual en ambas terminales.

Si ambos medios de datos fallan, no hay una ruta util: los pendientes se mantienen en RAM para reintentarlos cuando vuelva una ruta disponible. Apagar o reiniciar la placa pierde ese estado. Actualmente, si se reinicia una K8, se reinician ambas para comenzar una nueva sesion.

La recuperacion automatica descrita cubre IR y sonido. Los relojes cableados siguen siendo necesarios y no tienen un respaldo automatico implementado.
