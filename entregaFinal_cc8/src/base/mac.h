#ifndef PHY10_MAC_H
#define PHY10_MAC_H
#include <stdint.h>
#include <stdbool.h>
enum {M_IDLE,M_BACKOFF,M_REQUEST,M_WAIT_ACK,M_RECV_SYN,M_SEND_ACK,M_WAIT_DATA,M_LEADER,M_FOLLOWER,M_RELEASE};
enum {MA_NONE,MA_SYN,MA_ACK,MA_RESET};
enum {ME_READY,ME_SYN,ME_RECEIVE_SYN,ME_FIRST_WIN,ME_TIE_WIN,ME_TIE_YIELD,ME_ACK,ME_ESTABLISHED,ME_TIMEOUT,ME_REJECT,ME_RELEASE,ME_BUSY};
typedef struct {
    unsigned identity,state,event,event_id;bool ready,collision_seen,probe;
    uint32_t requested_at,due,deadline,random;
    uint32_t requests,accepted,timeouts,rejected,first_wins,tie_wins,yields,busy,frames;
} V10Mac;
void mac_init(V10Mac *m,unsigned identity);
void mac_start(V10Mac *m,uint32_t now);
void mac_stop(V10Mac *m);
unsigned mac_tick(V10Mac *m,uint32_t now,bool pending,bool free_medium);
/* Retorno: 1 recibir SYN bajo, 2 recibir SYN-ACK alto, 3 aceptar datos. */
unsigned mac_rise(V10Mac *m,uint32_t now);
void mac_syn_result(V10Mac *m,uint32_t now,bool valid);
void mac_ack_result(V10Mac *m,uint32_t now,bool valid);
void mac_sent(V10Mac *m,uint32_t now);
void mac_frame_done(V10Mac *m,uint32_t now);
void mac_released(V10Mac *m,uint32_t now);
void mac_lost(V10Mac *m,uint32_t now);
#endif
