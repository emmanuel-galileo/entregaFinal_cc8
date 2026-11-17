# Proyecto 3 — Capa Física de Comunicación

Implementación de un protocolo híbrido paralelo y serial para comunicar dos equipos NUCLEO-F303K8, con chat, interfaz de supervisión y registro del protocolo.

## Integrantes

Emmanuel Santos 23005326
Carlos Yoc 23004205

## Documentación oficial

**Consultar el documento técnico, los diagramas de conexiones y la explicación del protocolo en el siguiente repositorio:**

https://github.com/emmanuel-galileo/entregaFinal_cc8.git

## Documentación incluida

- [Memoria técnica en PDF](documentacion/Memoria_Tecnica_CC8.pdf).
- [Esquemático de conexiones en imagen](documentacion/Esquematico_CC8.png).
- [Resumen de validación](documentacion/Validacion_resumen.json).

## Contenido

- `ESTACION.uvprojx` y `PROTO.uvprojx`: proyectos para Keil µVision.
- `src/`: código fuente del firmware y bibliotecas utilizadas.
- `RTE/`: archivos de inicio y configuración del dispositivo.
- `app.py` e `interfaz/`: aplicación de chat, servidor web, visualización y pruebas.
- `Iniciar_CC8.cmd`: inicio de la aplicación en Windows.
- `terminal.ps1`: interfaz alternativa por terminal.

Ambas versiones comparten el protocolo y la interfaz. La versión actual es **BUILD 1105**.

## Ejecutar el chat

1. Instalar Python de 64 bits, versión 3.10 o posterior.
2. Ejecutar `Iniciar_CC8.cmd`. La primera ejecución descarga las dependencias y requiere conexión a Internet.
3. Conectar las tarjetas y cerrar otras terminales que estén usando sus puertos COM.
4. Elegir el modo de conexión: dos tarjetas en una computadora, o una tarjeta local en cada computadora. Seleccionar los puertos y las identidades A/B correspondientes.
5. Conectar, aplicar la misma configuración de comunicación en ambos extremos y activar el enlace. El chat permite escribir, transmitir y visualizar los mensajes recibidos.
6. Para usar la sala desde el navegador, pulsar **Chat web**. La aplicación inicia un servidor HTTP local y abre su dirección disponible, normalmente `http://127.0.0.1:8765`.

Mantener la aplicación abierta mientras se utiliza el chat web. En dos computadoras, ejecutar una instancia en cada equipo, conectada a su tarjeta local. La comunicación entre tarjetas utiliza los medios físicos; el servidor web proporciona la interfaz de usuario.

## Funciones principales

- Transmisión paralela por infrarrojo y sonido, organizada en rondas sincronizadas.
- Barridos de frecuencia, validación durante la transmisión y reconstrucción local de bits.
- Sincronización SYN/SFD, cuatro tipos de trama, DATA de 8 bits y CRC de 8 bits.
- CRC seleccionable, ACK/NACK, reparación y retransmisión.
- UTF-8 de 1 a 4 bytes, Extended ASCII mediante Windows-1252 y compresión opcional.
- Detección de fallos de canal, continuidad por el medio disponible y recuperación del canal.
- Modo de demostración a 1 Hz y modo rápido.
- Registro de tramas, CRC, confirmaciones, errores, reparaciones y retransmisiones, con exportación de sesiones.

En el panel de pruebas se distinguen las pruebas con tarjetas, las fallas inyectadas por software y los modelos matemáticos. Las demostraciones de interferencia física requieren actuar sobre el montaje.

## Observar el protocolo durante la demostración

La pestaña **En vivo** sigue el recorrido del documento: **Turno → Ronda → Barridos → Matriz → Canales → Trama**. Elegir la K8 que se desea observar; con una sola tarjeta local, la vista se limita a esa tarjeta.

- **Ampliar protocolo** oculta los controles de conexión para dar espacio a la explicación.
- **Pausar vista**, las flechas de ronda y **Volver al vivo** permiten leer la captura sin detener las tarjetas.
- **Volver a una evidencia** abre directamente rondas con rescate 2/3, recuperación matricial, CRC inválido, reparación o Turbo.
- Los botones inferiores ejecutan las demostraciones existentes con ambas K8 locales. Los fallos de estas demostraciones se inyectan por software; las pruebas de interferencia física siguen en **Pruebas**. Solo la demostración de Turbo usa modo rápido.
- **Registro** conserva los datos serie y permite exportar o abrir sesiones anteriores, identificadas como **archivo importado**.

