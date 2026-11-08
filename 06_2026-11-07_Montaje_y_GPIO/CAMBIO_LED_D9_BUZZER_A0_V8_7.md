# Armado V8.7: LED D9 y buzzer A0

Mismo cableado en ambas NUCLEO-F303K8. BUILD807 / PINMAP5.

| Elemento | Conexion |
|---|---|
| LED IR anodo | D9 / PA8 mediante resistencia de 330 ohm en serie |
| LED IR catodo | GND local |
| Modulo buzzer pasivo S | A0 / PA0 (PWM TIM2_CH1, nominal 2700 Hz) |
| Modulo buzzer + y - | 3V3 y GND locales |
| Sensor flama DO | D6 / PB1 |
| KY-037 DO | A1 / PA1 |
| Modulos sensores VCC y GND | 3V3 y GND locales |
| Reloj A hacia B | D11 de A -> 330 ohm -> A6 de B |
| Reloj B hacia A | D11 de B -> 330 ohm -> A6 de A |
| Referencia comun | GND A unido a GND B |

```text
D9 --- 330 ohm --- anodo LED IR
GND ------------- catodo LED IR
A0 -------------- S del modulo buzzer
```

Retirar la conexion antigua del LED a D3 y mover S del buzzer de D9 a A0.
D9 solo debe llegar al LED mediante su resistencia. No unir D3 y D9.
D3, A3, D2 y D12 quedan en alta impedancia; ello no elimina puentes de estano.
No unir los 3V3 de las dos placas. Hacer cambios con ambos USB desconectados.

El usuario agrego un switch: falta verificar su conexion exacta. Mantenerlo fijo
durante cada tanda y comparar otra posicion solo despues de apagar los emisores.
Siempre conservar la resistencia del LED en serie, cualquiera que sea la posicion.

Menu esperado: IR_TX=D9 SND_TX=A0. /status: BUILD=807 PINMAP=5 TONE_HZ=2699.
La primera prueba solo alterna IR; no emite reloj ni sonido. Una diferencia entre
IR_TX_SET y IR_TX_PIN apaga la salida y termina para revisar el cableado.

Los proyectos historicos sin SOUND_TEST_BUZZER_A0 conservan el buzzer TIM1/D9;
solo Protocolo_K8_V8 define este simbolo y usa TIM2/A0.
