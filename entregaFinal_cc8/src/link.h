#ifndef PHY11_LINK_H
#define PHY11_LINK_H
#include "codec.h"
#define V11_QUEUE 512U
enum { L_BEGIN, L_DATA, L_CHECK, L_REPAIR, L_REPAIR_DATA };
/* Control de trama: TTSS. No confundir TT con kind del encabezado por ronda. */
enum { V11_FRAME_START, V11_FRAME_CONTINUE, V11_FRAME_END, V11_FRAME_SINGLE };
typedef void (*V11Deliver)(void *, uint8_t);
typedef struct {
    uint8_t h[2], data[2], indices[2], mask, kind, arg, stage, seq;
    bool real;
} V11Cell;
typedef struct {
    uint8_t queue[V11_QUEUE];
    uint8_t queue_types[V11_QUEUE / 4U]; /* Cuatro etiquetas de 2 bits por byte. */
    uint16_t head, tail;
    bool permitted, frame_present, repairing, corrupt_next, drop_ack;
    uint32_t tx_frame, rx_frame;
    uint8_t frame_seq, rx_frame_seq, work, normal_block, stage, cursor, confirmed, repair_set,
        repair_index, repair_tries, sequence, active, good[2];
    uint8_t rx_block, rx_cursor, rx_known, rx_values, rx_mask, rx_repair, rx_fixed;
    bool rx_repairing, rx_final, rx_done, rx_context;
    bool rx_message_open;
    bool cached;
    uint8_t last_seq, last_h[2], last_arg;
    int last_reply[2];
    V11Cell cell;
    bool pending;
    unsigned crc_kind;
    uint32_t round, tx_bytes, rx_bytes, fec_bits, retries, header_bad, frame_bad, duplicates,
        suspensions[2], restores[2], primed_bad[2], pilot_tests[2], type_bad;
    V11Deliver deliver;
    void *user;
} V11;
void v11_init(V11 *p, V11Deliver deliver, void *user);
void v11_lease(V11 *p, bool sender);
unsigned v11_queued(const V11 *p);
/* Cada llamada encola una unidad completa de mensaje, ya codificada/comprimida. */
bool v11_enqueue(V11 *p, const uint8_t *data, unsigned length);
bool v11_busy(const V11 *p);
void v11_prepare(V11 *p, V11Cell *c);
void v11_receive(V11 *p, const int h0[2], const int h1[2], const int data[2], int reply[2]);
void v11_finish(V11 *p, const int reply[2], unsigned tested);
void v11_pilot(V11 *p, unsigned lane, unsigned sent, int primed);
#endif
