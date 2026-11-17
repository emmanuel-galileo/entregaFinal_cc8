#include "mac.h"
static void event(V10Mac *m,unsigned e){m->event=e;++m->event_id;}
static void backoff(V10Mac *m,uint32_t now){m->state=M_BACKOFF;m->random=m->random*1664525U+1013904223U;m->due=now+40U+(m->random>>24U)%101U;}
void mac_init(V10Mac *m,unsigned id){uint8_t *p=(uint8_t *)m;for(unsigned i=0;i<sizeof(*m);++i){p[i]=0;}m->identity=id&1U;m->random=0x73851U+id*1777U;}
void mac_start(V10Mac *m,uint32_t now){m->ready=true;m->state=M_IDLE;m->due=now+25U;m->collision_seen=false;event(m,ME_READY);}
void mac_stop(V10Mac *m){m->ready=false;m->state=M_IDLE;m->probe=false;}
unsigned mac_tick(V10Mac *m,uint32_t now,bool pending,bool free_medium){
    if(!m->ready){return MA_NONE;}
    if((m->state==M_WAIT_ACK||m->state==M_RECV_SYN||m->state==M_WAIT_DATA)&&(int32_t)(now-m->deadline)>=0){++m->timeouts;event(m,ME_TIMEOUT);backoff(m,now);return MA_RESET;}
    if(m->state==M_SEND_ACK && (int32_t)(now-m->due)>=0){event(m,ME_ACK);return MA_ACK;}
    if((m->state==M_IDLE||m->state==M_BACKOFF)&&(pending||m->probe)&&(int32_t)(now-m->due)>=0){
        if(!free_medium){++m->busy;event(m,ME_BUSY);backoff(m,now);return MA_NONE;}
        m->state=M_REQUEST;m->requested_at=now;m->collision_seen=false;++m->requests;event(m,ME_SYN);return MA_SYN;
    }return MA_NONE;
}
unsigned mac_rise(V10Mac *m,uint32_t now){
    if(!m->ready){return 0U;}
    if(m->state==M_IDLE||m->state==M_BACKOFF){m->state=M_RECV_SYN;m->deadline=now+1100U;event(m,ME_RECEIVE_SYN);return 1U;}
    if(m->state==M_REQUEST){
        if(!m->collision_seen){m->collision_seen=true;
            if((uint32_t)(now-m->requested_at)<=2U){
                if(m->identity==1U){++m->yields;m->state=M_RECV_SYN;m->deadline=now+1100U;event(m,ME_TIE_YIELD);return 1U;}
                ++m->tie_wins;event(m,ME_TIE_WIN);
            }else{++m->first_wins;event(m,ME_FIRST_WIN);}
        }return 0U;
    }
    if(m->state==M_RECV_SYN){return 1U;}
    if(m->state==M_WAIT_ACK){return 2U;}
    if(m->state==M_WAIT_DATA){m->state=M_FOLLOWER;++m->accepted;m->probe=false;event(m,ME_ESTABLISHED);return 3U;}
    return m->state==M_FOLLOWER?3U:0U;
}
void mac_syn_result(V10Mac *m,uint32_t now,bool valid){
    if(m->state!=M_RECV_SYN){return;}
    if(valid){m->state=M_SEND_ACK;m->due=now+20U;}
    else{++m->rejected;event(m,ME_REJECT);backoff(m,now);}
}
void mac_ack_result(V10Mac *m,uint32_t now,bool valid){
    if(m->state!=M_WAIT_ACK){return;}
    if(valid){m->state=M_LEADER;++m->accepted;m->probe=false;event(m,ME_ESTABLISHED);}
    else{++m->rejected;event(m,ME_REJECT);backoff(m,now);}
}
void mac_sent(V10Mac *m,uint32_t now){
    if(m->state==M_REQUEST){m->state=M_WAIT_ACK;m->deadline=now+1100U;}
    else if(m->state==M_SEND_ACK){m->state=M_WAIT_DATA;m->deadline=now+1100U;}
}
void mac_frame_done(V10Mac *m,uint32_t now){if(m->state==M_LEADER){m->state=M_RELEASE;m->due=now+8U;++m->frames;event(m,ME_RELEASE);}}
void mac_released(V10Mac *m,uint32_t now){
    const bool was_sender=m->state==M_RELEASE;m->state=M_IDLE;m->due=now+(was_sender?120U:25U);m->collision_seen=false;event(m,ME_RELEASE);
}
void mac_lost(V10Mac *m,uint32_t now){++m->timeouts;event(m,ME_TIMEOUT);backoff(m,now);}
