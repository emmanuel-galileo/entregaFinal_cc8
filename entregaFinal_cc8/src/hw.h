#ifndef PHY11_HW_H
#define PHY11_HW_H
#include "link.h"
#include "version.h"
#define V11_BUILD APP_BUILD
typedef struct {
    uint32_t clocks, clock_bad, uart_errors, uart_drops, capture_overruns, capture_window_overruns,
        ir_edges, mic_edges;
    uint32_t rounds, period_ms, interval_ms, deadline_miss, local_data, local_echo, local_control,
        local_hs, silence, invalid;
    uint32_t turbo_enter, turbo_exit, pilot_pairs, pilot_skipped, pilot_step_ms, pilot_pair_ms;
    int received[2], returned[2];
    uint8_t sent[2];
    uint32_t active, fec, quantum_kind, turbo, phase;
} V11Stats;
void hw11_init(V11 *p);
void hw11_node(unsigned n);
void hw11_start(void);
void hw11_stop(void);
void hw11_probe(void);
bool hw11_running(void);
bool hw11_read(char *c);
uint32_t hw11_now(void);
void hw11_putc(char c);
void hw11_puts(const char *s);
void hw11_number(uint32_t n);
void hw11_signed(int n);
void hw11_status(void);
void hw11_log(void);
void hw11_samples(void);
void hw11_events(bool enabled);
void hw11_pump_events(void);
void hw11_mac_log(void);
uint32_t hw11_event(void);
bool hw11_rate(const char *mode);
bool hw11_boost(bool on);
void hw11_fault(unsigned mask);
void hw11_inject(unsigned mask, bool flip);
void hw11_notch(unsigned mask, unsigned step);
void hw11_threshold(uint32_t n);
void hw11_manual(unsigned kind, bool on);
void hw11_mic(void);
const V11Stats *hw11_stats(void);
#endif
