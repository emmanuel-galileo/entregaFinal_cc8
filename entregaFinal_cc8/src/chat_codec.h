#ifndef CHAT_CODEC_V8_H
#define CHAT_CODEC_V8_H
#include <stdbool.h>
#include <stdint.h>

#define CHAT_MAX 185U
#define CHAT_WIRE_MAX (2U+2U*(CHAT_MAX+2U)+1U)
enum { CHAT_ERROR=-1, CHAT_MORE=0, CHAT_READY=1 };
typedef struct {
    uint8_t packed[CHAT_MAX+2U], plain[CHAT_MAX];
    unsigned used, length;
    uint8_t state, kind;
    bool escaped, compressed;
} ChatRx;

unsigned chat_encode(const uint8_t *text, unsigned length, bool compress,
                     uint8_t *wire, unsigned capacity, bool *compressed);
unsigned chat_plain_wire_size(const uint8_t *text, unsigned length);
void chat_rx_init(ChatRx *rx);
int chat_rx_feed(ChatRx *rx, uint8_t byte);
#endif
