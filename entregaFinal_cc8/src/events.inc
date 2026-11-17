#define EVENT_WORDS 12U
#define EVENT_SLOTS 16U
static uint32_t events[EVENT_SLOTS][EVENT_WORDS];
static volatile unsigned event_head, event_tail;
static volatile uint32_t event_drops;
static bool events_enabled;
static uint32_t event_round;
static void event_push(const uint32_t *words) {
    const uint32_t state = __get_PRIMASK();
    __disable_irq();
    const unsigned next = (event_head + 1U) & (EVENT_SLOTS - 1U);
    if (next == event_tail) {
        ++event_drops;
    } else {
        for (unsigned n = 0; n < EVENT_WORDS; ++n) {
            events[event_head][n] = words[n];
        }
        event_head = next;
    }
    __set_PRIMASK(state);
}
static void event_sweep(unsigned lane, unsigned tag, unsigned band, bool turbo,
                        const V10Sweep *s, const V11Decision *d) {
    if (!events_enabled) { return; }
    uint32_t v[EVENT_WORDS] = {0};
    v[0] = 1U | (tag << 8U) | (lane << 16U) | (band << 17U) |
           ((uint32_t)turbo << 18U) | ((uint32_t)d->recovered << 19U) |
           ((uint32_t)d->valid << 20U) | ((uint32_t)d->reason << 24U);
    v[1] = ticks;
    for (unsigned n = 0; n < 3U; ++n) {
        v[2U + n] = (s->hz[n] & 65535U) | (s->edges[n] << 16U);
    }
    v[5] = s->window_us[0] / 1000U | ((s->window_us[1] / 1000U) << 16U);
    v[6] = s->window_us[2] / 1000U | ((uint32_t)(d->symbol + 1) << 16U);
    v[7] = (uint32_t)d->slope;
    v[8] = event_round;
    v[9] = q_start;
    v[11] = 0x10000000U;
    event_push(v);
}
static void event_quantum(bool sender, bool repairing) {
    if (!events_enabled) { return; }
    uint32_t v[EVENT_WORDS] = {0};
    const int h = received[0][0] >= 0 ? received[0][0] : received[0][1];
    const int a = received[1][0] >= 0 ? received[1][0] : received[1][1];
    const unsigned kind = sender ? prepared.kind : (h >= 0 ? ((unsigned)h >> 1U) : 0U);
    const unsigned mask = sender ? prepared.mask : (a >= 0 ? (unsigned)a : 0U);
    const unsigned block = sender ? (kind ? prepared.arg : protocol->work) : protocol->rx_block;
    const unsigned stage = sender ? prepared.stage : h < 0 || a < 0 ? 15U :
        kind ? (mask == 0U ? L_BEGIN : mask == 1U ? L_CHECK : L_REPAIR) :
        repairing ? L_REPAIR_DATA : L_DATA;
    const unsigned count = (mask & 1U) + ((mask >> 1U) & 1U);
    unsigned index = repairing ? protocol->rx_repair :
        protocol->rx_cursor >= count ? protocol->rx_cursor - count : 0U;
    const unsigned i0 = sender ? prepared.indices[0] : index;
    if (!repairing && (mask & 1U)) { ++index; }
    const unsigned i1 = sender ? prepared.indices[1] : index;
    v[0] = 2U | ((uint32_t)sender << 8U) | (kind << 9U) |
        ((uint32_t)current_turbo << 10U) | ((uint32_t)protocol->active << 11U) |
        ((uint32_t)(sender ? prepared.real : h >= 0 && (kind || mask)) << 13U) |
        ((uint32_t)(sender ? prepared.seq : (h >= 0 ? h & 1 : 0)) << 14U) |
        ((uint32_t)(sender ? !protocol->frame_present : protocol->rx_done) << 15U) |
        (stage << 16U) | (mask << 20U) | ((block & 3U) << 24U) |
        ((uint32_t)protocol->crc_kind << 28U);
    v[1] = ticks;
    v[2] = event_round;
    v[3] = sender ? protocol->tx_frame : protocol->rx_frame;
    v[4] = protocol->rx_known | ((uint32_t)protocol->rx_values << 8U) |
        ((uint32_t)protocol->rx_fixed << 16U) | ((uint32_t)protocol->rx_mask << 24U);
    v[5] = sender ? prepared.data[0] | ((uint32_t)prepared.data[1] << 8U) :
        (uint32_t)(received[2][0] + 1) | ((uint32_t)(received[2][1] + 1) << 8U);
    const int *const replies = sender ? reply_in : reply_out;
    v[6] = (uint32_t)(replies[0] + 1) | ((uint32_t)(replies[1] + 1) << 8U) |
        (i0 << 16U) | (i1 << 24U);
    v[7] = q_step | (q_period << 16U);
    v[8] = protocol->fec_bits;
    v[9] = protocol->frame_bad;
    v[10] = sender ? protocol->tx_bytes : protocol->rx_bytes;
    v[11] = (sender ? prepared.h[0] : (h >= 0 ? (unsigned)h : 255U)) |
        ((sender ? prepared.h[1] : (a >= 0 ? (unsigned)a : 255U)) << 8U) |
        ((erase_this | (flip_this << 2U) | (notch_this << 4U)) << 16U) |
        ((0x10U | notch_step) << 24U);
    event_push(v);
}
void hw11_events(bool enabled) {
    const uint32_t state = __get_PRIMASK();
    __disable_irq();
    events_enabled = enabled;
    event_head = event_tail = 0U;
    __set_PRIMASK(state);
}
void hw11_pump_events(void) {
    static const char digits[] = "0123456789ABCDEF";
    if (event_head == event_tail) { return; }
    uint32_t v[EVENT_WORDS];
    const uint32_t state = __get_PRIMASK();
    __disable_irq();
    for (unsigned n = 0; n < EVENT_WORDS; ++n) { v[n] = events[event_tail][n]; }
    event_tail = (event_tail + 1U) & (EVENT_SLOTS - 1U);
    __set_PRIMASK(state);
    hw11_puts("@CC8 ");
    for (unsigned n = 0; n < EVENT_WORDS; ++n) {
        for (int shift = 28; shift >= 0; shift -= 4) {
            hw11_putc(digits[(v[n] >> (unsigned)shift) & 15U]);
        }
    }
    hw11_puts("\r\n");
}
