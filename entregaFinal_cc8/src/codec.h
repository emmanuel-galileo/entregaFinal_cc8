#ifndef PHY11_CODEC_H
#define PHY11_CODEC_H
#include "base/codec.h"
typedef struct {
    int32_t symbol, slope;
    uint8_t valid, recovered, reason;
} V11Decision;
enum { V11_VALID, V11_SILENCE, V11_INVALID };
uint32_t v11_frequency(unsigned band, unsigned lane, unsigned symbol, bool turbo, unsigned step);
bool v11_decode(unsigned band, unsigned lane, bool turbo, const V10Sweep *s, V11Decision *d);
#endif
