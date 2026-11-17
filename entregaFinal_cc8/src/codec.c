#include "codec.h"
static const uint16_t normal[2][2][4][3] = {
    {{{80, 100, 120}, {80, 120, 160}, {80, 140, 180}, {80, 160, 200}},
     {{2700, 2800, 2900}, {2700, 2900, 3000}, {2700, 3000, 3100}, {2700, 3100, 3200}}},
    {{{400, 350, 300}, {400, 300, 200}, {400, 330, 260}, {400, 280, 220}},
     {{4100, 4000, 3900}, {4100, 3900, 3700}, {4100, 3800, 3600}, {4100, 3700, 3500}}}};
static const uint16_t boosted[2][4][3] = {
    {{200, 240, 300}, {200, 280, 340}, {200, 300, 360}, {200, 320, 380}},
    {{400, 350, 300}, {400, 320, 260}, {400, 300, 240}, {400, 280, 220}}};
uint32_t v11_frequency(unsigned band, unsigned lane, unsigned symbol, bool turbo, unsigned step) {
    return turbo && lane == 0U ? boosted[band & 1U][symbol & 3U][step % 3U]
                               : normal[band & 1U][lane & 1U][symbol & 3U][step % 3U];
}
bool v11_decode(unsigned band, unsigned lane, bool turbo, const V10Sweep *s, V11Decision *d) {
    d->symbol = -1;
    d->slope = 0;
    d->valid = 0U;
    d->recovered = 0U;
    d->reason = V11_SILENCE;
    if (band > 1U || lane > 1U) {
        return false;
    }
    unsigned quality = 0U, usable = 0U;
    for (unsigned n = 0; n < 3U; ++n) {
        if (s->edges[n]) {
            d->reason = V11_INVALID;
        }
        const uint32_t expected = (s->hz[n] * s->window_us[n] + 500000U) / 1000000U,
                       allow = (expected * 35U + 99U) / 100U + 2U;
        const uint32_t error =
            s->edges[n] > expected ? s->edges[n] - expected : expected - s->edges[n];
        if (s->hz[n] && s->window_us[n] && s->periods[n] >= 3U && expected >= 3U &&
            error <= allow && s->bad[n] <= 2U + s->edges[n] / 10U) {
            quality |= 1U << n;
        }
    }
    for (unsigned i = 0; i < 3U; ++i) {
        for (unsigned j = i + 1U; j < 3U; ++j) {
            if ((quality & (1U << i)) && (quality & (1U << j))) {
                if (s->time_us[j] <= s->time_us[i]) {
                    return false;
                }
                if ((band == 0U && s->hz[j] * 1000U <= s->hz[i] * 1015U) ||
                    (band == 1U && s->hz[j] * 1000U >= s->hz[i] * 985U)) {
                    return false;
                }
            }
        }
    }
    for (unsigned n = 0; n < 3U; ++n) {
        if (quality & (1U << n)) {
            for (unsigned k = 0; k < 4U; ++k) {
                const uint32_t f = v11_frequency(band, lane, k, turbo, n),
                               e = s->hz[n] > f ? s->hz[n] - f : f - s->hz[n];
                if (e * 10000U <= f * 120U) {
                    usable |= 1U << n;
                }
            }
        }
    }
    unsigned count = 0U, first = 3U, last = 0U;
    for (unsigned n = 0; n < 3U; ++n) {
        if (usable & (1U << n)) {
            ++count;
            if (first == 3U) {
                first = n;
            }
            last = n;
        }
    }
    d->valid = (uint8_t)usable;
    if (count < 2U) {
        return false;
    }
    const uint32_t delta = s->hz[last] > s->hz[first] ? s->hz[last] - s->hz[first]
                                                      : s->hz[first] - s->hz[last],
                   dt = s->time_us[last] - s->time_us[first];
    int found = -1;
    for (unsigned k = 0; k < 4U; ++k) {
        bool match = true;
        for (unsigned n = 0; n < 3U; ++n) {
            if (usable & (1U << n)) {
                const uint32_t f = v11_frequency(band, lane, k, turbo, n),
                               e = s->hz[n] > f ? s->hz[n] - f : f - s->hz[n];
                if (e * 10000U > f * 120U) {
                    match = false;
                }
            }
        }
        const uint32_t f0 = v11_frequency(band, lane, k, turbo, first),
                       f1 = v11_frequency(band, lane, k, turbo, last),
                       wanted = f0 > f1 ? f0 - f1 : f1 - f0,
                       e = delta > wanted ? delta - wanted : wanted - delta;
        if (e * 100U > wanted * 45U) {
            match = false;
        }
        if (match) {
            if (found >= 0) {
                return false;
            }
            found = (int)k;
        }
    }
    if (found < 0) {
        return false;
    }
    d->symbol = found;
    d->recovered = count == 2U;
    d->reason = V11_VALID;
    d->slope = (int32_t)(delta * 1000000U / dt) * (band == 0U ? 1 : -1);
    return true;
}
