#include "hw.h"
#include "base/mac.h"
#include "stm32f3xx.h"
#define UART_SIZE 512U
static V11 *protocol;
static V10Mac mac;
static volatile uint32_t ticks;
static volatile bool running;
static const bool clock_inverted = APP_RX_ACTIVE_LOW != 0U;
static volatile char uart[UART_SIZE];
static volatile unsigned head, tail;
static volatile V11Stats stats;
static unsigned node = 2U;
static uint32_t periods[2] = {370, 370};
static volatile unsigned faults;
static bool ir_on, sound_on;
static uint32_t mic_history[32], ir_history[32], threshold20 = 60;
static unsigned selected_profile = 0U;
static bool irboost = true;
static volatile unsigned lease_profile, lease_cfg, tx_band, rx_band;
static volatile bool lease, leader;
static volatile uint32_t base_period = 1000, base_step = 75;
static volatile uint32_t q_start, last_q_start, next_q_at, q_period = 1000, q_step = 75, rx_start,
                                                           ack_start;
static volatile unsigned substep, ack_step;
static volatile bool q_active, q_finished, ack_running, ack_ready, current_turbo;
static volatile unsigned pair_phase;
static V11Cell prepared;
static int received[4][2], reply_out[2], reply_in[2];
static unsigned erase_next, erase_this, flip_next, flip_this, notch_next, notch_this, notch_step;
static bool probe_only, lease_done;
static uint32_t lease_bytes, lease_round, last_header;
static volatile bool hs_tx, hs_rx, hs_aligned;
static volatile int hs_next = -1;
static volatile uint32_t hs_due, hs_tx_at, hs_rise, hs_deadline;
static volatile unsigned hs_kind, hs_index, hs_rx_kind, hs_rx_index, hs_count, hs_codes[4], hs_got;
static int hs_results[2];
static volatile bool sfd_wait;
static unsigned release_count;
static bool release_level;
static uint32_t pulse_off, ack_off;
static bool pilot_running, pilot_tx, pilot_receiver, pilot_scored;
static unsigned pilot_step, pilot_bit;
static int saved_pilot = -1;
static uint32_t pilot_start, pilot_duration;
typedef struct {
    uint32_t sum, count, edges, bad, matched_sum, matched_n;
    uint16_t last;
    bool have;
} Meter;
typedef struct {
    bool active, known, lost, turbo;
    unsigned band, step, tag;
    uint32_t start, period, guard, end, pmin, pmax;
    Meter m;
    V10Sweep wave;
} Capture;
static volatile Capture caps[2];
static const uint16_t profile_period[4] = {1000, 800, 1000, 2000},
                      profile_step[4] = {75, 60, 75, 150};
static void mode(GPIO_TypeDef *port, unsigned pin, unsigned value) {
    port->MODER = (port->MODER & ~(3UL << (2U * pin))) | (value << (2U * pin));
}
static void alternate(GPIO_TypeDef *port, unsigned pin, unsigned af) {
    const unsigned shift = (pin % 8U) * 4U;
    port->AFR[pin / 8U] = (port->AFR[pin / 8U] & ~(15UL << shift)) | (af << shift);
    mode(port, pin, 2U);
}
static void clock_out(bool on) {
    GPIOB->BSRR = 1UL << (5U + (on ? 0U : 16U));
}
static bool clock_in_active(void) {
    return ((GPIOA->IDR & (1UL << 7U)) != 0U) != clock_inverted;
}
static void led(bool on) {
    GPIOB->BSRR = 1UL << (3U + (on ? 0U : 16U));
}
static void carrier(unsigned lane, uint32_t hz, bool on) {
    TIM_TypeDef *const timer = lane == 0U ? TIM1 : TIM2;
    const uint32_t period = (1000000U + hz / 2U) / hz;
    timer->CR1 &= ~TIM_CR1_CEN;
    timer->ARR = period - 1U;
    periods[lane] = period;
    on = on && !(faults & (1U << lane));
    timer->CCR1 = on ? period / 2U : (lane == 0U ? 0U : period);
    timer->CNT = 0U;
    timer->EGR = TIM_EGR_UG;
    timer->SR = 0U;
    timer->CR1 |= TIM_CR1_CEN;
    if (lane == 0U) {
        ir_on = on;
    } else {
        sound_on = on;
    }
}

