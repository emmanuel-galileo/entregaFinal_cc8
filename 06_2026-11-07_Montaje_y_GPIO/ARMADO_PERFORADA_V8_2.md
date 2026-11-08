# Armado actual en perforada: V8.2, BUILD802

Asignacion acordada para ambas NUCLEO-F303K8, con USB arriba, usando
GND derecho y pines de senal separados. Esta guia sustituye las asignaciones
de pines de los planes anteriores; el protocolo y la compresion no cambian.

| Funcion | Pin | GPIO |
|---|---|---|
| LED IR, con 330 ohm en serie | A3 | PA4 |
| DO del sensor de flama | D6 | PB1 |
| DO del KY-037 | A1 | PA1 |
| Senal del modulo buzzer pasivo | D9 | PA8 |
| Salida de reloj, con 330 ohm en serie | D2 | PA12 |
| Entrada de reloj, colector PC817 | D12 | PB4 |
| Alimentacion de los modulos propios | 3V3 | Local |
| Tierra de los modulos propios | GND derecho | Local |

Los AO quedan sin conexion. Cada LED tiene el anodo hacia la resistencia
y el catodo a GND local. Cada NUCLEO se alimenta por su USB; no unir los 3V3.

## PC817, vista superior

Girar el encapsulado para que la marca del pin 1 quede abajo a la izquierda.
La vista de soldadura queda reflejada.

```text
       4           3
       |           |
     +---------------+
     |     PC817     |
     | .             |
     +---------------+
       |           |
       1           2
```

PC817 instalado en B, reloj A->B:

```text
D2_A -- 330 ohm -- pin 1
GND_A ----------- pin 2
GND_B ----------- pin 3
                  pin 4 --+-- D12_B
                          +-- 4.7 kohm -- 3V3_B
```

PC817 instalado en A, reloj B->A:

```text
D2_B -- 330 ohm -- pin 1
GND_B ----------- pin 2
GND_A ----------- pin 3
                  pin 4 --+-- D12_A
                          +-- 4.7 kohm -- 3V3_A
```

Pin 2 es retorno del transmisor remoto; pin 3 es tierra local del receptor.
Conservar separados esos nodos en la perforada. Ambos USB en un mismo PC
pueden unir las tierras a traves del PC: no es aislamiento global del sistema.

## Version y diagnostico

La version BUILD802 adapta solo GPIO/EXTI y agrega diagnostico manual.
La recepcion del reloj utiliza PB4/EXTI4; el microfono conserva PA1/EXTI1.
El sensor de flama PB1 se lee por GPIO, sin ocupar EXTI1.

Con `/stop`, `/ir 1|0` activa el LED de A3 y `/clock 1|0` fija D2.
`/tone 1|0` conserva el tono de 3000 Hz. `/stop` apaga todos los emisores.
`/status` muestra BUILD802, PINMAP=2, IR_DO en D6 y CLK_RX en D12.
El reloj recibido se invierte: D2 remoto alto debe producir D12 local bajo.

`probar_armado_perforada_v8.ps1` verifica tres ciclos por sentido de reloj
y de IR, con el protocolo detenido, conserva registros y apaga las salidas.
`calibrar_sonido_v8.ps1` mide silencio, cada buzzer y ambos.
Los scripts actuales requieren BUILD802; las versiones previas estan respaldadas.

El 15/11/2026 se compilo con cero errores/advertencias, paso el modelo de
36 casos fisicos ideales y las verificaciones de GPIO, vector EXTI4, comandos
manuales y codec. Esto no reemplaza la validacion de soldadura y posicion real.
