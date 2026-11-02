# Primera prueba del protocolo en las dos NUCLEO

Version experimental del 2 de noviembre de 2026. El mismo programa sirve para ambas placas.
El proyecto anterior `Pruebas_Fisicas.uvprojx` y su firmware V6 se conservan.
La imagen actual es V7.2 (`BUILD=702`), con calibracion y ACK agrupado.
Ver [optimizacion de confirmaciones](OPTIMIZACION_ACK_V7_2.md).

## Cargar en Keil

1. Abrir **Protocolo_K8_V7.uvprojx**, target **Target_1**.
2. Compilar con F7. Debe terminar con cero errores y advertencias.
3. Seleccionar el ST-LINK de la primera placa y cargar con F8.
4. Seleccionar el otro ST-LINK y cargar el mismo proyecto con F8.
5. Salir del modo debug para que ambas ejecuten. No dejar una detenida en un breakpoint.

El ejecutable nuevo es `Objects\Protocolo_K8_V7\Protocolo_K8_V7.axf`.
No cargar el AXF de Pruebas_Fisicas ni el proyecto Lab10.
En Debug > ST-Link > Settings se puede cambiar la unidad/numero de serie con ambas USB conectadas.
El cableado permanece igual: D1 IR, A0 flama DO; D9 buzzer, A1 microfono DO;
D2 reloj TX por PC817 y A2 reloj RX desde PC817. VCP usa PA2/PA15.

## Para que hagamos las pruebas automaticas

Con los dos programas cargados, cerrar todas las terminales que ocupen los COM y pulsar
RESET en ambas placas. Dejar el montaje y los potenciometros fijos.
No es necesario abrir terminales: el script abre los dos puertos, identifica A/B y registra todo.

Los ultimos COM usados fueron A=COM3, B=COM5; pueden configurarse si cambiaron.

```powershell
.\probar_protocolo_v7.ps1 -PortA COM3 -PortB COM5 -Stage Basico
```

Primero comprobar texto A->B y B->A y la prueba conocida en ambos sentidos.
Despues ejecutar etapas independientes, reiniciando **ambas** placas antes de cada ejecucion:

| Etapa | Que prueba |
|---|---|
| Basico | Mensajes en ambos sentidos y comprobaciones de IR/sonido. |
| IR | Mensajes por IR solamente, en ambos sentidos. |
| Sonido | Mensajes por sonido solamente, en ambos sentidos. |
| Duplex | Mensajes enviados fisicamente al mismo tiempo. |
| CRC | CRC incorrecto intencional, deteccion y retransmision. |
| Timeout | Una confirmacion omitida, temporizador y descarte del duplicado. |
| UTF8 | Caracteres de 1, 2, 3 y 4 bytes. |
| Fallos | Apagado por software de cada emisor de A, cambio al medio sano y recuperacion. |
| Todo | Todas las etapas seguidas; se detiene al primer fallo. |

Las etapas Fallos afectan A->B por defecto. Repetir con `-FailureSource B`
para cubrir B->A sin cambiar la identidad de las placas.
Posteriormente repetir bloqueando fisicamente IR, desconectando solamente la senal/alimentacion
del modulo con los USB desconectados para recablear, y con ruido ambiental. La inyeccion por
software verifica el mecanismo, pero no sustituye esas pruebas fisicas.

El script deja los emisores apagados, restaura la mascara de fallos a cero, cierra ambos puertos
y escribe JSONL con comandos/respuestas y JSON con los resultados en `output\pruebas`.
Si falla, conserva el registro y los bytes pendientes en RAM; RESET de ambas inicia otra sesion.
Si una etapa termino correctamente y no quedan datos pendientes, se puede ejecutar la siguiente
con `-ContinueSession` para conservar las secuencias y evitar reiniciar las placas.
El script negocia el modo requerido por la nueva etapa antes de enviar mensajes.
`-CrcKind 0|1|2|3` selecciona y verifica la variante CRC en ambas K8 antes de empezar.
`-MicThresholdA` y `-MicThresholdB` permiten comparar umbrales sin girar los potenciometros
ni cargar otro firmware. El valor inicial de ambos es 60 flancos por 20 ms.
Para una tanda duplex mas larga, usar `-DuplexMessageA`, `-DuplexMessageB` y
`-DuplexSeconds 90`. El limite es 185 bytes UTF-8 por mensaje.
Agregar `-Automatic` para comprobar la conversacion con los diagnosticos periodicos
y el cambio automatico de medio activos en las dos K8. Sin este parametro, las etapas
de datos usan `/auto 0` para medir primero los medios sin cambios de configuracion.
`-GroupAck 0` usa ACK individual y `-GroupAck 1` el agrupado (valor por defecto).
Se cambia con las placas detenidas, sin datos ni controles pendientes.
Para comparar tandas automaticas, agregar `-PrimeProbe` en ambas: termina una
comprobacion conocida por sentido antes de activar el diagnostico periodico.

## Terminal manual

```powershell
.\terminal_protocolo_v7.ps1 -PortName COM3
.\terminal_protocolo_v7.ps1 -PortName COM5
```

Ejecutar cada comando en una ventana distinta. Elegir 1 para A y 2 para B.
Los comandos del menu llevan Enter; ESC solamente cierra el puerto.

Para una primera prueba controlada, escribir en **ambas**:

```text
/auto 0
/start
```

En A:

```text
/send Hola B
```