La visualización distingue las mediciones recibidas, la matriz planeada en TX, las posiciones todavía desconocidas en RX y el retorno preparado frente al retorno observado. Las gráficas de barridos representan tres frecuencias medidas; el reparto temporal de la ronda es un esquema calculado con sus tiempos reportados.

Esta actualización de la interfaz utiliza los eventos de **BUILD 1105** y no requiere cambiar el firmware.

## Dos chats y ejemplos de texto

Con ambas K8 en una PC se muestran dos conversaciones, una desde la perspectiva de A y otra desde B, cada una con su propia entrada y botón **Enviar**. Un mensaje pendiente se muestra primero en su emisor; la burbuja recibida aparece en el destino cuando su K8 entrega el mensaje. Con dos PC, cada aplicación muestra su conversación local. La sala web ofrece las mismas dos perspectivas cuando ambas tarjetas están conectadas localmente.

En cada chat se puede elegir un ejemplo y pulsar **Cargar**: `A`, `$`, `ñ`, `€`, `😀`, `Uñ€😀`, `ñ€` o un mensaje vacío. **Cargar** prepara el borrador; **Enviar** inicia la transmisión. El botón **Emoji** abre el selector de emojis, signos y letras especiales. El contador muestra los bytes originales y su detalle hexadecimal al colocar el cursor encima.

En **Pruebas → Texto** también están disponibles los ensayos individuales de un carácter, dólar y emoji, además de UTF-8 completo y CP1252. Los datos de estos ensayos van a 1 Hz. Los emojis requieren UTF-8; los ejemplos y símbolos incompatibles se desactivan al seleccionar CP1252.

Estos controles hacen accesibles las capacidades UTF-8 de 1, 2, 3 y 4 bytes y Extended ASCII que ya implementaba BUILD 1105. La codificación, la trama y el protocolo físico son los mismos descritos en la memoria técnica.

## Interrumpir durante la transmisión

El botón **Interrumpir en vivo…**, en la barra inferior, abre un panel flotante que deja visible el protocolo. Elegir los emisores de A o B y enviar un mensaje desde el chat. Durante su transmisión se puede:

- **Apagar IR** o **Silenciar buzzer** hasta pulsar **Restaurar IR + sonido**. Cerrar el panel conserva el bloqueo; el pie de la ventana muestra los bloqueos confirmados.
- Elegir **Omitir un escalón una vez**, el medio y la primera, segunda o tercera frecuencia, y pulsar **Aplicar una vez**. Por defecto omite la segunda frecuencia del sonido, para observar el rescate 2/3.
- Armar una pérdida de datos, una inversión de bits, un CRC alterado o un ACK omitido. Cada opción explica cuándo actúa; alterar CRC afecta al próximo byte que se prepare.

Estas órdenes ya existen en BUILD 1105 y no envían STOP. El panel distingue orden enviada, orden armada y aplicación observada en una ronda cuando existe ese evento. Si se usan durante una prueba automática, el resultado queda marcado **manual** y registra las intervenciones. La propia prueba puede restaurar los emisores al avanzar o terminar.

**Diagnóstico y calibración** es otro apartado: `Tono apagado · con STOP` sirve para una prueba del emisor detenido y no para silenciarlo durante el chat. Los controles de diagnóstico que requieren STOP muestran una explicación si se intentan con el chat activo.

Las inyecciones del panel son por software. La demostración de interferencia totalmente física se realiza con el switch o con ruido del teléfono. En modo Demostración el ritmo sigue fijo a 1 Hz; para observar Turbo Solo-IR se debe seleccionar previamente el modo Rápido.

## Compilar el firmware

Abrir el proyecto de la versión correspondiente en Keil µVision, instalar los paquetes de dispositivo solicitados, compilar y cargar en las tarjetas. Se utilizó ARM Compiler 6.24, STM32F3xx_DFP 2.2.2 y CMSIS 6.2.0. Después de programar, reiniciar ambas tarjetas.

Las dependencias de Python están fijadas en `interfaz/requirements.txt`. Se conservan los avisos y licencias de los componentes de terceros dentro de sus fuentes.
