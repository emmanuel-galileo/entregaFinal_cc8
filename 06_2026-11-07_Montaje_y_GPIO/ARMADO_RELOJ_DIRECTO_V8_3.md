# Reloj directo: conservar los PC817 soldados

Version actual del 15/11/2026: **V8.5, BUILD805, PINMAP3, 2700 Hz**.
Cargada y verificada en ambas placas; usuario confirmo RESET en ambas.

Se retiro el programa temporal de sonido V6 y se incorporo 2700 Hz al firmware
del proyecto. El tono no cambia el cableado. La primera comprobacion del nuevo
montaje dio reloj B->A 6/6 y A->B sin deteccion; IR A->B responde y B->A no.
El sonido se recupero en la ultima tanda y responde en ambos sentidos, tambien
con ambos buzzers activados y en silencio. La lectura GPIO de V8.5 confirma que
D11_A cambia pero A6_B sigue en 0; A3_B cambia pero el enlace IR B->A no se detecta.
Estas pruebas aun no validan transmision de tramas.

## Lo que queda soldado

Los PC817 y su cableado anterior a D2 y D12 pueden quedarse donde estan,
si las conexiones de alimentacion no tienen cortocircuitos.
La V8.5 deja D2/PA12 y D12/PB4 en modo analogico, sin pull-up/pull-down:
alta impedancia. No envia pulsos por D2 ni habilita interrupciones de D12.
Esto deshabilita su uso desde el micro; no desconecta las soldaduras de 3V3/GND
ni puede corregir un corto fisico.

## Los tres cables nuevos

Con ambos USB desconectados, usando D11 y A6 libres:

```text
NUCLEO A                              NUCLEO B

D11 ---- resistencia de 330 ohm -------- A6
A6  ---- resistencia de 330 ohm -------- D11
GND ---------------------------------- GND
```

Cada linea de senal tiene su propia resistencia en serie. No se conectan
a 3V3 ni se unen las salidas 3V3 de las placas. Cada NUCLEO conserva su USB.
Usar cables cortos y mantener ambas placas alimentadas durante las pruebas.
Si ya hay una union de GND correcta entre las placas, esa conexion sirve.

Con USB arriba, D11 es el penultimo pin abajo a la izquierda; A6 esta
a la derecha, entre A7 y A5. No usar A7: se utiliza para la terminal USB.

## Resto del armado, igual en A y B

| Funcion | Pin |
|---|---|
| LED IR: pin -> 330 ohm -> anodo; catodo a GND local | A3 |
| DO del sensor de flama | D6 |
| DO del KY-037 | A1 |
| S del modulo buzzer pasivo; el tono se elige por software | D9 |
| Reloj directo TX | D11 / PB5 |
| Reloj directo RX | A6 / PA7 |
| Alimentacion y tierra de los modulos | 3V3 y GND locales |

Los AO siguen sin conexion. IR y sonido transportan los datos; los cables
nuevos transportan solo los relojes, uno por cada sentido.
El enlace directo no tiene aislamiento mediante optoacopladores.

Para la union GND_A-GND_B puede aprovecharse un puente entre dos puntos de
tierra ya soldados. Si son las patas 2 y 3 de un PC817, comprobar que siguen
siendo respectivamente GND remoto y GND local segun el armado anterior.
No incluir las patas 1 o 4 en ese puente. Con una union de tierra correcta basta;
no unir las salidas 3V3. Hacer las soldaduras con ambos USB desconectados.

## Carga y comprobacion

1. Cargar el proyecto `Protocolo_K8_V8.uvprojx` actualizado en ambas K8.
2. Pulsar RESET en ambas despues de grabar. Elegir 1=A y 2=B en las terminales.
3. `/status` debe mostrar `BUILD=805` y `PINMAP=3 CLOCK_DIRECT=1 LEGACY_OFF=1`.
   `LEGACY_OFF=1` describe la configuracion de los GPIO, no una medicion electrica.
4. Con `/stop` en ambas, `/clock 1` en A debe producir `CLK_RX=1` en B;
   `/clock 0` debe producir `CLK_RX=0`. Repetir de B a A. Al terminar, `/stop`.

Conservar estos pines para usar V8.5; no agregar puentes D2-D12.
El programa anterior BUILD802 no utiliza D11/A6 como reloj.
La V8.5 recibe el flanco de subida sin invertir la senal, con los mismos tiempos
de simbolo y la misma compresion/protocolo que V8.2.

El script `probar_armado_perforada_v8.ps1 -Stage MapaReloj` prueba solo los
relojes, tres ciclos por sentido, y termina dejando las salidas apagadas.
La etapa `Remoto` tambien prueba IR; el nombre del script se conserva.
La etapa `Loopback` ahora corresponde a D11 -> 330 ohm -> A6 de una sola placa,
y su puente temporal debe retirarse antes de conectar las dos direcciones remotas.

## Verificacion realizada, sin hardware

Keil: cero errores y advertencias. El AXF paso 36 escenarios simultaneos
con sensores ideales, la recepcion EXTI7 ascendente, desactivacion de EXTI4,
alta impedancia de D2/D12, comandos manuales y reconstruccion de texto comprimido.
Se hicieron ademas las pruebas fisicas resumidas al inicio de esta guia.

Respaldo anterior: `Respaldo_V8_4_pre_lectura_pines_20261115_152559.zip`.
Resultado ideal: `output/pruebas/resultado_temporizacion_v8_5.json`.
Asignacion de pines verificada en la tabla 12 del
[manual UM1956 de ST](https://www.st.com/resource/en/user_manual/dm00231744-stm32-nucleo32-boards-mb1180-stmicroelectronics.pdf).
