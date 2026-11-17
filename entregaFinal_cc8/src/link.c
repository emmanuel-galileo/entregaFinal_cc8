#include "link.h"
static uint8_t part(const V11 *p) {
    return (uint8_t)((p->tx_frame >> (18U - 6U * p->work)) & 63U);
}
void v11_init(V11 *p, V11Deliver d, void *u) {
    uint8_t *b = (uint8_t *)p;
    for (unsigned n = 0; n < sizeof(*p); ++n) {
        b[n] = 0U;
    }
    p->active = 3U;
    p->permitted = true;
    p->deliver = d;
    p->user = u;
}
unsigned v11_queued(const V11 *p) {
    return (p->head - p->tail) & 511U;
}
bool v11_busy(const V11 *p) {
    return p->frame_present || v11_queued(p) != 0U;
}
bool v11_enqueue(V11 *p, const uint8_t *d, unsigned n) {
    if (n > 511U - v11_queued(p)) {
        return false;
    }
    for (unsigned i = 0; i < n; ++i) {
        const unsigned type = n == 1U       ? V11_FRAME_SINGLE
                              : i == 0U     ? V11_FRAME_START
                              : i + 1U == n ? V11_FRAME_END
                                            : V11_FRAME_CONTINUE;
        const unsigned slot = p->head / 4U, shift = (p->head & 3U) * 2U;
        p->queue_types[slot] = (uint8_t)((p->queue_types[slot] & ~(3U << shift)) | (type << shift));
        p->queue[p->head] = d[i];
        p->head = (uint16_t)((p->head + 1U) & 511U);
    }
    return true;
}
void v11_lease(V11 *p, bool sender) {
    p->permitted = sender;
    p->pending = false;
    p->cached = false;
    p->sequence = 0U;
    if (sender) {
        p->stage = L_BEGIN;
        p->cursor = 0U;
        p->confirmed = 0U;
        p->repair_tries = 0U;
    }
}
static void reset_block(V11 *p) {
    p->stage = L_BEGIN;
    p->cursor = 0U;
    p->confirmed = 0U;
    p->repair_tries = 0U;
}
void v11_prepare(V11 *p, V11Cell *c) {
    if (p->pending) {
        *c = p->cell;
        ++p->retries;
        return;
    }
    if (p->permitted && !p->frame_present && v11_queued(p)) {
        const uint8_t v = p->queue[p->tail];
        const unsigned type = (p->queue_types[p->tail / 4U] >> ((p->tail & 3U) * 2U)) & 3U;
        p->tail = (uint16_t)((p->tail + 1U) & 511U);
        p->tx_frame = v10_frame(p->crc_kind, (uint8_t)((type << 2U) | p->frame_seq), v);
        if (p->corrupt_next) {
            p->tx_frame ^= 1UL << 4U;
            p->corrupt_next = false;
        }
        p->frame_present = true;
        p->normal_block = 0U;
        p->work = 0U;
        p->repairing = false;
        reset_block(p);
    }
    c->seq = p->sequence;
    c->kind = 0U;
    c->mask = 0U;
    c->arg = 0U;
    c->stage = p->stage;
    c->real = p->permitted && p->frame_present;
    c->indices[0] = 0U;
    c->indices[1] = 0U;
    c->data[0] = (uint8_t)(p->round & 1U);
    c->data[1] = (uint8_t)((p->round + 1U) & 1U);
    if (c->real) {
        if (p->stage == L_BEGIN || p->stage == L_CHECK || p->stage == L_REPAIR) {
            c->kind = 1U;
            c->arg = p->stage == L_REPAIR ? (p->repair_index & 3U) : p->work;
            c->mask = p->stage == L_BEGIN   ? 0U
                      : p->stage == L_CHECK ? 1U
                                            : (p->repair_index < 4U ? 2U : 3U);
            c->data[0] = c->arg;
            c->data[1] = c->arg;
        } else {
            c->mask = p->active;
            const uint8_t word = v10_word(part(p));
            unsigned index = p->stage == L_REPAIR_DATA ? p->repair_index : p->cursor;
            if (p->stage == L_DATA && index == 7U && c->mask == 3U) {
                c->mask = 1U;
            }
            for (unsigned lane = 0; lane < 2U; ++lane) {
                if (c->mask & (1U << lane)) {
                    c->indices[lane] = (uint8_t)index;
                    c->data[lane] = (word >> index) & 1U;
                    if (p->stage != L_REPAIR_DATA) {
                        ++index;
                    }
                }
            }
        }
    }
    c->h[0] = (uint8_t)((c->kind << 1U) | c->seq);
    c->h[1] = c->mask;
    p->cell = *c;
    p->pending = true;
}
static int checked_block(V11 *p) {
    uint8_t data, fixed;
    if (!p->rx_context || p->rx_cursor != 8U ||
        !v10_recover(p->rx_values, p->rx_known, &data, &fixed)) {
        return 1;
    }
    for (unsigned f = fixed & ~p->rx_fixed; f; f >>= 1U) {
        p->fec_bits += f & 1U;
    }
    p->rx_fixed |= fixed;
    const unsigned shift = 18U - 6U * p->rx_block;
    p->rx_frame = (p->rx_frame & ~(63UL << shift)) | ((uint32_t)data << shift);
    p->rx_mask |= (uint8_t)(1U << p->rx_block);
    if (p->rx_block == 3U || p->rx_final) {
        p->rx_final = true;
        if (p->rx_mask != 15U || !v10_frame_valid(p->crc_kind, p->rx_frame)) {
            ++p->frame_bad;
            return 2;
        }
        const unsigned control = p->rx_frame >> 20U;
        const uint8_t value = (uint8_t)(p->rx_frame >> 12U);
        if ((control & 3U) == p->rx_frame_seq) {
            const unsigned type = control >> 2U;
            const bool opening = type == V11_FRAME_START || type == V11_FRAME_SINGLE;
            if (opening == p->rx_message_open) {
                ++p->type_bad;
                return 2;
            }
            p->rx_message_open = type == V11_FRAME_START || type == V11_FRAME_CONTINUE;
            p->rx_frame_seq = (uint8_t)((p->rx_frame_seq + 1U) & 3U);
            ++p->rx_bytes;
            if (p->deliver) {
                p->deliver(p->user, value);
            }
        }
        p->rx_done = true;
        p->rx_final = false;
    }
    return 0;
}
void v11_receive(V11 *p, const int h0[2], const int h1[2], const int d[2], int reply[2]) {
    unsigned valid = 0U;
    for (unsigned l = 0; l < 2U; ++l) {
        reply[l] = 3;
        if (h0[l] >= 0 && h0[l] < 4 && h1[l] >= 0 && h1[l] < 4) {
            valid |= 1U << l;
        }
    }
    if (valid == 3U && (h0[0] != h0[1] || h1[0] != h1[1])) {
        valid = 0U;
    }
    if (!valid) {
        ++p->header_bad;
        return;
    }
    const unsigned lane = valid & 1U ? 0U : 1U, h = (unsigned)h0[lane], arg = (unsigned)h1[lane],
                   seq = h & 1U;
    if (p->cached && seq == p->last_seq) {
        if (p->last_h[0] != h || p->last_h[1] != arg) {
            ++p->header_bad;
            return;
        }
        ++p->duplicates;
        for (unsigned l = 0; l < 2U; ++l) {
            if (valid & (1U << l)) {
                reply[l] = p->last_reply[l];
                if (reply[l] == 3) {
                    if (!(h & 2U)) {
                        reply[l] = d[l] >= 0 && d[l] < 2 ? 1 - d[l] : 2;
                    } else if (d[l] == p->last_arg) {
                        reply[l] = p->last_reply[l ^ 1U];
                    }
                }
            }
        }
        return;
    }
    if (h & 2U) {
        int value = -1;
        unsigned payload = 0U;
        for (unsigned l = 0; l < 2U; ++l) {
            if ((valid & (1U << l)) && d[l] >= 0 && d[l] < 4) {
                if (value >= 0 && value != d[l]) {
                    ++p->header_bad;
                    return;
                }
                value = d[l];
                payload |= 1U << l;
            }
        }
        if (value < 0) {
            return;
        }
        p->last_arg = (uint8_t)value;
        int result = 0;
        if (arg == 0U) {
            if (value == 0 && p->rx_done) {
                p->rx_mask = 0U;
                p->rx_frame = 0U;
                p->rx_done = false;
                p->rx_final = false;
            }
            p->rx_block = (uint8_t)value;
            p->rx_known = 0U;
            p->rx_values = 0U;
            p->rx_fixed = 0U;
            p->rx_cursor = 0U;
            p->rx_repairing = false;
            p->rx_context = true;
            p->rx_mask &= (uint8_t)~(1U << value);
        } else if (arg == 1U) {
            result = p->rx_context && p->rx_block == (unsigned)value ? checked_block(p) : 2;
        } else {
            p->rx_repair = (uint8_t)(value + (arg == 3U ? 4U : 0U));
            p->rx_repairing = true;
        }
        for (unsigned l = 0; l < 2U; ++l) {
            if (payload & (1U << l)) {
                reply[l] = result;
            }
        }
    } else {
        unsigned index = p->rx_repairing ? p->rx_repair : p->rx_cursor;
        if (arg && (!p->rx_context || index >= 8U)) {
            return;
        }
        if (p->rx_repairing && arg == 3U && d[0] >= 0 && d[0] < 2 && d[1] >= 0 && d[1] < 2 &&
            d[0] != d[1]) {
            reply[0] = 2;
            reply[1] = 2;
        } else {
            for (unsigned l = 0; l < 2U; ++l) {
                if (valid & (1U << l)) {
                    reply[l] = d[l] >= 0 && d[l] < 2 ? 1 - d[l] : 2;
                }
                if (arg & (1U << l)) {
                    if (index >= 8U) {
                        return;
                    }
                    if (d[l] >= 0 && d[l] < 2) {
                        p->rx_values =
                            (uint8_t)((p->rx_values & ~(1U << index)) | ((unsigned)d[l] << index));
                        p->rx_known |= (uint8_t)(1U << index);
                    } else {
                        p->rx_known &= (uint8_t)~(1U << index);
                    }
                    if (!p->rx_repairing) {
                        ++index;
                    }
                }
            }
        }
        if (!p->rx_repairing) {
            p->rx_cursor = (uint8_t)index;
        }
        if (arg) {
            p->rx_repairing = false;
        }
    }
    p->cached = true;
    p->last_seq = (uint8_t)seq;
    p->last_h[0] = (uint8_t)h;
    p->last_h[1] = (uint8_t)arg;
    p->last_reply[0] = reply[0];
    p->last_reply[1] = reply[1];
    if (p->drop_ack) {
        p->drop_ack = false;
        reply[0] = 3;
        reply[1] = 3;
    }
}
static void health(V11 *p, unsigned lane, bool good) {
    ++p->pilot_tests[lane];
    const unsigned mask = 1U << lane;
    if (good) {
        if (p->good[lane] < 3U) {
            ++p->good[lane];
        }
        if (!(p->active & mask) && p->good[lane] >= 3U) {
            p->active |= (uint8_t)mask;
            ++p->restores[lane];
        }
    } else {
        ++p->primed_bad[lane];
        p->good[lane] = 0U;
        if (p->active & mask) {
            p->active &= (uint8_t)~mask;
            ++p->suspensions[lane];
        }
    }
}
void v11_pilot(V11 *p, unsigned lane, unsigned sent, int primed) {
    if (lane < 2U) {
        health(p, lane, primed >= 0 && primed < 2 && ((unsigned)primed ^ sent) == 1U);
    }
}
static void next_repair(V11 *p) {
    for (unsigned i = 0; i < 8U; ++i) {
        if (p->repair_set & (1U << i)) {
            p->repair_index = (uint8_t)i;
            p->repair_set &= (uint8_t)~(1U << i);
            p->stage = L_REPAIR;
            return;
        }
    }
    p->stage = L_CHECK;
}
void v11_finish(V11 *p, const int r[2], unsigned tested) {
    bool accepted = false;
    int result = -1;
    const V11Cell *c = &p->cell;
    for (unsigned l = 0; l < 2U; ++l) {
        if (tested & (1U << l)) {
            const bool valid = r[l] >= 0 && r[l] < 3;
            bool good = valid;
            if (c->kind == 0U) {
                good = valid && r[l] < 2 && ((unsigned)r[l] ^ c->data[l]) == 1U;
            }
            health(p, l, good);
            if (valid) {
                accepted = true;
                if (result < 0) {
                    result = r[l];
                } else if (c->kind && result != r[l]) {
                    accepted = false;
                    result = 3;
                }
            }
            if (c->kind == 0U && (c->mask & (1U << l)) && good) {
                p->confirmed |= (uint8_t)(1U << c->indices[l]);
            }
        }
    }
    ++p->round;
    if (!accepted || result == 3) {
        return;
    }
    p->pending = false;
    p->sequence ^= 1U;
    if (!c->real) {
        return;
    }
    if (c->stage == L_BEGIN) {
        p->stage = L_DATA;
        p->cursor = 0U;
        p->confirmed = 0U;
    } else if (c->stage == L_DATA) {
        for (unsigned l = 0; l < 2U; ++l) {
            if (c->mask & (1U << l)) {
                ++p->cursor;
            }
        }
        if (p->cursor >= 8U) {
            p->stage = L_CHECK;
        }
    } else if (c->stage == L_REPAIR) {
        p->stage = L_REPAIR_DATA;
    } else if (c->stage == L_REPAIR_DATA) {
        if (c->mask) {
            next_repair(p);
        }
    } else if (c->stage == L_CHECK) {
        if (result == 0) {
            if (p->work == 3U || p->repairing) {
                ++p->tx_bytes;
                p->frame_seq = (uint8_t)((p->frame_seq + 1U) & 3U);
                p->frame_present = false;
                p->repairing = false;
            } else {
                ++p->normal_block;
                p->work = p->normal_block;
                reset_block(p);
            }
        } else if (result == 2) {
            const uint8_t control = (uint8_t)(p->tx_frame >> 20U),
                          value = (uint8_t)(p->tx_frame >> 12U);
            p->tx_frame = v10_frame(p->crc_kind, control, value);
            p->work = p->repairing ? (uint8_t)(p->work ? p->work - 1U : 3U) : 3U;
            p->repairing = true;
            reset_block(p);
        } else {
            ++p->repair_tries;
            p->repair_set = (uint8_t)~p->confirmed;
            if (!p->repair_set || p->repair_tries >= 3U) {
                reset_block(p);
            } else {
                next_repair(p);
            }
        }
    }
}