#include "events.inc"
#include "capture.inc"
void USART2_IRQHandler(void) {
    const uint32_t sr = USART2->ISR;
    if (sr & (USART_ISR_ORE | USART_ISR_FE | USART_ISR_NE)) {
        ++stats.uart_errors;
        USART2->ICR = USART_ICR_ORECF | USART_ICR_FECF | USART_ICR_NCF;
    }
    if (sr & USART_ISR_RXNE) {
        const char c = (char)USART2->RDR;
        const unsigned next = (head + 1U) & (UART_SIZE - 1U);
        if (next == tail) {
            ++stats.uart_drops;
        } else {
            uart[head] = c;
            head = next;
        }
    }
}

#include "timing.inc"
void hw11_init(V11 *link) {
    protocol = link;
    RCC->CR |= RCC_CR_HSION;
    while (!(RCC->CR & RCC_CR_HSIRDY)) {
    }
    RCC->CFGR &= ~RCC_CFGR_SW;
    while ((RCC->CFGR & RCC_CFGR_SWS) != RCC_CFGR_SWS_HSI) {
    }
    RCC->CFGR &= ~(RCC_CFGR_HPRE | RCC_CFGR_PPRE1 | RCC_CFGR_PPRE2);
    SystemCoreClockUpdate();
    RCC->AHBENR |= RCC_AHBENR_GPIOAEN | RCC_AHBENR_GPIOBEN;
    (void)RCC->AHBENR;
    mode(GPIOA, 12U, 3U);
    mode(GPIOA, 4U, 3U);
    mode(GPIOB, 4U, 3U);
    mode(GPIOB, 0U, 3U);
    GPIOA->PUPDR &= ~((3UL << 24U) | (3UL << 8U));
    GPIOB->PUPDR &= ~((3UL << 8U) | 3UL);
    GPIOB->BSRR = (1UL << 21U) | (1UL << 19U);
    GPIOB->OTYPER &= ~((1UL << 5U) | (1UL << 3U));
    mode(GPIOB, 5U, 1U);
    mode(GPIOB, 3U, 1U);
    GPIOA->BSRR = (1UL << 24U) | 1UL;
    GPIOA->OTYPER &= ~((1UL << 8U) | 1UL);
    GPIOA->PUPDR &= ~((3UL << 16U) | 3UL);
    RCC->APB1ENR |= RCC_APB1ENR_TIM2EN | RCC_APB1ENR_TIM3EN | RCC_APB1ENR_USART2EN;
    RCC->APB2ENR |= RCC_APB2ENR_TIM1EN | RCC_APB2ENR_SYSCFGEN;
    TIM1->CR1 = TIM_CR1_ARPE;
    TIM1->PSC = 7U;
    TIM1->CCMR1 = TIM_CCMR1_OC1M_1 | TIM_CCMR1_OC1M_2 | TIM_CCMR1_OC1PE;
    TIM1->CCER = TIM_CCER_CC1E;
    TIM1->BDTR = TIM_BDTR_MOE;
    TIM2->CR1 = TIM_CR1_ARPE;
    TIM2->PSC = 7U;
    TIM2->CCMR1 = TIM_CCMR1_OC1M_1 | TIM_CCMR1_OC1M_2 | TIM_CCMR1_OC1PE;
    TIM2->CCER = TIM_CCER_CC1E;
    carrier(0U, 2700U, false);
    carrier(1U, 2700U, false);
    alternate(GPIOA, 8U, 6U);
    alternate(GPIOA, 0U, 1U);
    /* Capturas independientes para los dos canales. */
    alternate(GPIOB, 1U, 2U);
    GPIOB->PUPDR = (GPIOB->PUPDR & ~(3UL << 2U)) | (1UL << 2U);
    TIM3->CR1 = 0U;
    TIM3->PSC = 7U;
    TIM3->ARR = 65535U;
    /* fDTS/32, ocho muestras: rechazar pulsos <32 us antes de capturarlos. */
    TIM3->CCMR2 = TIM_CCMR2_CC4S_0 | (15UL << 12U);
    TIM3->CCER = TIM_CCER_CC4E;
    TIM3->EGR = TIM_EGR_UG;
    TIM3->SR = 0U;
    TIM3->DIER = TIM_DIER_CC4IE;
    NVIC_SetPriority(TIM3_IRQn, 1U);
    NVIC_EnableIRQ(TIM3_IRQn);
    TIM3->CR1 = TIM_CR1_CEN;
    mode(GPIOA, 1U, 0U);
    mode(GPIOA, 7U, 0U);
    GPIOA->PUPDR = (GPIOA->PUPDR & ~((3UL << 2U) | (3UL << 14U))) | (1UL << 2U) | ((APP_RX_ACTIVE_LOW ? 1UL : 2UL) << 14U);
    SYSCFG->EXTICR[0] &= ~(15UL << 4U);
    SYSCFG->EXTICR[1] &= ~(15UL << 12U);
    EXTI->IMR &= ~EXTI_IMR_MR4;
    EXTI->RTSR &= ~EXTI_RTSR_TR4;
    EXTI->FTSR &= ~EXTI_FTSR_TR4;
    NVIC_DisableIRQ(EXTI4_IRQn);
    NVIC_ClearPendingIRQ(EXTI4_IRQn);
    EXTI->PR = EXTI_PR_PR1 | EXTI_PR_PR4 | EXTI_PR_PR7;
    EXTI->RTSR |= EXTI_RTSR_TR1 | EXTI_RTSR_TR7;
    EXTI->FTSR |= EXTI_FTSR_TR1 | EXTI_FTSR_TR7;
    EXTI->IMR |= EXTI_IMR_MR1 | EXTI_IMR_MR7;
    NVIC_SetPriority(EXTI9_5_IRQn, 1U);
    NVIC_EnableIRQ(EXTI9_5_IRQn);
    NVIC_SetPriority(EXTI1_IRQn, 1U);
    NVIC_EnableIRQ(EXTI1_IRQn);
    alternate(GPIOA, 2U, 7U);
    alternate(GPIOA, 15U, 7U);
    USART2->CR1 = 0U;
    USART2->CR2 = 0U;
    USART2->CR3 = 0U;
    USART2->BRR = (SystemCoreClock + 57600U) / 115200U;
    USART2->ICR = USART_ICR_ORECF | USART_ICR_FECF | USART_ICR_NCF;
    USART2->CR1 = USART_CR1_TE | USART_CR1_RE | USART_CR1_RXNEIE | USART_CR1_UE;
    NVIC_SetPriority(USART2_IRQn, 0U);
    NVIC_EnableIRQ(USART2_IRQn);
    (void)SysTick_Config(SystemCoreClock / 1000U);
    NVIC_SetPriority(SysTick_IRQn, 2U);
    protocol->permitted = false;
}
uint32_t hw11_now(void) {
    return ticks;
}
bool hw11_read(char *c) {
    if (head == tail) {
        return false;
    }
    *c = uart[tail];
    tail = (tail + 1U) & (UART_SIZE - 1U);
    return true;
}
void hw11_putc(char c) {
    while (!(USART2->ISR & USART_ISR_TXE)) {
    }
    USART2->TDR = (uint8_t)c;
}
void hw11_puts(const char *s) {
    while (*s) {
        hw11_putc(*s++);
    }
}
void hw11_number(uint32_t n) {
    char b[11];
    unsigned used = 0;
    do {
        b[used++] = (char)('0' + n % 10U);
        n /= 10U;
    } while (n);
    while (used) {
        hw11_putc(b[--used]);
    }
}
void hw11_signed(int n) {
    if (n < 0) {
        hw11_putc('-');
        hw11_number((uint32_t)-n);
    } else {
        hw11_number((uint32_t)n);
    }
}
bool hw11_running(void) {
    return running;
}
void hw11_stop(void) {
    const uint32_t s = __get_PRIMASK();
    __disable_irq();
    running = false;
    mac_stop(&mac);
    clear_exchange();
    __set_PRIMASK(s);
}
void hw11_node(unsigned n) {
    hw11_stop();
    node = n < 2U ? n : 2U;
    threshold20 = n == 1U ? 90U : 60U;
    mac_init(&mac, node);
}
void hw11_start(void) {
    hw11_stop();
    if (node > 1U) {
        return;
    }
    mac_start(&mac, ticks);
    running = true;
}
void hw11_probe(void) {
    if (!running) {
        hw11_start();
    }
    mac.probe = true;
}
static bool same(const char *a, const char *b) {
    while (*a && *a == *b) {
        ++a;
        ++b;
    }
    return *a == *b;
}
bool hw11_rate(const char *s) {
    if (running) {
        return false;
    }
    if (same(s, "log") || same(s, "demo")) {
        selected_profile = 0U;
        return true;
    }
    if (same(s, "max")) {
        selected_profile = 1U;
        return true;
    }
    if (same(s, "1")) {
        selected_profile = 2U;
        return true;
    }
    if (same(s, "1.25")) {
        selected_profile = 1U;
        return true;
    }
    if (same(s, "0.5")) {
        selected_profile = 3U;
        return true;
    }
    return false;
}
bool hw11_boost(bool on) {
    if (running) {
        return false;
    }
    irboost = on;
    return true;
}
void hw11_fault(unsigned m) {
    faults = m & 3U;
}
void hw11_inject(unsigned m, bool flip) {
    if (flip) {
        flip_next = m & 3U;
    } else {
        erase_next = m & 3U;
    }
}
void hw11_notch(unsigned m, unsigned step) {
    if (step < 3U) {
        notch_step = step;
        notch_next = m & 3U;
    }
}
void hw11_threshold(uint32_t n) {
    if (n && n <= 500U) {
        threshold20 = n;
    }
}
void hw11_manual(unsigned kind, bool on) {
    if (running) {
        return;
    }
    if (kind < 2U) {
        carrier(kind, 2700, on);
        if (kind == 0U) {
            TIM1->CCR1 = on && !(faults & 1U) ? periods[0] : 0U;
        }
    } else if (kind == 2U) {
        clock_out(on);
    } else {
        led(on);
    }
}
void hw11_mic(void) {
    const uint32_t now = ticks;
    hw11_puts("MIC20=");
    hw11_number(mic_history[now & 31U] - mic_history[(now - 20U) & 31U]);
    hw11_puts(" THRESHOLD=");
    hw11_number(threshold20);
    hw11_puts("\r\n");
}
const V11Stats *hw11_stats(void) {
    return (const V11Stats *)&stats;
}
uint32_t hw11_event(void) {
    return mac.event_id + (uint32_t)stats.turbo_enter + (uint32_t)stats.turbo_exit +
           (uint32_t)stats.phase;
}
void hw11_mac_log(void) {
    static const char *const names[] = {"READY",     "SYN_TX",      "SYN_RX",     "FIRST_EDGE_WIN",
                                        "TIE_WIN_A", "TIE_YIELD_B", "SYN_ACK_TX", "ESTABLISHED",
                                        "TIMEOUT",   "REJECT",      "RELEASE",    "BUSY_BACKOFF"};
    hw11_puts("PHY_HS EVENT=");
    hw11_puts(names[mac.event]);
    hw11_puts(" STATE=");
    hw11_number(mac.state);
    hw11_puts(" REQ=");
    hw11_number(mac.requests);
    hw11_puts(" ACCEPT=");
    hw11_number(mac.accepted);
    hw11_puts(" TIMEOUT=");
    hw11_number(mac.timeouts);
    hw11_puts(" TIE_WIN=");
    hw11_number(mac.tie_wins);
    hw11_puts(" YIELD=");
    hw11_number(mac.yields);
    hw11_puts(" FRAMES=");
    hw11_number(mac.frames);
    hw11_puts("\r\n");
    hw11_puts("PHY_RATE PHASE=");
    hw11_puts(!lease ? (stats.phase == 1U ? "SFD_FAST" : "SYN_FAST") : "DATA");
    hw11_puts(" MODE=");
    hw11_puts(lease_profile == 0U ? "DEMO" : current_turbo ? "MAX_IR_X2" : "MAX");
    hw11_puts(" Q_MS=");
    hw11_number(lease ? q_period : 0U);
    hw11_puts(" CLOCK_mHz=");
    hw11_number(lease && q_period ? 1000000U / q_period : 13333U);
    hw11_puts(" CHIRP_STEP_MS=");
    hw11_number(lease ? q_step : 75U);
    hw11_puts("\r\n");
}
void hw11_status(void) {
    hw11_puts("DEVICE VERSION=" APP_VERSION_NAME " BUILD=1105 NODE=");
    hw11_number(node);
    hw11_puts(" CLK=");
    hw11_number(stats.clocks);
    hw11_puts(" CLOCK_BAD=");
    hw11_number(stats.clock_bad);
    hw11_puts(" UART_ERR=");
    hw11_number(stats.uart_errors);
    hw11_puts(" UART_DROP=");
    hw11_number(stats.uart_drops);
    hw11_puts(" CAP_OVR=");
    hw11_number(stats.capture_overruns);
    hw11_puts(" CAP_WIN_OVR=");
    hw11_number(stats.capture_window_overruns);
    hw11_puts(" EVENT_DROP=");
    hw11_number(event_drops);
    hw11_puts("\r\n");
    hw11_puts("CLOCK_RX_RAW=");
    hw11_number((GPIOA->IDR >> 7U) & 1U);
    hw11_puts(" CLOCK_RX_ACTIVE=");
    hw11_number(clock_in_active());
    hw11_puts("\r\n");
    hw11_puts("TIMING PROFILE=");
    hw11_number(selected_profile);
    hw11_puts(" IRBOOST=");
    hw11_number(irboost);
    hw11_puts(" Q_MS=");
    hw11_number(stats.period_ms);
    hw11_puts(" INTERVAL_MS=");
    hw11_number(stats.interval_ms);
    hw11_puts(" DEADLINE_MISS=");
    hw11_number(stats.deadline_miss);
    hw11_puts(" TURBO_ON=");
    hw11_number(stats.turbo_enter);
    hw11_puts(" TURBO_OFF=");
    hw11_number(stats.turbo_exit);
    hw11_puts(" PILOT_PAIRS=");
    hw11_number(stats.pilot_pairs);
    hw11_puts(" PILOT_SKIP=");
    hw11_number(stats.pilot_skipped);
    hw11_puts(" PILOT_STEP_MS=");
    hw11_number(stats.pilot_step_ms);
    hw11_puts(" PILOT_PAIR_MS=");
    hw11_number(stats.pilot_pair_ms);
    hw11_puts(" FAULT=");
    hw11_number(faults);
    hw11_puts("\r\n");
    hw11_puts("LOCAL23_DATA=");
    hw11_number(stats.local_data);
    hw11_puts(" LOCAL23_ECHO=");
    hw11_number(stats.local_echo);
    hw11_puts(" LOCAL23_CTRL=");
    hw11_number(stats.local_control);
    hw11_puts(" LOCAL23_HS=");
    hw11_number(stats.local_hs);
    hw11_puts(" SILENCE=");
    hw11_number(stats.silence);
    hw11_puts(" INVALID=");
    hw11_number(stats.invalid);
    hw11_puts("\r\n");
    hw11_mac_log();
}
void hw11_log(void) {
    V11Stats s;
    const uint32_t m = __get_PRIMASK();
    __disable_irq();
    s = stats;
    __set_PRIMASK(m);
    hw11_puts("Q=");
    hw11_number(s.rounds);
    hw11_puts(" ROLE=");
    hw11_puts(leader ? "TX" : "RX");
    hw11_puts(" Q_MS=");
    hw11_number(s.period_ms);
    hw11_puts(" INTERVAL_MS=");
    hw11_number(s.interval_ms);
    hw11_puts(" TURBO=");
    hw11_number(s.turbo);
    hw11_puts(" ACTIVE=");
    hw11_number(s.active);
    hw11_puts(" KIND=");
    hw11_puts(s.quantum_kind ? "CTRL" : "DATA");
    for (unsigned l = 0; l < 2U; ++l) {
        hw11_puts(l ? " SND=" : " IR=");
        if (leader && s.turbo && l == 1U) {
            hw11_puts("PILOT_PAIR");
            continue;
        }
        hw11_signed(leader ? s.sent[l] : s.received[l]);
        hw11_putc('/');
        hw11_signed(s.returned[l]);
        hw11_puts(s.quantum_kind ? " STATUS=" : " XOR=");
        const int v = leader ? s.sent[l] : s.received[l];
        if (s.quantum_kind) {
            hw11_signed(s.returned[l]);
        } else {
            hw11_signed(v >= 0 && v < 2 && s.returned[l] >= 0 && s.returned[l] < 2
                            ? (v ^ s.returned[l])
                            : -1);
        }
    }
    hw11_puts(" LOCAL23=");
    hw11_number(s.local_data + s.local_echo + s.local_control);
    hw11_puts(" FEC=");
    hw11_number(s.fec);
    hw11_puts(" PILOT_PHASE=");
    hw11_number(pair_phase);
    hw11_puts("\r\n");
}
void hw11_samples(void) {
    for (unsigned l = 0; l < 2U; ++l) {
        hw11_puts("SAMPLE LANE=");
        hw11_number(l);
        for (unsigned n = 0; n < 3U; ++n) {
            hw11_puts(" HZ=");
            hw11_number(caps[l].wave.hz[n]);
            hw11_puts(" EDGES=");
            hw11_number(caps[l].wave.edges[n]);
            hw11_puts(" US=");
            hw11_number(caps[l].wave.window_us[n]);
        }
        hw11_puts("\r\n");
    }
}
