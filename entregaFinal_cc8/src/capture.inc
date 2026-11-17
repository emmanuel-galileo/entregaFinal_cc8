enum { TAG_HS = 0, TAG_H0 = 1, TAG_H1 = 2, TAG_DATA = 3, TAG_ECHO = 4, TAG_PILOT = 5 };
static void symbol_ready(unsigned lane, unsigned tag, const V11Decision *d);
static void cap_begin(unsigned lane, unsigned tag, unsigned step, uint32_t start, uint32_t duration,
                      unsigned band, bool turbo, bool known) {
    volatile Capture *c = &caps[lane];
    c->active = false;
    c->known = known;
    c->lost = false;
    c->tag = tag;
    c->step = step;
    c->start = start;
    c->period = duration;
    c->band = band;
    c->turbo = turbo;
    c->guard = duration >= 100U ? 25U : duration >= 50U ? 12U : 5U;
    c->end = start + duration - 4U;
    c->m.sum = 0;
    c->m.count = 0;
    c->m.edges = 0;
    c->m.bad = 0;
    c->m.matched_sum = 0;
    c->m.matched_n = 0;
    if (step == 0U) {
        for (unsigned n = 0; n < 3U; ++n) {
            c->wave.hz[n] = 0;
            c->wave.periods[n] = 0;
            c->wave.edges[n] = 0;
            c->wave.bad[n] = 0;
            c->wave.window_us[n] = 0;
            c->wave.time_us[n] = 0;
        }
    }
    uint32_t minimum = 65535U, maximum = 0U;
    for (unsigned k = 0; k < 4U; ++k) {
        const uint32_t f = v11_frequency(band, lane, k, turbo, step), p = 1000000U / f;
        if (p < minimum) {
            minimum = p;
        }
        if (p > maximum) {
            maximum = p;
        }
    }
    c->pmin = minimum * 90U / 100U;
    c->pmax = maximum * 110U / 100U;
    c->active = true;
}
static void edge(unsigned lane, uint16_t timestamp) {
    volatile Capture *c = &caps[lane];
    const uint16_t dt = (uint16_t)(timestamp - c->m.last);
    const bool have = c->m.have;
    c->m.last = timestamp;
    c->m.have = true;
    if (!c->active) {
        return;
    }
    const uint32_t age = ticks - c->start;
    if (age < c->guard || age >= c->period - 4U) {
        return;
    }
    ++c->m.edges;
    if (!have) {
        return;
    }
    if (dt < 100U || dt > 55000U) {
        ++c->m.bad;
        return;
    }
    c->m.sum += dt;
    ++c->m.count;
    if (dt >= c->pmin && dt <= c->pmax) {
        c->m.matched_sum += dt;
        ++c->m.matched_n;
    }
}
void TIM3_IRQHandler(void) {
    const uint32_t sr = TIM3->SR;
    if (sr & TIM_SR_CC4IF) {
        const uint16_t t = (uint16_t)TIM3->CCR4;
        TIM3->SR = ~(TIM_SR_CC4IF | TIM_SR_CC4OF);
        ++stats.ir_edges;
        if (sr & TIM_SR_CC4OF) {
            ++stats.capture_overruns;
            if (caps[0].active) {
                ++stats.capture_window_overruns;
                caps[0].lost = true;
            }
            caps[0].m.have = false;
        }
        edge(0U, t);
    }
}
void EXTI1_IRQHandler(void) {
    if (EXTI->PR & EXTI_PR_PR1) {
        EXTI->PR = EXTI_PR_PR1;
        ++stats.mic_edges;
        if (GPIOA->IDR & 2U) {
            edge(1U, (uint16_t)TIM3->CNT);
        }
    }
}
__attribute__((noinline)) static void cap_end(unsigned lane) {
    volatile Capture *c = &caps[lane];
    c->active = false;
    const unsigned s = c->step;
    uint32_t sum = lane ? c->m.matched_sum : c->m.sum, n = lane ? c->m.matched_n : c->m.count;
    if (c->lost) {
        sum = 0;
        n = 0;
    }
    c->wave.hz[s] = sum ? (n * 1000000U + sum / 2U) / sum : 0;
    c->wave.periods[s] = n;
    c->wave.edges[s] = c->m.edges;
    c->wave.bad[s] = lane ? 0 : c->m.bad;
    c->wave.window_us[s] = (c->period - 4U - c->guard) * 1000U;
    c->wave.time_us[s] = s * c->period * 1000U + c->guard * 1000U + c->wave.window_us[s] / 2U;
    if (s == 2U) {
        V10Sweep wave;
        for (unsigned k = 0; k < 3U; ++k) {
            wave.hz[k] = c->wave.hz[k];
            wave.periods[k] = c->wave.periods[k];
            wave.edges[k] = c->wave.edges[k];
            wave.bad[k] = c->wave.bad[k];
            wave.window_us[k] = c->wave.window_us[k];
            wave.time_us[k] = c->wave.time_us[k];
        }
        V11Decision d;
        (void)v11_decode(c->band, lane, c->turbo, &wave, &d);
        if (d.reason == V11_SILENCE) {
            ++stats.silence;
        } else if (d.reason == V11_INVALID) {
            ++stats.invalid;
        }
        if (d.recovered) {
            if (c->tag == TAG_DATA) {
                ++stats.local_data;
            } else if (c->tag == TAG_ECHO || c->tag == TAG_PILOT) {
                ++stats.local_echo;
            } else if (c->tag == TAG_HS) {
                ++stats.local_hs;
            } else {
                ++stats.local_control;
            }
        }
        event_sweep(lane, c->tag, c->band, c->turbo, &wave, &d);
        symbol_ready(lane, c->tag, &d);
    }
}
