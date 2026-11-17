#include "codec.h"
static const uint16_t frequencies[2][2][2][3]={
 {{{80,100,120},{80,120,160}},{{2700,2800,2900},{2700,2900,3000}}},
 {{{400,350,300},{400,300,200}},{{4100,4000,3900},{4100,3900,3700}}}
};
uint32_t v10_frequency(unsigned node,unsigned lane,unsigned bit,unsigned step){return frequencies[node&1U][lane&1U][bit&1U][step%3U];}
uint8_t v10_crc(unsigned kind,const uint8_t *bytes,unsigned length){
    static const uint8_t poly[4]={0x07,0x2F,0x1D,0x8C};if(kind>3U){return 0U;}
    uint8_t crc=kind==1U||kind==2U?255U:0U;
    for(unsigned n=0;n<length;++n){crc^=bytes[n];for(unsigned b=0;b<8U;++b){
        crc=kind==3U?(uint8_t)((crc>>1U)^((crc&1U)?poly[kind]:0U)):(uint8_t)((crc<<1U)^((crc&128U)?poly[kind]:0U));
    }}return kind==1U||kind==2U?(uint8_t)(crc^255U):crc;
}
uint8_t v10_word(uint8_t data){
    const unsigned positions[6]={0,3,4,5,2,1};uint8_t word=0U;
    for(unsigned n=0;n<6U;++n){word|=(uint8_t)(((data>>(5U-n))&1U)<<positions[n]);}
    word|=(uint8_t)((((word>>0U)^(word>>3U)^(word>>4U))&1U)<<6U);
    word|=(uint8_t)((((word>>1U)^(word>>2U)^(word>>5U))&1U)<<7U);return word;
}
bool v10_recover(uint8_t values,uint8_t known,uint8_t *data,uint8_t *recovered){
    static const uint8_t groups[2][4]={{0,3,4,6},{1,2,5,7}};
    const unsigned positions[6]={0,3,4,5,2,1};uint8_t fixed=0U;
    for(unsigned group=0;group<2U;++group){
        unsigned missing=0U,where=0U,value=0U;
        for(unsigned n=0;n<4U;++n){const unsigned p=groups[group][n];if(known&(1U<<p)){value^=(values>>p)&1U;}else{++missing;where=p;}}
        if(missing>1U){return false;}
        if(!missing && value){return false;}
        if(missing){values=(uint8_t)((values&~(1U<<where))|(value<<where));known|=(uint8_t)(1U<<where);fixed|=(uint8_t)(1U<<where);}
    }
    *data=0U;for(unsigned n=0;n<6U;++n){*data=(uint8_t)((*data<<1U)|((values>>positions[n])&1U));}
    *recovered=fixed&0x3FU;return true;
}
uint32_t v10_frame(unsigned kind,uint8_t control,uint8_t data){
    const uint8_t bytes[2]={control,data};return ((uint32_t)(control&15U)<<20U)|((uint32_t)data<<12U)|((uint32_t)v10_crc(kind,bytes,2U)<<4U)|10U;
}
bool v10_frame_valid(unsigned kind,uint32_t frame){
    const uint8_t c=(uint8_t)(frame>>20U),d=(uint8_t)(frame>>12U);return (frame&15U)==10U&&frame==v10_frame(kind,c,d);
}
int v10_classify(unsigned remote,unsigned lane,const uint32_t hz[3],const uint32_t count[3],const uint32_t bad[3]){
    bool up=true,down=true;
    for(unsigned n=0;n<3U;++n){if(count[n]<3U || bad[n]>2U+count[n]/10U){return -1;}}
    for(unsigned n=0;n<2U;++n){
        if(hz[n+1U]*1000U<=hz[n]*1015U){up=false;}
        if(hz[n+1U]*1000U>=hz[n]*985U){down=false;}
    }if((remote==0U&&!up)||(remote==1U&&!down)){return -1;}
    int found=-1;
    for(unsigned bit=0;bit<2U;++bit){bool ok=true;
        for(unsigned n=0;n<3U;++n){const uint32_t expected=v10_frequency(remote,lane,bit,n);const uint32_t error=hz[n]>expected?hz[n]-expected:expected-hz[n];if(error*10000U>expected*120U){ok=false;}}
        if(ok){if(found>=0){return -1;}found=(int)bit;}
    }return found;
}
bool v10_decode(unsigned band,unsigned lane,const V10Sweep *s,V10Decision *d){
    d->bit=-1;d->slope_hz_s=0;d->valid_steps=0U;d->reconstructed=0U;
    if(band>1U||lane>1U){return false;}
    unsigned quality=0U;
    for(unsigned n=0;n<3U;++n){
        /* Una polaridad por ciclo en PB1/PA1. +/-35% y dos bordes de ventana.
           La densidad usa flancos crudos, no solo los periodos filtrados. */
        const uint32_t expected=(s->hz[n]*s->window_us[n]+500000U)/1000000U;
        const uint32_t allowance=(expected*35U+99U)/100U+2U;
        const uint32_t error=s->edges[n]>expected?s->edges[n]-expected:expected-s->edges[n];
        if(s->window_us[n] && s->hz[n] && s->periods[n]>=3U && expected>=3U && error<=allowance && s->bad[n]<=2U+s->edges[n]/10U){quality|=1U<<n;}
    }
    /* No convertir una contradiccion de direccion en un borrado conveniente. */
    for(unsigned i=0;i<3U;++i){for(unsigned j=i+1U;j<3U;++j){
        if((quality&(1U<<i))&&(quality&(1U<<j))){
            if(s->time_us[j]<=s->time_us[i]){return false;}
            if((band==0U && s->hz[j]*1000U<=s->hz[i]*1015U)||(band==1U && s->hz[j]*1000U>=s->hz[i]*985U)){return false;}
        }
    }}
    unsigned usable=0U;
    for(unsigned n=0;n<3U;++n){if(quality&(1U<<n)){
        for(unsigned bit=0;bit<2U;++bit){const uint32_t f=v10_frequency(band,lane,bit,n);const uint32_t e=s->hz[n]>f?s->hz[n]-f:f-s->hz[n];if(e*10000U<=f*120U){usable|=1U<<n;}}
    }}
    unsigned count=0U,first=3U,last=0U;
    for(unsigned n=0;n<3U;++n){if(usable&(1U<<n)){++count;if(first==3U){first=n;}last=n;}}
    d->valid_steps=(uint8_t)usable;if(count<2U){return false;}
    const uint32_t delta=s->hz[last]>s->hz[first]?s->hz[last]-s->hz[first]:s->hz[first]-s->hz[last];
    const uint32_t dt=s->time_us[last]-s->time_us[first];
    int found=-1;
    for(unsigned bit=0;bit<2U;++bit){bool match=true;
        for(unsigned n=0;n<3U;++n){if(usable&(1U<<n)){const uint32_t f=v10_frequency(band,lane,bit,n);const uint32_t e=s->hz[n]>f?s->hz[n]-f:f-s->hz[n];if(e*10000U>f*120U){match=false;}}}
        const uint32_t f0=v10_frequency(band,lane,bit,first),f1=v10_frequency(band,lane,bit,last);
        const uint32_t wanted=f0>f1?f0-f1:f1-f0,error=delta>wanted?delta-wanted:wanted-delta;
        if(error*100U>wanted*45U){match=false;}
        if(match){if(found>=0){return false;}found=(int)bit;}
    }
    if(found<0){return false;}
    d->bit=found;d->reconstructed=count==2U;
    d->slope_hz_s=(int32_t)((delta*1000000U)/dt)*(band==0U?1:-1);
    return true;
}