En B debe aparecer `[B] CHAT_RX Hola B`. La pantalla tambien muestra las tramas y confirmaciones.
Al final, `/status` permite revisar BAD, RETRY, TIMEOUT y DUP. El mensaje completo se muestra
al recibir su terminador; los registros de tramas pueden aparecer antes.
Con `/auto 1` se habilita el protocolo automatico de comprobacion y cambio de medio.
Para terminar, usar `/stop` en ambas y luego ESC en cada terminal.

La terminal usa UTF-8 por defecto. Para ASCII extendido se puede abrir **ambas** con
`-TextEncoding CP1252`. Las K8 transportan bytes sin recodificarlos. La codificacion y la
variante CRC deben configurarse iguales en ambos extremos; V7 no las negocia por el enlace.

## Implementacion incluida

* SYN=1111 y SFD=0000, duplicados en los dos medios a 20 ms por simbolo.
* Control de 4 bits: TT SS, transmitido completo por ambos medios a 40 ms por bit.
* TT=00 DATA, 01 ACK, 10 NACK, 11 LINK. Secuencias modulo 4; ventana Selective Repeat de 2.
* DATA de 8 bits y CRC de 8 bits. CRC sobre dos bytes: Control con nibble superior cero y DATA.
* CRC seleccionable: SMBUS (predeterminado), AUTOSAR, SAE-J1850 y MAXIM-DOW.
* DATA+CRC se distribuyen IR primero/sonido segundo en modo ambos; por un solo medio se
  serializan completos. ACK, NACK y LINK se duplican completos para sobrevivir a un medio caido.
* ACK/NACK DATA=0000 RR AA, con bits relativos a SS y SS+1. RR solicita repetir y AA confirma.
* LINK DATA=0000 MMMM solicita modo, 0001 MMMM lo confirma; MMMM=0 ambos, 1 IR, 2 sonido.
* LINK DATA=00111100 es la prueba A/A'. LINK DATA=0010 MMMM comunica su resultado.
  Solo se cuentan respuestas validas que correspondan a la prueba pendiente.
* Dos pruebas consecutivas fallidas apartan un medio; tres buenas lo reincorporan mediante
  aviso/confirmacion. Cada sentido lleva su estado propio. No se pierden pendientes al cambiar.
* Comprobar cada 32 DATA nuevos o 2 s desde el ultimo resultado, y adelantar ante NACK o timeout.
  La segunda prueba de una primera falla se programa enseguida; se respetan las tramas en curso.
* Pausa minima de reloj 80 ms; el receptor finaliza la captura al detectar 60 ms sin nuevo
  inicio de simbolo. No busca SYN/SFD dentro del cuerpo de la trama.
* Timeout 3 s desde fin de TX. Las respuestas tienen prioridad entre tramas,
  con la excepcion acotada del ACK individual: puede ceder a la segunda DATA propia
  para agrupar dos confirmaciones. Sin datos propios el ACK sale inmediatamente.
  NACK, fin de mensaje y duplicados no ceden a DATA. Ver limites de V7.2 arriba.
* No hay limite de reintentos en V7: con ambos medios ausentes conserva los pendientes mientras
  las placas permanezcan encendidas. Las colas son limitadas; un mensaje que no cabe se rechaza
  completo y se informa. No hay persistencia ante un corte de alimentacion.

### Alcance de esta primera version

La sesion empieza con secuencia cero y ambos medios. **Reiniciar una sola placa durante una
conversacion todavia requiere reiniciar tambien la otra**: recuperacion automatica de reinicios
y negociacion de configuracion quedan fuera de esta primera validacion.
El terminador de mensaje es LF; maximo 185 bytes por comando `/send` y 191 bytes por mensaje
recibido. Un byte UTF-8 se transmite en su propia trama. La compresion sigue pendiente.

La emision simultanea esta implementada con temporizadores y recepcion independientes.
Todavia hay que demostrar que el montaje separa el buzzer local del microfono local:
si el microfono escucha ambos buzzers, un detector de presencia de tono no puede distinguir
su origen. Ajustar solo el protocolo no garantiza que desaparezca esa interferencia.

## Verificacion realizada sin placas

* Keil ARMCLANG 6.24: cero errores y advertencias; imagen dentro de los limites de flash/RAM.
* `tests\ejecutar_arm.py`: ejecuta el C real compilado para Cortex-M4 con Unicorn. Vectores
  CRC publicados, todas las combinaciones de byte/Control/CRC/modo, corrupcion, desorden,
  ACK perdido, secuencias que dan varias vueltas, fallos de ambos medios, avisos perdidos,
  recuperacion y umbrales exactos de dos/tres comprobaciones.
* `tests\temporizacion_v7.py`: ejecuta SysTick, EXTI y codec del AXF final en dos placas
  emuladas. 36 casos de recepcion simultanea con sensores ideales, incluyendo diferentes
  modos por sentido. La biblioteca memcpy se modela como copia de bytes; no se verifica
  esa biblioteca. Tambien demuestra perdida de tramas al introducir autoescucha en ese modelo.
* Estos resultados **no son pruebas de las K8 fisicas ni de la velocidad final**.

Resultados guardados en `output\pruebas\resultado_logica_v7.json` y
`output\pruebas\resultado_temporizacion_v7.json`.
Para repetir, usar Python 3.12 del runtime de Codex y las dependencias locales
`tmp\protocolo_test_deps` (Unicorn 2.1.4 y pyelftools 0.33). No se instalaron globalmente.

Vectores de referencia: https://reveng.sourceforge.io/crc-catalogue/all.htm

