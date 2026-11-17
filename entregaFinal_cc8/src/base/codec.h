#ifndef PHY10_CODEC_H
#define PHY10_CODEC_H
#include <stdint.h>
#include <stdbool.h>
uint8_t v10_crc(unsigned kind,const uint8_t *bytes,unsigned length);
uint8_t v10_word(uint8_t data);
bool v10_recover(uint8_t values,uint8_t known,uint8_t *data,uint8_t *recovered);
uint32_t v10_frame(unsigned kind,uint8_t control,uint8_t data);
bool v10_frame_valid(unsigned kind,uint32_t frame);
int v10_classify(unsigned remote,unsigned lane,const uint32_t hz[3],const uint32_t count[3],const uint32_t bad[3]);
uint32_t v10_frequency(unsigned node,unsigned lane,unsigned bit,unsigned step);
typedef struct {
    uint32_t hz[3],periods[3],edges[3],bad[3],window_us[3],time_us[3];
} V10Sweep;
typedef struct {int32_t bit,slope_hz_s;uint8_t valid_steps,reconstructed;} V10Decision;
bool v10_decode(unsigned band,unsigned lane,const V10Sweep *s,V10Decision *d);
#endif
