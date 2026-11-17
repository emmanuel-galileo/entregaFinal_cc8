#include "chat_codec.h"
#include "third_party/heatshrink/heatshrink_encoder.h"
#include "third_party/heatshrink/heatshrink_decoder.h"

#define ESC 0x1BU
enum { BOUNDARY, TEXT, TAG, PACKET, DISCARD };
static heatshrink_encoder encoder;
static heatshrink_decoder decoder;
static uint8_t compressed_buffer[CHAT_MAX];

static bool quoted(const uint8_t *text, unsigned length)
{
    if (length && text[0] == ESC) { return true; }
    for (unsigned n=0;n<length;++n) { if (text[n] == '\n') { return true; } }
    return false;
}
static unsigned escaped_size(const uint8_t *bytes, unsigned length)
{
    unsigned result=length;
    for (unsigned n=0;n<length;++n) { if (bytes[n] == ESC || bytes[n] == '\n') { ++result; } }
    return result;
}
static unsigned packet_size(unsigned original, const uint8_t *body, unsigned length)
{
    const uint8_t header[2]={(uint8_t)original,(uint8_t)length};
    return 3U+escaped_size(header,2U)+escaped_size(body,length);
}
unsigned chat_plain_wire_size(const uint8_t *text, unsigned length)
{
    return quoted(text,length) ? packet_size(length,text,length) : length+1U;
}
static bool compress_text(const uint8_t *text, unsigned length, unsigned *length_out)
{
    heatshrink_encoder_reset(&encoder);
    size_t sunk=0U;
    if (heatshrink_encoder_sink(&encoder,(uint8_t *)text,length,&sunk) != HSER_SINK_OK || sunk != length) { return false; }
    unsigned used=0U;
    for (unsigned guard=0;guard<4096U;++guard) {
        const HSE_finish_res done=heatshrink_encoder_finish(&encoder);
        if (done == HSER_FINISH_DONE) { *length_out=used; return true; }
        if (done < 0 || used >= sizeof(compressed_buffer)) { return false; }
        size_t count=0U;
        if (heatshrink_encoder_poll(&encoder,compressed_buffer+used,sizeof(compressed_buffer)-used,&count) < 0) { return false; }
        used+=(unsigned)count;
    }
    return false;
}
static bool expand(const uint8_t *bytes, unsigned length, uint8_t *output, unsigned expected)
{
    heatshrink_decoder_reset(&decoder);
    unsigned consumed=0U,produced=0U;
    for (unsigned guard=0;guard<4096U;++guard) {
        size_t sunk=0U,count=0U;
        if (consumed < length) {
            if (heatshrink_decoder_sink(&decoder,(uint8_t *)bytes+consumed,length-consumed,&sunk) < 0) { return false; }
            consumed+=(unsigned)sunk;
        }
        uint8_t extra;
        const unsigned room=expected-produced;
        if (heatshrink_decoder_poll(&decoder,room ? output+produced : &extra,room ? room : 1U,&count) < 0 || count > room) { return false; }
        produced+=(unsigned)count;
        if (consumed == length && !count) {
            return heatshrink_decoder_finish(&decoder) == HSDR_FINISH_DONE && produced == expected;
        }
        if (!sunk && !count && consumed < length) { return false; }
    }
    return false;
}
static bool put_escaped(uint8_t byte, uint8_t *wire, unsigned capacity, unsigned *used)
{
    if (byte == ESC || byte == '\n') {
        if (*used+2U > capacity) { return false; }
        wire[(*used)++]=ESC; wire[(*used)++]=(uint8_t)(byte == '\n' ? 0U : 1U);
    } else {
        if (*used >= capacity) { return false; }
        wire[(*used)++]=byte;
    }
    return true;
}
unsigned chat_encode(const uint8_t *text, unsigned length, bool compress,
                     uint8_t *wire, unsigned capacity, bool *compressed)
{
    *compressed=false;
    if (length > CHAT_MAX) { return 0U; }
    unsigned packed_length=0U;
    const unsigned raw_size=chat_plain_wire_size(text,length);
    const uint8_t *body=text;
    unsigned body_length=length;
    if (compress && length >= 8U && compress_text(text,length,&packed_length)
        && packet_size(length,compressed_buffer,packed_length) < raw_size) {
        *compressed=true; body=compressed_buffer; body_length=packed_length;
    }
    if (!*compressed && !quoted(text,length)) {
        if (length+1U > capacity) { return 0U; }
        for (unsigned n=0;n<length;++n) { wire[n]=text[n]; }
        wire[length]='\n'; return length+1U;
    }
    if (packet_size(length,body,body_length) > capacity) { return 0U; }
    unsigned used=0U;
    wire[used++]=ESC; wire[used++]=(uint8_t)(*compressed ? 'C' : 'R');
    if (!put_escaped((uint8_t)length,wire,capacity,&used) || !put_escaped((uint8_t)body_length,wire,capacity,&used)) { return 0U; }
    for (unsigned n=0;n<body_length;++n) { if (!put_escaped(body[n],wire,capacity,&used)) { return 0U; } }
    wire[used++]='\n'; return used;
}
void chat_rx_init(ChatRx *rx)
{
    rx->used=0U; rx->length=0U; rx->state=BOUNDARY; rx->escaped=false; rx->compressed=false; rx->kind=0U;
}
static int finish_packet(ChatRx *rx)
{
    rx->state=BOUNDARY;
    if (rx->used < 2U) { return CHAT_ERROR; }
    const unsigned original=rx->packed[0],packed=rx->packed[1];
    if (original > CHAT_MAX || packed > CHAT_MAX || rx->used != packed+2U) { return CHAT_ERROR; }
    if (rx->kind == 'R') {
        if (original != packed) { return CHAT_ERROR; }
        for (unsigned n=0;n<original;++n) { rx->plain[n]=rx->packed[n+2U]; }
    } else {
        if (!original || !packed || !expand(rx->packed+2U,packed,rx->plain,original)) { return CHAT_ERROR; }
    }
    rx->length=original; rx->compressed=rx->kind == 'C'; return CHAT_READY;
}
int chat_rx_feed(ChatRx *rx, uint8_t byte)
{
    if (rx->state == DISCARD) { if (byte == '\n') { rx->state=BOUNDARY; } return CHAT_MORE; }
    if (rx->state == BOUNDARY) {
        rx->used=0U; rx->length=0U; rx->escaped=false; rx->compressed=false;
        if (byte == ESC) { rx->state=TAG; return CHAT_MORE; }
        rx->state=TEXT;
    }
    if (rx->state == TEXT) {
        if (byte == '\n') { rx->length=rx->used; rx->state=BOUNDARY; return CHAT_READY; }
        if (rx->used == CHAT_MAX) { rx->state=DISCARD; return CHAT_ERROR; }
        rx->plain[rx->used++]=byte; return CHAT_MORE;
    }
    if (rx->state == TAG) {
        if (byte != 'C' && byte != 'R') { rx->state=byte == '\n' ? BOUNDARY : DISCARD; return CHAT_ERROR; }
        rx->kind=byte; rx->state=PACKET; return CHAT_MORE;
    }
    if (byte == '\n') {
        if (rx->escaped) { rx->state=BOUNDARY; return CHAT_ERROR; }
        return finish_packet(rx);
    }
    if (rx->escaped) {
        rx->escaped=false;
        if (byte > 1U) { rx->state=DISCARD; return CHAT_ERROR; }
        byte=(uint8_t)(byte == 0U ? '\n' : ESC);
    } else if (byte == ESC) { rx->escaped=true; return CHAT_MORE; }
    if (rx->used == sizeof(rx->packed)) { rx->state=DISCARD; return CHAT_ERROR; }
    rx->packed[rx->used++]=byte; return CHAT_MORE;
}
