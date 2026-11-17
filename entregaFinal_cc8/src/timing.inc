/* Toda la informacion por barridos. En datos: un pulso fisico por quantum. */
static void off(void) {
    carrier(0, 2700, false);
    carrier(1, 2700, false);
    clock_out(false);
    led(false);
    caps[0].active = false;
    caps[1].active = false;
}
static void clear_exchange(void) {
    lease = false;
    hs_tx = false;
    hs_rx = false;
    hs_aligned = false;
    hs_next = -1;
    sfd_wait = false;
    q_active = false;
    ack_running = false;
    pilot_running = false;
    protocol->permitted = false;
    off();
}
static unsigned cfg_make(unsigned profile, bool boost) {
    unsigned c = profile | ((boost && profile != 0U) ? 4U : 0U);
    return c | (((c ^ (c >> 1U) ^ (c >> 2U)) & 1U) << 3U);
}
static bool cfg_valid(unsigned c) {
    return c < 16U && ((c ^ (c >> 1U) ^ (c >> 2U) ^ (c >> 3U)) & 1U) == 0U &&
           ((c & 3U) != 0U || !(c & 4U));
}
static void set_profile(unsigned cfg) {
    lease_cfg = cfg;
    lease_profile = cfg & 3U;
    base_period = profile_period[lease_profile];
    base_step = profile_step[lease_profile];
}
static void enter_lease(bool initiator) {
    lease = true;
    leader = initiator;
    hs_tx = false;
    hs_rx = false;
    hs_aligned = false;
    hs_next = -1;
    sfd_wait = false;
    tx_band = initiator ? 0U : 1U;
    rx_band = tx_band ^ 1U;
    v11_lease(protocol, initiator);
    lease_bytes = protocol->tx_bytes;
    lease_round = protocol->round;
    probe_only = initiator && !v11_busy(protocol);
    lease_done = false;
    q_active = false;
    q_finished = true;
    ack_running = false;
    ack_ready = false;
    current_turbo = false;
    pair_phase = 1U;
    last_q_start = 0;
    next_q_at = ticks + 80U;
    last_header = ticks;
    pulse_off = 0;
    ack_off = 0;
    q_period = base_period;
    q_step = base_step;
    stats.period_ms = q_period;
    stats.phase = 2U;
}
static void hs_output(unsigned index) {
    const unsigned symbol = hs_codes[index / 3U], step = index % 3U;
    for (unsigned l = 0; l < 2U; ++l) {
        carrier(l, v11_frequency(tx_band, l, symbol, false, step), true);
    }
}
static void hs_begin(unsigned kind) {
    hs_kind = kind;
    hs_index = 0U;
    hs_tx = true;
    hs_rx = false;
    caps[0].active = false;
    caps[1].active = false;
    hs_tx_at = ticks;
    tx_band = (kind == 1U || kind == 3U) ? 1U : 0U;
    rx_band = tx_band ^ 1U;
    if (kind == 0U) {
        set_profile(cfg_make(selected_profile, irboost));
        hs_codes[0] = 3U;
        hs_codes[1] = 3U;
        hs_codes[2] = lease_cfg >> 2U;
        hs_codes[3] = lease_cfg & 3U;
        hs_count = 4U;
    } else if (kind == 1U) {
        hs_codes[0] = lease_cfg >> 2U;
        hs_codes[1] = lease_cfg & 3U;
        hs_count = 2U;
    } else if (kind == 2U) {
        hs_codes[0] = 0U;
        hs_codes[1] = 0U;
        hs_count = 2U;
    } else {
        hs_codes[0] = (lease_cfg ^ 15U) >> 2U;
        hs_codes[1] = (lease_cfg ^ 15U) & 3U;
        hs_count = 2U;
    }
    stats.phase = kind == 2U || kind == 3U ? 1U : 0U;
    hs_output(0U);
    clock_out(true);
}
static void hs_packet_done(void) {
    hs_rx = false;
    caps[0].active = false;
    caps[1].active = false;
    if (hs_rx_kind == 0U) {
        const unsigned cfg = (hs_codes[2] << 2U) | hs_codes[3];
        const bool good = hs_codes[0] == 3U && hs_codes[1] == 3U && cfg_valid(cfg);
        if (good) {
            set_profile(cfg);
        }
        mac_syn_result(&mac, ticks, good);
    } else if (hs_rx_kind == 1U) {
        const bool good = ((hs_codes[0] << 2U) | hs_codes[1]) == lease_cfg;
        mac_ack_result(&mac, ticks, good);
        if (good) {
            hs_next = 2;
            hs_due = ticks + 20U;
        }
    } else if (hs_rx_kind == 2U) {
        if (hs_codes[0] == 0U && hs_codes[1] == 0U) {
            hs_next = 3;
            hs_due = ticks + 20U;
        } else {
            mac_lost(&mac, ticks);
            clear_exchange();
        }
    } else {
        if (((hs_codes[0] << 2U) | hs_codes[1]) == (lease_cfg ^ 15U)) {
            enter_lease(true);
        } else {
            mac_lost(&mac, ticks);
            clear_exchange();
        }
    }
}
static void hs_rising(unsigned kind) {
    if (hs_tx) {
        hs_tx = false;
        off();
    }
    if (!hs_rx) {
        hs_rx = true;
        hs_aligned = false;
        hs_rx_kind = kind;
        hs_rx_index = 0U;
        hs_count = kind == 0U ? 4U : 2U;
    } else {
        ++hs_rx_index;
    }
    if (hs_rx_index >= hs_count * 3U) {
        hs_rx = false;
        return;
    }
    hs_rise = ticks;
    hs_got = 0U;
    rx_band = (kind == 0U || kind == 2U) ? 0U : 1U;
    for (unsigned l = 0; l < 2U; ++l) {
        cap_begin(l, TAG_HS, hs_rx_index % 3U, ticks, 75U, rx_band, false, false);
    }
}
static void pilot_output(unsigned step) {
    if (pilot_tx) {
        carrier(1, v11_frequency(tx_band, 1, pilot_bit, false, step), true);
    } else {
        carrier(1, 2700, false);
    }
}
static void pilot_begin(bool recipient) {
    pilot_receiver = recipient;
    pilot_running = true;
    pilot_scored = false;
    pilot_start = q_start;
    pilot_duration = 2U * base_step;
    pilot_step = 0U;
    stats.pilot_step_ms = pilot_duration;
    stats.pilot_pair_ms = 2U * q_period;
    if (!recipient) {
        pilot_tx = pair_phase == 0U;
        if (pilot_tx) {
            pilot_bit = (protocol->round >> 1U) & 1U;
            ++stats.pilot_skipped;
        } else {
            ++stats.pilot_pairs;
        }
    } else {
        pilot_tx = pair_phase == 1U && saved_pilot >= 0;
        if (pilot_tx) {
            pilot_bit = 1U - (unsigned)saved_pilot;
        }
    }
    if (pilot_tx) {
        caps[1].active = false;
        pilot_output(0U);
    } else {
        carrier(1, 2700, false);
        cap_begin(1, TAG_PILOT, 0U, q_start, pilot_duration, rx_band, false, true);
    }
}
static void wave_output(unsigned part, unsigned step) {
    for (unsigned l = 0; l < 2U; ++l) {
        if (current_turbo && l == 1U) {
            continue;
        }
        if (leader) {
            if (part == 3U) {
                carrier(l, 2700, false);
                continue;
            }
            int s = part < 2U ? prepared.h[part] : prepared.data[l];
            bool on = true;
            if (part == 2U) {
                if (erase_this & (1U << l)) {
                    on = false;
                }
                if (notch_this & (1U << l) && step == notch_step) {
                    on = false;
                }
                if (flip_this & (1U << l)) {
                    s ^= 1;
                }
            }
            carrier(l, v11_frequency(tx_band, l, (unsigned)s, current_turbo, step), on);
        } else {
            if (part != 3U) {
                carrier(l, 2700, false);
                continue;
            }
            const int s = reply_out[l];
            carrier(l, v11_frequency(tx_band, l, s >= 0 ? (unsigned)s : 3U, current_turbo, step),
                    s >= 0);
        }
    }
}
static void receive_step(unsigned part, unsigned step, uint32_t start, bool known) {
    for (unsigned l = 0; l < 2U; ++l) {
        if (current_turbo && l == 1U) {
            continue;
        }
        cap_begin(l,
                  part == 0U   ? TAG_H0
                  : part == 1U ? TAG_H1
                  : part == 2U ? TAG_DATA
                               : TAG_ECHO,
                  step, start, q_step, rx_band, current_turbo, known);
    }
}
static void finish_quantum(void) {
    if (q_finished) {
        return;
    }
    q_finished = true;
    v11_finish(protocol, reply_in, current_turbo ? 1U : 3U);
    event_quantum(true, false);
    if ((reply_in[0] >= 0 && reply_in[0] < 3) ||
        (!current_turbo && reply_in[1] >= 0 && reply_in[1] < 3)) {
        last_header = ticks;
    }
    stats.rounds = protocol->round;
    stats.period_ms = q_period;
    stats.active = protocol->active;
    stats.fec = protocol->fec_bits;
    stats.quantum_kind = prepared.kind;
    for (unsigned l = 0; l < 2U; ++l) {
        stats.sent[l] = prepared.data[l];
        stats.received[l] = received[2][l];
        stats.returned[l] = reply_in[l];
    }
    if (protocol->tx_bytes > lease_bytes || (probe_only && protocol->round - lease_round >= 8U)) {
        lease_done = true;
        protocol->permitted = false;
    }
}
static void start_quantum(void) {
    ++event_round;
    const uint32_t previous_period = q_period;
    const bool was = current_turbo;
    const bool may = (lease_cfg & 4U) && protocol->active == 1U;
    if (!was || pair_phase == 1U) {
        current_turbo = may;
        pair_phase = 0U;
    } else {
        pair_phase = 1U;
    }
    if (was && !current_turbo) {
        ++stats.turbo_exit;
    }
    if (!was && current_turbo) {
        ++stats.turbo_enter;
    }
    q_period = current_turbo ? base_period / 2U : base_period;
    q_step = current_turbo ? base_step / 2U : base_step;
    /* Las sondas sin mensaje usan pilotos y no modifican bloques de recepcion. */
    v11_prepare(protocol, &prepared);
    erase_this = prepared.real ? erase_next : 0;
    flip_this = prepared.real ? flip_next : 0;
    notch_this = prepared.real ? notch_next : 0;
    if (prepared.real) {
        erase_next = 0;
        flip_next = 0;
        notch_next = 0;
    }
    q_start = ticks;
    if (last_q_start) {
        stats.interval_ms = q_start - last_q_start;
        if (stats.interval_ms != previous_period) {
            ++stats.deadline_miss;
        }
    }
    last_q_start = q_start;
    next_q_at = q_start + q_period;
    q_active = true;
    q_finished = false;
    ack_running = false;
    ack_ready = false;
    substep = 0U;
    for (unsigned p = 0; p < 4U; ++p) {
        for (unsigned l = 0; l < 2U; ++l) {
            received[p][l] = -1;
        }
    }
    reply_in[0] = -1;
    reply_in[1] = -1;
    wave_output(0U, 0U);
    clock_out(true);
    pulse_off =
        q_start + (current_turbo ? base_period / 40U + (pair_phase ? 4U : 0U) : base_period / 20U);
    if (current_turbo) {
        pilot_begin(false);
    }
    stats.turbo = current_turbo;
    stats.phase = 2U;
}
static void begin_receive_quantum(void) {
    ++event_round;
    q_start = ticks;
    rx_start = ticks;
    q_period = base_period;
    q_step = base_step;
    current_turbo = false;
    q_active = true;
    substep = 0U;
    ack_ready = false;
    q_finished = true;
    pilot_running = false;
    if (last_q_start) {
        stats.interval_ms = ticks - last_q_start;
    }
    last_q_start = ticks;
    for (unsigned p = 0; p < 4U; ++p) {
        for (unsigned l = 0; l < 2U; ++l) {
            received[p][l] = -1;
        }
    }
    reply_out[0] = 3;
    reply_out[1] = 3;
    carrier(0, 2700, false);
    carrier(1, 2700, false);
    receive_step(0U, 0U, ticks, false);
}
static void adjust_receive_quantum(uint32_t width) {
    const bool turbo = (lease_cfg & 4U) && width < (base_period / 20U) * 3U / 4U;
    current_turbo = turbo;
    q_period = turbo ? base_period / 2U : base_period;
    q_step = turbo ? base_step / 2U : base_step;
    pair_phase = turbo && width >= base_period / 40U + 2U ? 1U : 0U;
    for (unsigned l = 0; l < 2U; ++l) {
        if (turbo && l == 1U) {
            caps[l].active = false;
            continue;
        }
        caps[l].period = q_step;
        caps[l].guard = q_step >= 100 ? 25 : q_step >= 50 ? 12 : 5;
        caps[l].end = q_start + q_step - 4U;
        caps[l].turbo = turbo;
        caps[l].known = true;
    }
    if (turbo) {
        pilot_begin(true);
    }
    stats.turbo = turbo;
    stats.period_ms = q_period;
}
static void symbol_ready(unsigned lane, unsigned tag, const V11Decision *d) {
    if (tag == TAG_HS) {
        hs_results[lane] = d->symbol;
        hs_got |= 1U << lane;
        if (hs_got == 3U) {
            int v = hs_results[0] >= 0 ? hs_results[0] : hs_results[1];
            if (hs_results[0] >= 0 && hs_results[1] >= 0 && hs_results[0] != hs_results[1]) {
                v = -1;
            }
            hs_codes[hs_rx_index / 3U] = v >= 0 ? (unsigned)v : 255U;
            if (hs_rx_index / 3U + 1U == hs_count) {
                hs_packet_done();
            }
        }
        return;
    }
    if (tag == TAG_PILOT) {
        if (leader && pair_phase == 1U) {
            v11_pilot(protocol, 1U, pilot_bit, d->symbol);
            pilot_scored = true;
        } else if (!leader && pair_phase == 0U) {
            saved_pilot = d->symbol >= 0 && d->symbol < 2 ? d->symbol : -1;
        }
        return;
    }
    const unsigned part = tag - TAG_H0;
    received[part][lane] = d->symbol;
    if (part == 3U) {
        reply_in[lane] = d->symbol;
    }
}
static bool free_medium(uint32_t now) {
    const uint32_t mic = mic_history[now & 31U] - mic_history[(now - 20U) & 31U],
                   ir = ir_history[now & 31U] - ir_history[(now - 20U) & 31U];
    return !clock_in_active() && (((GPIOB->IDR & 2U) && ir <= 1U) || mic < threshold20);
}
static void schedule_handshake(uint32_t now) {
    if (hs_tx) {
        const uint32_t dt = now - hs_tx_at;
        if (dt >= 75U) {
            clock_out(false);
            ++hs_index;
            if (hs_index < hs_count * 3U) {
                hs_output(hs_index);
                clock_out(true);
                hs_tx_at = now;
            } else {
                hs_tx = false;
                off();
                if (hs_kind < 2U) {
                    mac_sent(&mac, now);
                } else if (hs_kind == 2U) {
                    sfd_wait = true;
                    hs_deadline = now + 1100U;
                } else {
                    enter_lease(false);
                }
            }
        } else if (dt >=
                   (hs_index == 0U ? (12U + hs_kind * 8U - (hs_kind == 3U ? 4U : 0U)) : 37U)) {
            clock_out(false);
        }
        return;
    }
    if (hs_next >= 0 && (int32_t)(now - hs_due) >= 0) {
        const unsigned k = (unsigned)hs_next;
        hs_next = -1;
        hs_begin(k);
        return;
    }
    if (sfd_wait && (int32_t)(now - hs_deadline) >= 0) {
        mac_lost(&mac, now);
        clear_exchange();
        return;
    }
    const unsigned a = mac_tick(&mac, now, v11_busy(protocol), free_medium(now));
    if (a == MA_RESET) {
        clear_exchange();
    } else if (a == MA_SYN) {
        hs_begin(0U);
    } else if (a == MA_ACK) {
        hs_begin(1U);
    }
}
void EXTI9_5_IRQHandler(void) {
    if (!(EXTI->PR & EXTI_PR_PR7)) {
        return;
    }
    EXTI->PR = EXTI_PR_PR7;
    if (!running || node > 1U) {
        return;
    }
    const bool high = clock_in_active();
    const uint32_t now = ticks;
    if (high) {
        ++stats.clocks;
        if (!lease) {
            if (sfd_wait) {
                hs_rising(3U);
                return;
            }
            const unsigned a = mac_rise(&mac, now);
            if (a == 1U) {
                hs_rising(0U);
            } else if (a == 2U) {
                hs_rising(1U);
            } else if (a == 3U) {
                hs_rising(2U);
            }
            return;
        }
        if (leader) {
            ack_start = now;
            ack_step = 0U;
            ack_running = true;
            receive_step(3U, 0U, now, true);
        } else {
            begin_receive_quantum();
        }
        return;
    }
    if (hs_rx) {
        const uint32_t w = now - hs_rise;
        if (w < 4U) {
            hs_rx = false;
            caps[0].active = false;
            caps[1].active = false;
            if (mac.state == M_RECV_SYN) {
                mac_released(&mac, now);
            }
            return;
        }
        /* El primer pulso marca el comienzo de paquete, no datos de aplicacion.
           Permite engancharse tras un arranque a mitad de SYN, sin desplazar los 3 escalones. */
        int marked = -1;
        const unsigned widths[4] = {12U, 20U, 28U, 32U};
        for (unsigned k = 0; k < 4U; ++k) {
            if (w + 2U >= widths[k] && w <= widths[k] + 2U) {
                marked = (int)k;
            }
        }
        if (marked >= 0) {
            const bool allowed = marked == 0   ? (mac.state != M_REQUEST)
                                 : marked == 1 ? (mac.state == M_WAIT_ACK)
                                 : marked == 2
                                     ? (mac.state == M_WAIT_DATA || mac.state == M_FOLLOWER)
                                     : sfd_wait;
            if (!allowed) {
                hs_rx = false;
                hs_aligned = false;
                caps[0].active = false;
                caps[1].active = false;
                return;
            }
            if (marked == 0) {
                mac.state = M_IDLE;
                (void)mac_rise(&mac, now);
                hs_next = -1;
                sfd_wait = false;
            }
            hs_rx_kind = (unsigned)marked;
            hs_rx_index = 0U;
            hs_count = marked == 0 ? 4U : 2U;
            hs_aligned = true;
            hs_got = 0U;
            rx_band = marked == 0 || marked == 2 ? 0U : 1U;
            for (unsigned l = 0; l < 2U; ++l) {
                cap_begin(l, TAG_HS, 0U, hs_rise, 75U, rx_band, false, true);
            }
            return;
        }
        if (!hs_aligned) {
            hs_rx = false;
            caps[0].active = false;
            caps[1].active = false;
            return;
        }
        for (unsigned l = 0; l < 2U; ++l) {
            caps[l].period = 75U;
            caps[l].guard = 12U;
            caps[l].end = hs_rise + 71U;
            caps[l].known = true;
        }
        return;
    }
    if (lease && !leader) {
        const uint32_t w = now - rx_start;
        if (w < 4U) {
            mac_released(&mac, now);
            clear_exchange();
            return;
        }
        if (w > base_period / 10U) {
            ++stats.clock_bad;
            return;
        }
        adjust_receive_quantum(w);
    }
}
void SysTick_Handler(void) {
    const uint32_t now = ++ticks;
    mic_history[now & 31U] = stats.mic_edges;
    ir_history[now & 31U] = stats.ir_edges;
    for (unsigned l = 0; l < 2U; ++l) {
        if (caps[l].active && caps[l].known && (int32_t)(now - caps[l].end) >= 0) {
            cap_end(l);
        }
    }
    if (!running || node > 1U) {
        return;
    }
    if (mac.state == M_RELEASE) {
        if ((int32_t)(now - mac.due) >= 0) {
            if (!release_level) {
                clock_out(true);
                release_level = true;
                mac.due = now + 2U;
            } else {
                clock_out(false);
                release_level = false;
                ++release_count;
                if (release_count == 3U) {
                    mac_released(&mac, now);
                    clear_exchange();
                } else {
                    mac.due = now + 10U;
                }
            }
        }
        return;
    }
    if (!lease) {
        const uint32_t state = __get_PRIMASK();
        __disable_irq();
        schedule_handshake(now);
        __set_PRIMASK(state);
        return;
    }
    if (pilot_running) {
        const uint32_t elapsed = now - pilot_start;
        if (pilot_step < 2U && elapsed >= (pilot_step + 1U) * pilot_duration) {
            ++pilot_step;
            if (pilot_tx) {
                pilot_output(pilot_step);
            } else {
                cap_begin(1, TAG_PILOT, pilot_step, pilot_start + pilot_step * pilot_duration,
                          pilot_duration, rx_band, false, true);
            }
        }
        if (elapsed >= 3U * pilot_duration) {
            pilot_running = false;
            if (pilot_tx) {
                carrier(1, 2700, false);
            }
        }
    }
    if (!leader) {
        if (ack_off && (int32_t)(now - ack_off) >= 0) {
            clock_out(false);
            ack_off = 0U;
        }
        if (q_active && substep < 12U && now - q_start >= (substep + 1U) * q_step) {
            ++substep;
            if (substep < 12U) {
                const unsigned part = substep / 3U, step = substep % 3U;
                if (part < 3U) {
                    receive_step(part, step, q_start + substep * q_step, true);
                } else {
                    if (part == 3U && step == 0U) {
                        const bool was_repairing = protocol->rx_repairing;
                        v11_receive(protocol, received[0], received[1], received[2], reply_out);
                        event_quantum(false, was_repairing);
                        if (reply_out[0] < 3 || reply_out[1] < 3) {
                            last_header = now;
                        }
                        ++stats.rounds;
                        stats.period_ms = q_period;
                        stats.active = protocol->active;
                        stats.fec = protocol->fec_bits;
                        stats.quantum_kind =
                            (received[0][0] >= 0 ? received[0][0] : received[0][1]) >= 2 ? 1U : 0U;
                        for (unsigned l = 0; l < 2U; ++l) {
                            stats.received[l] = received[2][l];
                            stats.returned[l] = reply_out[l];
                        }
                        wave_output(3U, 0U);
                        clock_out(true);
                        ack_off = now + q_period / 20U;
                    } else {
                        wave_output(part, step);
                    }
                }
            } else {
                carrier(0, 2700, false);
                if (!current_turbo) {
                    carrier(1, 2700, false);
                }
                q_active = false;
            }
        }
        if (now - last_header > 5000U && !q_active) {
            mac_lost(&mac, now);
            clear_exchange();
        }
        return;
    }
    if (pulse_off && (int32_t)(now - pulse_off) >= 0) {
        clock_out(false);
        pulse_off = 0U;
    }
    if (now - last_header > 5000U) {
        mac_lost(&mac, now);
        clear_exchange();
        return;
    }
    if (ack_running && ack_step < 2U && now - ack_start >= (ack_step + 1U) * q_step) {
        ++ack_step;
        receive_step(3U, ack_step, ack_start + ack_step * q_step, true);
    }
    if (ack_running && now - ack_start >= 3U * q_step) {
        ack_running = false;
        ack_ready = true;
        finish_quantum();
    }
    if (q_active && substep < 12U && now - q_start >= (substep + 1U) * q_step) {
        ++substep;
        if (substep < 12U) {
            wave_output(substep / 3U, substep % 3U);
        } else {
            carrier(0, 2700, false);
            if (!current_turbo) {
                carrier(1, 2700, false);
            }
        }
    }
    if (q_active && !q_finished && now - q_start >= q_period - 10U) {
        finish_quantum();
    }
    if ((int32_t)(now - next_q_at) >= 0) {
        if (q_active && !q_finished) {
            finish_quantum();
        }
        if (lease_done && (!current_turbo || pair_phase == 1U)) {
            off();
            release_count = 0U;
            release_level = false;
            mac_frame_done(&mac, now);
            return;
        }
        start_quantum();
    }
}
