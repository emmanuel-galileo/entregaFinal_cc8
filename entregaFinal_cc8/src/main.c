#include "chat_codec.h"
#include "hw.h"
#include "stm32f3xx.h"
static V11 app;
static ChatRx chat_rx;
static uint8_t wire[CHAT_WIRE_MAX];
static volatile uint8_t rx[256];
static volatile unsigned rx_head, rx_tail, rx_drops;
static char input[192], node = '?';
static unsigned input_n;
static bool previous_cr, input_overflow, compression = true, trace, monitor;
static uint32_t last_q, last_mac, last_monitor, comp_tx, comp_rx, plain_tx, app_errors, input_bytes,
    wire_bytes, saved_bytes;
static void deliver(void *user, uint8_t value) {
    (void)user;
    const unsigned next = (rx_head + 1U) & 255U;
    if (next == rx_tail) {
        ++rx_drops;
    } else {
        rx[rx_head] = value;
        rx_head = next;
    }
}
static void prefix(void) {
    hw11_putc('[');
    hw11_putc(node);
    hw11_puts("] ");
}
static bool equal(const char *a, const char *b) {
    while (*a && *b && *a == *b) {
        ++a;
        ++b;
    }
    return *a == *b;
}
static bool starts(const char *a, const char *b) {
    while (*b) {
        if (*a++ != *b++) {
            return false;
        }
    }
    return true;
}
static unsigned number(const char *s) {
    unsigned n = 0;
    while (*s >= '0' && *s <= '9') {
        n = n * 10U + (unsigned)(*s++ - '0');
        if (n > 10000U) {
            return 10000U;
        }
    }
    return n;
}
static bool option(const char *s, char max) {
    return s[0] >= '0' && s[0] <= max && !s[1];
}
static void field(const char *label, uint32_t value) {
    hw11_puts(label);
    hw11_number(value);
}
static void status(void) {
    prefix();
    hw11_puts("STATUS VERSION=" APP_VERSION_NAME " BUILD=1105");
    field(" RUN=", hw11_running());
    field(" ACTIVE=", app.active);
    field(" CRC=", app.crc_kind);
    field(" QUEUED=", v11_queued(&app));
    field(" PENDING=", app.frame_present);
    field(" TX=", app.tx_bytes);
    field(" RX=", app.rx_bytes);
    field(" BLOCK=", app.work);
    field(" KNOWN=", app.rx_known);
    field(" FEC=", app.fec_bits);
    field(" RETRY=", app.retries);
    field(" BAD=", app.frame_bad);
    field(" HDR_BAD=", app.header_bad);
    field(" DUP=", app.duplicates);
    field(" RESTORE_IR=", app.restores[0]);
    field(" RESTORE_SND=", app.restores[1]);
    field(" APP_ERR=", app_errors);
    field(" RX_DROP=", rx_drops);
    field(" COMPRESS=", compression);
    field(" COMP_TX=", comp_tx);
    field(" COMP_RX=", comp_rx);
    field(" PLAIN_TX=", plain_tx);
    field(" INPUT_BYTES=", input_bytes);
    field(" WIRE_BYTES=", wire_bytes);
    field(" SAVED_BYTES=", saved_bytes);
    hw11_puts("\r\n");
    prefix();
    hw11_status();
    prefix();
    hw11_log();
}
static void menu(void) {
    prefix();
    hw11_puts("VERSION " APP_VERSION_NAME " BUILD1105 - BARRIDOS + PRIMADO + PARIDAD\r\n");
    hw11_puts("/start /stop /status /menu /send Hola /compress 0|1 /trace 0|1 /phylog 0|1\r\n");
    hw11_puts("/probe: 8 rondas de prueba; /badcrc: alterar CRC siguiente byte; /dropack: omitir "
              "ACK\r\n");
    hw11_puts("/fault 0|1|2|3: apagar TX ninguno/IR/sonido/ambos (incluye encabezado)\r\n");
    hw11_puts("/notch 0|1|2 1|2|3: omitir un escalon en IR/sonido/ambos\r\n");
    hw11_puts("/erase 1|2|3 o /flip 1|2|3: perder/cambiar proximo par de datos\r\n");
    hw11_puts("Con STOP: /rate log|max|0.5|1|1.25 (Hz), /irboost 0|1, /crc 0|1|2|3\r\n");
    hw11_puts("Con STOP: /ir 0|1 /tone 0|1 (2700Hz) /clock 0|1 /identify 0|1\r\n");
    hw11_puts("/samples /mic /monitor 0|1 /threshold 60 (A) o 90 (B): escucha/calibracion\r\n");
    hw11_puts("/events 0|1: eventos para la interfaz. Reiniciar ambas si reinicias una.\r\n");
}
static void command(char *line) {
    if (equal(line, "/start")) {
        monitor = false;
        if (!hw11_running()) {
            hw11_start();
        }
        prefix();
        hw11_puts("RUN=1\r\n");
    } else if (equal(line, "/probe")) {
        monitor = false;
        hw11_probe();
        hw11_puts("PROBE_REQUESTED\r\n");
    } else if (equal(line, "/stop")) {
        hw11_stop();
        monitor = false;
        prefix();
        hw11_puts("RUN=0; pendientes conservados\r\n");
    } else if (equal(line, "/status")) {
        status();
    } else if (equal(line, "/samples")) {
        hw11_samples();
    } else if (equal(line, "/menu") || equal(line, "?")) {
        menu();
    } else if (equal(line, "/badcrc")) {
        app.corrupt_next = true;
        hw11_puts("BADCRC_ARMED\r\n");
    } else if (equal(line, "/dropack")) {
        app.drop_ack = true;
        hw11_puts("DROP_ACK_ARMED\r\n");
    } else if (starts(line, "/fault ") && option(line + 7, '3')) {
        hw11_fault(number(line + 7));
        status();
    } else if (starts(line, "/erase ") && option(line + 7, '3')) {
        hw11_inject(number(line + 7), false);
        hw11_puts("ERASE_ARMED\r\n");
    } else if (starts(line, "/notch ") && line[7] >= '0' && line[7] <= '2' && line[8] == ' ' &&
               option(line + 9, '3')) {
        hw11_notch(number(line + 9), (unsigned)(line[7] - '0'));
        hw11_puts("NOTCH_ARMED\r\n");
    } else if (starts(line, "/flip ") && option(line + 6, '3')) {
        hw11_inject(number(line + 6), true);
        hw11_puts("FLIP_ARMED\r\n");
    } else if (starts(line, "/phylog ") && option(line + 8, '1')) {
        trace = line[8] == '1';
        hw11_mac_log();
    } else if (starts(line, "/events ") && option(line + 8, '1')) {
        hw11_events(line[8] == '1');
        hw11_puts(line[8] == '1' ? "EVENTS=1 FORMAT=1\r\n" : "EVENTS=0\r\n");
    } else if (starts(line, "/trace ") && option(line + 7, '1')) {
        trace = line[7] == '1';
    } else if (starts(line, "/compress ") && option(line + 10, '1')) {
        compression = line[10] == '1';
        status();
    } else if (starts(line, "/threshold ")) {
        hw11_threshold(number(line + 11));
        hw11_mic();
    } else if (equal(line, "/mic")) {
        hw11_mic();
    } else if (starts(line, "/monitor ") && option(line + 9, '1')) {
        monitor = line[9] == '1';
    } else if (starts(line, "/rate ")) {
        hw11_puts(hw11_rate(line + 6) ? "RATE_SET\r\n" : "RATE_BUSY_OR_INVALID\r\n");
    } else if (starts(line, "/irboost ") && option(line + 9, '1')) {
        hw11_puts(hw11_boost(line[9] == '1') ? "IRBOOST_SET\r\n" : "STOP_FIRST\r\n");
    } else if (starts(line, "/crc ") && option(line + 5, '3')) {
        if (!hw11_running() && !v11_busy(&app) && (!app.rx_context || app.rx_done)) {
            app.crc_kind = number(line + 5);
            status();
        } else {
            hw11_puts("CRC_BUSY: parar y vaciar ambas\r\n");
        }
    } else if (starts(line, "/ir ") || starts(line, "/tone ") || starts(line, "/clock ") ||
               starts(line, "/identify ")) {
        if (hw11_running()) {
            hw11_puts("STOP_FIRST\r\n");
        } else {
            const unsigned kind = starts(line, "/ir ")      ? 0U
                                  : starts(line, "/tone ")  ? 1U
                                  : starts(line, "/clock ") ? 2U
                                                            : 3U;
            const char *arg = line + (kind == 0U ? 4U : kind == 1U ? 6U : kind == 2U ? 7U : 10U);
            if (option(arg, '1')) {
                hw11_manual(kind, *arg == '1');
                hw11_puts("MANUAL_SET\r\n");
            } else {
                hw11_puts("INVALID_OPTION\r\n");
            }
        }
    } else if (starts(line, "/send ")) {
        unsigned length = 0;
        while (line[6U + length]) {
            ++length;
        }
        bool packed = false;
        const unsigned n = chat_encode((const uint8_t *)(line + 6), length, compression, wire,
                                       sizeof(wire), &packed);
        if (!n) {
            hw11_puts("MESSAGE_TOO_LONG: maximo 185 bytes\r\n");
            return;
        }
        const uint32_t state = __get_PRIMASK();
        __disable_irq();
        const bool ok = v11_enqueue(&app, wire, n);
        const unsigned goal = app.tx_bytes + v11_queued(&app) + (app.frame_present ? 1U : 0U);
        __set_PRIMASK(state);
        if (!ok) {
            hw11_puts("QUEUE_FULL\r\n");
            return;
        }
        const unsigned raw = chat_plain_wire_size((const uint8_t *)(line + 6), length);
        if (packed) {
            ++comp_tx;
        } else {
            ++plain_tx;
        }
        input_bytes += length;
        wire_bytes += n;
        saved_bytes += raw - n;
        prefix();
        field("QUEUED_MSG bytes=", n);
        field(" PLAIN=", length);
        field(" COMP=", packed);
        field(" SAVED=", raw - n);
        field(" GOAL_TX=", goal);
        hw11_puts("\r\n");
    } else if (*line) {
        hw11_puts("UNKNOWN: /menu\r\n");
    }
}
int main(void) {
    v11_init(&app, deliver, 0);
    chat_rx_init(&chat_rx);
    hw11_init(&app);
    hw11_puts("\r\nVERSION " APP_VERSION_NAME " BUILD1105. Emisores apagados.\r\nElige 1=A o 2=B, sin Enter.\r\n");
    for (;;) {
        char c;
        while (hw11_read(&c)) {
            if (node == '?') {
                if (c == '1' || c == '2') {
                    node = c == '1' ? 'A' : 'B';
                    hw11_node((unsigned)(c - '1'));
                    menu();
                } else if (c == '?') {
                    hw11_puts("VERSION " APP_VERSION_NAME " BUILD1105: elige 1=A o 2=B\r\n");
                }
                continue;
            }
            if (c == '\r' || c == '\n') {
                if (c == '\n' && previous_cr) {
                    previous_cr = false;
                    continue;
                }
                previous_cr = c == '\r';
                input[input_n] = 0;
                if (input_overflow) {
                    hw11_puts("INPUT_TOO_LONG\r\n");
                } else {
                    command(input);
                }
                input_n = 0U;
                input_overflow = false;
            } else {
                previous_cr = false;
                if (c == '\b' || c == 127) {
                    if (input_n) {
                        --input_n;
                    }
                } else if (input_n < sizeof(input) - 1U) {
                    input[input_n++] = c;
                } else {
                    input_overflow = true;
                }
            }
        }
        while (rx_tail != rx_head) {
            const uint8_t value = rx[rx_tail];
            rx_tail = (rx_tail + 1U) & 255U;
            const int result = chat_rx_feed(&chat_rx, value);
            if (result == CHAT_ERROR) {
                ++app_errors;
                prefix();
                hw11_puts("CHAT_RX_ERROR\r\n");
            } else if (result == CHAT_READY) {
                if (chat_rx.compressed) {
                    ++comp_rx;
                }
                prefix();
                hw11_puts("CHAT_RX ");
                for (unsigned n = 0; n < chat_rx.length; ++n) {
                    hw11_putc((char)chat_rx.plain[n]);
                }
                hw11_puts("\r\n");
            }
        }
        const uint32_t now = hw11_now();
        hw11_pump_events();
        if (trace && hw11_event() != last_mac) {
            last_mac = hw11_event();
            prefix();
            hw11_mac_log();
        }
        if (trace && hw11_stats()->rounds != last_q) {
            last_q = hw11_stats()->rounds;
            prefix();
            hw11_log();
        }
        if (monitor && (uint32_t)(now - last_monitor) >= 200U) {
            last_monitor = now;
            hw11_mic();
        }
    }
}
