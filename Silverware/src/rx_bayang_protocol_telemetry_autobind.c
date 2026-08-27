/*
The MIT License (MIT)

Copyright (c) 2016 silverx

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
*/


#include "binary.h"
#include "drv_spi.h"
#include "project.h"
#include "xn297.h"
#include "drv_time.h"
#include <stdio.h>
#include "defines.h"
#include "rx_bayang.h"
#include "util.h"


#define RX_MODE_NORMAL RXMODE_NORMAL
#define RX_MODE_BIND RXMODE_BIND
// radio settings

// packet period in uS
#define PACKET_PERIOD 3000
#define PACKET_PERIOD_TELEMETRY 5000

// was 250 ( uS )
#define PACKET_OFFSET 0

#ifdef USE_STOCK_TX
#undef PACKET_PERIOD
#define PACKET_PERIOD 2000
#undef PACKET_OFFSET
#define PACKET_OFFSET 0
#endif

// how many times to hop ahead if no reception
#define HOPPING_NUMBER 4


#ifdef RX_BAYANG_PROTOCOL_TELEMETRY_AUTOBIND

extern float rx[4];
extern char aux[AUXNUMBER];
extern char lastaux[AUXNUMBER];
extern char auxchange[AUXNUMBER];
extern float aux_analog[AUXNUMBER];
extern float lastaux_analog[AUXNUMBER];
extern char aux_analogchange[AUXNUMBER];


char lasttrim[4];

char rfchannel[4];
char rxaddress[5];
int telemetry_enabled = 0;
int rx_bind_enable = 0;
int rx_bind_load = 0;

int rxmode = 0;
int rf_chan = 0;
int rx_ready = 0;
int bind_safety = 0;

unsigned long autobindtime = 0;
int autobind_inhibit = 0;
int packet_period = PACKET_PERIOD;

void writeregs(uint8_t data[], uint8_t size)
{
    spi_cson();
    for (uint8_t i = 0; i < size; i++)
      {
          spi_sendbyte(data[i]);
      }
    spi_csoff();
}



void rx_init()
{


// always on (CH_ON) channel set 1
    aux[AUXNUMBER - 2] = 1;
// always off (CH_OFF) channel set 0
    aux[AUXNUMBER - 1] = 0;
#ifdef AUX1_START_ON
    aux[CH_AUX1] = 1;
#endif


#ifdef RADIO_XN297L

#ifndef TX_POWER
#define TX_POWER 7
#endif
	
// Gauss filter amplitude - lowest
static uint8_t demodcal[2] = { 0x39 , B00000001 };
writeregs( demodcal , sizeof(demodcal) );

// powerup defaults
//static uint8_t rfcal2[7] = { 0x3a , 0x45 , 0x21 , 0xef , 0xac , 0x3a , 0x50};
//writeregs( rfcal2 , sizeof(rfcal2) );

static uint8_t rfcal2[7] = { 0x3a , 0x45 , 0x21 , 0xef , 0x2c , 0x5a , 0x50};
writeregs( rfcal2 , sizeof(rfcal2) );

static uint8_t regs_1f[6] = { 0x3f , 0x0a, 0x6d , 0x67 , 0x9c , 0x46 };
writeregs( regs_1f , sizeof(regs_1f) );


static uint8_t regs_1e[4] = { 0x3e , 0xf6 , 0x37 , 0x5d };
writeregs( regs_1e , sizeof(regs_1e) );

#define XN_TO_RX B10001111
#define XN_TO_TX B10000010
#define XN_POWER B00000001|((TX_POWER&3)<<1)


#endif



#ifdef RADIO_XN297
    static uint8_t bbcal[6] = { 0x3f, 0x4c, 0x84, 0x6F, 0x9c, 0x20 };
    writeregs(bbcal, sizeof(bbcal));
// new values
    static uint8_t rfcal[8] =
        { 0x3e, 0xc9, 0x9a, 0xA0, 0x61, 0xbb, 0xab, 0x9c };
    writeregs(rfcal, sizeof(rfcal));

// 0xa7 0x03
    static uint8_t demodcal[6] =
        { 0x39, 0x0b, 0xdf, 0xc4, B00100111, B00000000 };
    writeregs(demodcal, sizeof(demodcal));


#ifndef TX_POWER
#define TX_POWER 3
#endif


#define XN_TO_RX B00001111
#define XN_TO_TX B00000010
#define XN_POWER (B00000001|((TX_POWER&3)<<1))
#endif

    delay(100);

// write rx address " 0 0 0 0 0 "
        
   static uint8_t rxaddr[6] = { 0x2a , 0 , 0 , 0 , 0 , 0  };
   writeregs( rxaddr , sizeof(rxaddr) );
    
    xn_writereg(EN_AA, 0);      // aa disabled
    xn_writereg(EN_RXADDR, 1);  // pipe 0 only
    xn_writereg(RF_SETUP, XN_POWER);    // power / data rate / lna
    xn_writereg(RX_PW_P0, 15);  // payload size
    xn_writereg(SETUP_RETR, 0); // no retransmissions ( redundant?)
    xn_writereg(SETUP_AW, 3);   // address size (5 bytes)
    xn_command(FLUSH_RX);
    xn_writereg(RF_CH, 0);      // bind on channel 0


#ifdef RADIO_XN297L
    xn_writereg(0x1d, B00111000);   // 64 bit payload , software ce
    spi_cson();
    spi_sendbyte(0xFD);         // internal CE high command
    spi_sendbyte(0);            // required for above
    spi_csoff();
#endif

#ifdef RADIO_XN297
    xn_writereg(0x1d, B00011000);   // 64 bit payload , software ce
#endif

    xn_writereg(0, XN_TO_RX);   // power up, crc enabled, rx mode

#ifdef RADIO_CHECK
    int rxcheck = xn_readreg(0x0f); // rx address pipe 5   
    // should be 0xc6
    extern void failloop(int);
    if (rxcheck != 0xc6)
        failloop(3);
#endif
    
    if ( rx_bind_load )
    {
          uint8_t rxaddr_regs[6] = { 0x2a ,  };                      
          for ( int i = 1 ; i < 6; i++)
          {
            rxaddr_regs[i] = rxaddress[i-1];
          }
          // write new rx address
          writeregs( rxaddr_regs , sizeof(rxaddr_regs) );
          rxaddr_regs[0] = 0x30; // tx register ( write ) number
          
          // write new tx address
          writeregs( rxaddr_regs , sizeof(rxaddr_regs) );

          xn_writereg(0x25, rfchannel[rf_chan]);    // Set channel frequency 
          rxmode = RX_MODE_NORMAL;
 
          if ( telemetry_enabled ) packet_period = PACKET_PERIOD_TELEMETRY;
    }
    else
    {
        autobind_inhibit = 1;
    }
    
}



//#define RXDEBUG

#ifdef RXDEBUG
unsigned long packettime;
int channelcount[4];
int failcount;
int skipstats[12];
int afterskip[12];

#warning "RX debug enabled"
#endif

int packetrx;
int packetpersecond;

#ifdef RX_BAYANG_EXTENDED_TELEMETRY
uint8_t telemetry_packets_lost_window;
uint8_t telemetry_link_quality;
uint8_t telemetry_current_gap_100us;
uint8_t telemetry_failsafe_count;
uint16_t telemetry_max_gap_100us;
uint32_t telemetry_rx_total;
uint32_t telemetry_lost_total;
uint32_t telemetry_tx_total;
static uint16_t telemetry_max_gap_window_100us;
static uint32_t telemetry_last_valid_rx_time;
static int telemetry_previous_failsafe = 1;
#endif


void send_telemetry(void);
void nextchannel(void);

int loopcounter = 0;
unsigned int send_time;
int telemetry_send = 0;
int oldchan = 0;

#define TELEMETRY_TIMEOUT 10000

void beacon_sequence()
{
    static int beacon_seq_state = 0;

    switch (beacon_seq_state)
      {
          case 0:
              // send data
              telemetry_send = 1;
              send_telemetry();
              beacon_seq_state++;
              break;

          case 1:
              // wait for data to finish transmitting
              if ((xn_readreg(0x17) & B00010000))
                {
                    xn_writereg(0, XN_TO_RX);
                    beacon_seq_state = 0;
                    telemetry_send = 0;
                    nextchannel();
                }
              else
                {   // if it takes too long we get rid of it
                    if (gettime() - send_time > TELEMETRY_TIMEOUT)
                      {
                          xn_command(FLUSH_TX);
                          xn_writereg(0, XN_TO_RX);
                          beacon_seq_state = 0;
                          telemetry_send = 0;
                      }
                }
              break;

          default:
              beacon_seq_state = 0;
              break;



      }

}



extern int lowbatt;
extern float vbattfilt;
extern float vbatt_comp;

#ifdef RX_BAYANG_EXTENDED_TELEMETRY

#define EXTENDED_TELEMETRY_HEADER 0x86
#define EXTENDED_TELEMETRY_CONTROL 0
#define EXTENDED_TELEMETRY_FLIGHT 1
#define EXTENDED_TELEMETRY_POWER 2
#define EXTENDED_TELEMETRY_SYSTEM 3

extern float GEstG[3];
extern float gyro[3];
extern float telemetry_accel_g[3];
extern float setpoint[3];
extern float rx[4];
extern float throttle;
extern float telemetry_motor_output[4];
extern float telemetry_relative_yaw_deg;
extern int armed_state;
extern int onground;
extern int failsafe;
extern int idle_state;
extern uint8_t telemetry_imu_type;
extern int16_t telemetry_imu_temperature_raw;
extern uint32_t telemetry_loop_time_sum_us;
extern uint32_t telemetry_loop_work_sum_us;
extern uint16_t telemetry_loop_time_max_us;
extern uint16_t telemetry_loop_samples;
extern uint16_t telemetry_loop_overruns;
extern float atan2approx(float y, float x);

static uint16_t telemetry_flight_seconds;
static uint32_t telemetry_flight_remainder_us;
static uint32_t telemetry_flight_last_us;
static int telemetry_was_flying;

static void telemetry_write_bits(int *data, uint8_t *bit_offset, uint32_t value, uint8_t bit_count)
{
    for (int bit = bit_count - 1; bit >= 0; bit--)
      {
        uint8_t byte_index = 2 + (*bit_offset >> 3);
        uint8_t byte_bit = 7 - (*bit_offset & 7);
        if (value & (1UL << bit))
            data[byte_index] |= 1 << byte_bit;
        (*bit_offset)++;
      }
}

static uint32_t telemetry_signed(float value, float resolution, uint8_t bits)
{
    float scaled = value / resolution;
    int32_t quantized = (int32_t)(scaled + (scaled >= 0.0f ? 0.5f : -0.5f));
    int32_t minimum = -(1L << (bits - 1));
    int32_t maximum = (1L << (bits - 1)) - 1;
    if (quantized < minimum)
        quantized = minimum;
    if (quantized > maximum)
        quantized = maximum;
    return (uint32_t)quantized & ((1UL << bits) - 1UL);
}

static uint32_t telemetry_unit_float(float value, uint8_t bits)
{
    if (value <= 0.0f)
        return 0;
    if (value >= 1.0f)
        return (1UL << bits) - 1UL;
    return (uint32_t)(value * (float)((1UL << bits) - 1UL) + 0.5f);
}

static uint16_t telemetry_u16(float value)
{
    if (value <= 0.0f)
        return 0;
    if (value >= 65535.0f)
        return 65535;
    return (uint16_t)(value + 0.5f);
}

static void telemetry_update_flight_time(void)
{
    uint32_t now = (uint32_t)gettime();
    int flying = armed_state && !onground;

    if (flying && !telemetry_was_flying)
      {
        telemetry_flight_seconds = 0;
        telemetry_flight_remainder_us = 0;
        telemetry_flight_last_us = now;
      }
    else if (flying)
      {
        telemetry_flight_remainder_us += (uint32_t)(now - telemetry_flight_last_us);
        telemetry_flight_last_us = now;
        while (telemetry_flight_remainder_us >= 1000000U && telemetry_flight_seconds < 65535U)
          {
            telemetry_flight_remainder_us -= 1000000U;
            telemetry_flight_seconds++;
          }
      }
    else
      {
        telemetry_flight_last_us = now;
      }

    telemetry_was_flying = flying;
}

static void telemetry_write_control(int *txdata)
{
    uint8_t offset = 0;
    for (int axis = 0; axis < 3; axis++)
        telemetry_write_bits(txdata, &offset, telemetry_signed(gyro[axis] * RADTODEG, 4.0f, 10), 10);
    for (int axis = 0; axis < 3; axis++)
        telemetry_write_bits(txdata, &offset, telemetry_signed(setpoint[axis] * RADTODEG, 4.0f, 10), 10);
    telemetry_write_bits(txdata, &offset, telemetry_unit_float(rx[3], 6), 6);
    telemetry_write_bits(txdata, &offset, telemetry_unit_float(throttle, 6), 6);
    for (int motor = 0; motor < 4; motor++)
        telemetry_write_bits(txdata, &offset, telemetry_unit_float(telemetry_motor_output[motor], 6), 6);
}

static void telemetry_write_flight(int *txdata)
{
    uint8_t offset = 0;
    uint8_t flags = 0;
    float roll = atan2approx(GEstG[0], GEstG[2]);
    float pitch = atan2approx(GEstG[1], GEstG[2]);
    telemetry_write_bits(txdata, &offset, telemetry_signed(roll, 0.1f, 12), 12);
    telemetry_write_bits(txdata, &offset, telemetry_signed(pitch, 0.1f, 12), 12);
    telemetry_write_bits(txdata, &offset, telemetry_signed(telemetry_relative_yaw_deg, 0.1f, 12), 12);
    for (int axis = 0; axis < 3; axis++)
        telemetry_write_bits(txdata, &offset, telemetry_signed(telemetry_accel_g[axis], 1.0f / 256.0f, 12), 12);
    telemetry_write_bits(txdata, &offset, telemetry_flight_seconds, 16);
    if (onground)
        flags |= 1 << 0;
    if (idle_state)
        flags |= 1 << 1;
    if (lowbatt)
        flags |= 1 << 2;
#ifdef LEVELMODE
    if (aux[LEVELMODE])
        flags |= 1 << 3;
#endif
#ifdef RACEMODE
    if (aux[RACEMODE])
        flags |= 1 << 4;
#endif
#ifdef HORIZON
    if (aux[HORIZON])
        flags |= 1 << 5;
#endif
#ifdef PIDPROFILE
    if (aux[PIDPROFILE])
        flags |= 1 << 6;
#endif
    telemetry_write_bits(txdata, &offset, flags, 8);
}

static void telemetry_write_power(int *txdata)
{
    uint8_t offset = 0;
    uint8_t battery_flags = lowbatt ? 1 : 0;
    uint8_t rx_rate = packetpersecond > 255 ? 255 : (uint8_t)packetpersecond;
    telemetry_write_bits(txdata, &offset, telemetry_u16(vbattfilt * 1000.0f), 16);
    telemetry_write_bits(txdata, &offset, telemetry_u16(vbatt_comp * 1000.0f), 16);
    telemetry_write_bits(txdata, &offset, rx_rate, 8);
    telemetry_write_bits(txdata, &offset, telemetry_packets_lost_window, 8);
    telemetry_write_bits(txdata, &offset, telemetry_link_quality, 8);
    telemetry_write_bits(txdata, &offset, battery_flags, 8);
    telemetry_write_bits(txdata, &offset, telemetry_max_gap_100us, 16);
    telemetry_write_bits(txdata, &offset, telemetry_current_gap_100us, 8);
    telemetry_write_bits(txdata, &offset, telemetry_failsafe_count, 8);
}

static void telemetry_write_system(int *txdata)
{
    static int counters_subpage;
    uint8_t offset = 0;
    telemetry_write_bits(txdata, &offset, counters_subpage, 1);
    if (!counters_subpage)
      {
        uint16_t samples = telemetry_loop_samples;
        uint32_t average = samples ? telemetry_loop_time_sum_us / samples : 0;
        uint32_t cpu_load = samples ? telemetry_loop_work_sum_us * 100U / ((uint32_t)samples * LOOPTIME) : 0;
        if (average > 65535U)
            average = 65535U;
        if (cpu_load > 100U)
            cpu_load = 100U;
        telemetry_write_bits(txdata, &offset, average, 16);
        telemetry_write_bits(txdata, &offset, telemetry_loop_time_max_us, 16);
        telemetry_write_bits(txdata, &offset, telemetry_loop_overruns, 16);
        telemetry_write_bits(txdata, &offset, (uint16_t)telemetry_imu_temperature_raw, 16);
        telemetry_write_bits(txdata, &offset, telemetry_imu_type, 8);
        telemetry_write_bits(txdata, &offset, cpu_load, 8);
        telemetry_write_bits(txdata, &offset, telemetry_tx_total & 0x7fffU, 15);
        telemetry_loop_time_sum_us = 0;
        telemetry_loop_work_sum_us = 0;
        telemetry_loop_time_max_us = 0;
        telemetry_loop_samples = 0;
      }
    else
      {
        telemetry_write_bits(txdata, &offset, telemetry_rx_total, 32);
        telemetry_write_bits(txdata, &offset, telemetry_lost_total, 32);
        telemetry_write_bits(txdata, &offset, telemetry_tx_total & 0x7fffffffU, 31);
      }
    counters_subpage = !counters_subpage;
}

static void telemetry_write_extended_packet(int *txdata)
{
    static const uint8_t page_cycle[8] = {
        EXTENDED_TELEMETRY_CONTROL, EXTENDED_TELEMETRY_FLIGHT,
        EXTENDED_TELEMETRY_CONTROL, EXTENDED_TELEMETRY_POWER,
        EXTENDED_TELEMETRY_CONTROL, EXTENDED_TELEMETRY_FLIGHT,
        EXTENDED_TELEMETRY_CONTROL, EXTENDED_TELEMETRY_SYSTEM,
    };
    static uint8_t cycle_index;
    static uint8_t sequence;
    uint8_t page = page_cycle[cycle_index];
    cycle_index = (cycle_index + 1) & 7;

    telemetry_update_flight_time();
    txdata[0] = EXTENDED_TELEMETRY_HEADER;
    for (int index = 1; index < 14; index++)
        txdata[index] = 0;
    txdata[1] = (page << 6) | (armed_state ? 1 << 5 : 0) | (failsafe ? 1 << 4 : 0) | (sequence & 0x0f);
    sequence = (sequence + 1) & 0x0f;

    if (page == EXTENDED_TELEMETRY_CONTROL)
        telemetry_write_control(txdata);
    else if (page == EXTENDED_TELEMETRY_FLIGHT)
        telemetry_write_flight(txdata);
    else if (page == EXTENDED_TELEMETRY_POWER)
        telemetry_write_power(txdata);
    else
        telemetry_write_system(txdata);
    telemetry_tx_total++;
}

#endif

void send_telemetry()
{

    int txdata[15];
    for (int i = 0; i < 15; i++)
        txdata[i] = i;
    txdata[0] = 133;
    txdata[1] = lowbatt;

    int vbatt = vbattfilt * 100;
// battery volt filtered    
    txdata[3] = (vbatt >> 8) & 0xff;
    txdata[4] = vbatt & 0xff;

    vbatt = vbatt_comp * 100;
// battery volt compensated 
    txdata[5] = (vbatt >> 8) & 0xff;
    txdata[6] = vbatt & 0xff;

    int temp = packetpersecond / 2;
    if (temp > 255)
        temp = 255;

    txdata[7] = temp;           // rx strenght

    if (lowbatt)
        txdata[3] |= (1 << 3);

#ifdef RX_BAYANG_EXTENDED_TELEMETRY
    telemetry_write_extended_packet(txdata);
#endif

    int sum = 0;
    for (int i = 0; i < 14; i++)
      {
          sum += txdata[i];
      }

    txdata[14] = sum;

    xn_command(FLUSH_TX);

    xn_writereg(0, XN_TO_TX);

    xn_writepayload(txdata, 15);

    send_time = gettime();

    return;
}



static char checkpacket()
{
    int status = xn_readreg(7);

    if (status & (1 << MASK_RX_DR))
      {                         // rx clear bit
          // this is not working well
          // xn_writereg( STATUS , (1<<MASK_RX_DR) );
          //RX packet received
          //return 1;
      }
    if ((status & B00001110) != B00001110)
      {
          // rx fifo not empty        
          return 2;
      }

    return 0;
}


int rxdata[15];


float packettodata(int *data)
{
    return (((data[0] & 0x0003) * 256 + data[1]) - 512) * 0.001953125;
}

float bytetodata(int byte)
{
    //return (byte - 128) * 0.0078125; // -1 to 1
    return byte * 0.00390625; // 0 to 1
}


static int decodepacket(void)
{
    if (rxdata[0] == 165)
      {
          int sum = 0;
          for (int i = 0; i < 14; i++)
            {
                sum += rxdata[i];
            }
          if ((sum & 0xFF) == rxdata[14])
            {
                rx[0] = packettodata(&rxdata[4]);
                rx[1] = packettodata(&rxdata[6]);
                rx[2] = packettodata(&rxdata[10]);
                // throttle     
                rx[3] =
                    ((rxdata[8] & 0x0003) * 256 +
                     rxdata[9]) * 0.000976562f;





#ifdef USE_STOCK_TX
                char trims[4];
                trims[0] = rxdata[6] >> 2;
                trims[1] = rxdata[4] >> 2;

                for (int i = 0; i < 2; i++)
                    if (trims[i] != lasttrim[i])
                      {
                          aux[CH_PIT_TRIM + i] = trims[i] > lasttrim[i];
                          lasttrim[i] = trims[i];
                      }
#else
                aux[CH_INV] = (rxdata[3] & 0x80) ? 1 : 0;   // inverted flag

                aux[CH_VID] = (rxdata[2] & 0x10) ? 1 : 0;

                aux[CH_PIC] = (rxdata[2] & 0x20) ? 1 : 0;
#endif

                aux[CH_TO] = (rxdata[3] & 0x20) ? 1 : 0;   // take off flag
                      
                aux[CH_EMG] = (rxdata[3] & 0x04) ? 1 : 0;   // emg stop flag
                      
                aux[CH_FLIP] = (rxdata[2] & 0x08) ? 1 : 0;

#ifdef USE_ANALOG_AUX
                aux[CH_EXPERT] = (rxdata[1] > 0x7F) ? 1 : 0;
#else
                aux[CH_EXPERT] = (rxdata[1] == 0xfa) ? 1 : 0;
#endif

                aux[CH_HEADFREE] = (rxdata[2] & 0x02) ? 1 : 0;

                aux[CH_RTH] = (rxdata[2] & 0x01) ? 1 : 0;   // rth channel

#ifdef USE_ANALOG_AUX
                // Assign all analog versions of channels based on boolean channel data
                for (int i = 0; i < AUXNUMBER - 2; i++)
                {
                  if (i == CH_ANA_AUX1)
                    aux_analog[CH_ANA_AUX1] = bytetodata(rxdata[1]);
                  else if (i == CH_ANA_AUX2)
                    aux_analog[CH_ANA_AUX2] = bytetodata(rxdata[13]);
                  else
                    aux_analog[i] = aux[i] ? 1.0 : 0.0;
                  aux_analogchange[i] = 0;
                  if (lastaux_analog[i] != aux_analog[i])
                    aux_analogchange[i] = 1;
                  lastaux_analog[i] = aux_analog[i];
                }
#endif

							if (aux[LEVELMODE]){
								if (aux[RACEMODE] && !aux[HORIZON]){
									if ( ANGLE_EXPO_ROLL > 0.01) rx[0] = rcexpo(rx[0], ANGLE_EXPO_ROLL);
									if ( ACRO_EXPO_PITCH > 0.01) rx[1] = rcexpo(rx[1], ACRO_EXPO_PITCH);
									if ( ANGLE_EXPO_YAW > 0.01) rx[2] = rcexpo(rx[2], ANGLE_EXPO_YAW);
								}else if (aux[HORIZON]){
									if ( ANGLE_EXPO_ROLL > 0.01) rx[0] = rcexpo(rx[0], ACRO_EXPO_ROLL);
									if ( ACRO_EXPO_PITCH > 0.01) rx[1] = rcexpo(rx[1], ACRO_EXPO_PITCH);
									if ( ANGLE_EXPO_YAW > 0.01) rx[2] = rcexpo(rx[2], ANGLE_EXPO_YAW);
								}else{
									if ( ANGLE_EXPO_ROLL > 0.01) rx[0] = rcexpo(rx[0], ANGLE_EXPO_ROLL);
									if ( ANGLE_EXPO_PITCH > 0.01) rx[1] = rcexpo(rx[1], ANGLE_EXPO_PITCH);
									if ( ANGLE_EXPO_YAW > 0.01) rx[2] = rcexpo(rx[2], ANGLE_EXPO_YAW);}
							}else{
								if ( ACRO_EXPO_ROLL > 0.01) rx[0] = rcexpo(rx[0], ACRO_EXPO_ROLL);
								if ( ACRO_EXPO_PITCH > 0.01) rx[1] = rcexpo(rx[1], ACRO_EXPO_PITCH);
								if ( ACRO_EXPO_YAW > 0.01) rx[2] = rcexpo(rx[2], ACRO_EXPO_YAW);
							}

                for (int i = 0; i < AUXNUMBER - 2; i++)
                  {
                      auxchange[i] = 0;
                      if (lastaux[i] != aux[i])
                          auxchange[i] = 1;
                      lastaux[i] = aux[i];
                  }

                return 1;       // valid packet 
            }
          return 0;             // sum fail
      }
    return 0;                   // first byte different
}



void nextchannel()
{
    rf_chan++;
    rf_chan &= 3; // same as %4
    xn_writereg(0x25, rfchannel[rf_chan]);
}


unsigned long lastrxtime;
unsigned long failsafetime;
unsigned long secondtimer;

int failsafe = 0;


unsigned int skipchannel = 0;
int lastrxchan;
int timingfail = 0;




void checkrx(void)
{
    int packetreceived = checkpacket();
    int pass = 0;
    if (packetreceived)
      {
          if (rxmode == RX_MODE_BIND)
            {                   // rx startup , bind mode
                xn_readpayload(rxdata, 15);

#ifdef USE_ANALOG_AUX
                if (rxdata[0] == 0xa2 || rxdata[0] == 0xa1)
                {  // bind packet
                        if (rxdata[0] == 0xa1)
#else
                if (rxdata[0] == 0xa4 || rxdata[0] == 0xa3)
                {  // bind packet
                        if (rxdata[0] == 0xa3)
#endif
                        {
                            telemetry_enabled = 1;
                            packet_period = PACKET_PERIOD_TELEMETRY;
                        }
                        
                      rfchannel[0] = rxdata[6];
                      rfchannel[1] = rxdata[7];
                      rfchannel[2] = rxdata[8];
                      rfchannel[3] = rxdata[9];
                        

                      uint8_t rxaddr_regs[6] = { 0x2a ,  };
                      
                      for ( int i = 1 ; i < 6; i++)
                      {
                        rxaddr_regs[i] = rxdata[i];
                        rxaddress[i-1] = rxdata[i];
                      }
                      // write new rx address
                      writeregs( rxaddr_regs , sizeof(rxaddr_regs) );
                      rxaddr_regs[0] = 0x30; // tx register ( write ) number
                      
                      // write new tx address
                      writeregs( rxaddr_regs , sizeof(rxaddr_regs) );

                      xn_writereg(0x25, rfchannel[rf_chan]);    // Set channel frequency 
											
                      rxmode = RX_MODE_NORMAL;
											 

#ifdef SERIAL
                      printf(" BIND \n");
#endif
                  }
            }
          else
            {               // normal mode  
#ifdef RXDEBUG
                channelcount[rf_chan]++;
                packettime = gettime() - lastrxtime;

                if (skipchannel && !timingfail)
                    afterskip[skipchannel]++;
                if (timingfail)
                    afterskip[0]++;

#endif

                unsigned long temptime = gettime();

                xn_readpayload(rxdata, 15);
                pass = decodepacket();

                if (pass)
                  {
#ifdef RX_BAYANG_EXTENDED_TELEMETRY
                      if (telemetry_last_valid_rx_time != 0)
                        {
                          uint32_t gap_100us = (uint32_t)(temptime - telemetry_last_valid_rx_time) / 100U;
                          if (gap_100us > 255U)
                              telemetry_current_gap_100us = 255U;
                          else
                              telemetry_current_gap_100us = (uint8_t)gap_100us;
                          if (gap_100us > telemetry_max_gap_window_100us)
                              telemetry_max_gap_window_100us = gap_100us > 65535U ? 65535U : (uint16_t)gap_100us;
                        }
                      telemetry_last_valid_rx_time = temptime;
                      telemetry_rx_total++;
#endif
                      packetrx++;
                      if (telemetry_enabled)
                          beacon_sequence();
                      skipchannel = 0;
                      timingfail = 0;
                      lastrxchan = rf_chan;
                      lastrxtime = temptime;
                      failsafetime = temptime;
                      failsafe = 0;
                      if (!telemetry_send)
                          nextchannel();
                  }
                else
                  {
#ifdef RXDEBUG
                      failcount++;
#endif
                  }
				bind_safety++;					
				if (bind_safety > 9){								//requires 10 good frames to come in before rx_ready safety can be toggled to 1
				rx_ready = 1;											// because aux channels initialize low and clear the binding while armed flag before aux updates high
				bind_safety = 10;	}
            }                   // end normal rx mode

      }                         // end packet received

// finish sending if already started
    if (telemetry_send)
        beacon_sequence();

    unsigned long time = gettime();


    if (time - lastrxtime > (HOPPING_NUMBER * packet_period + 1000)
        && rxmode != RX_MODE_BIND)
      {
          //  channel with no reception   
          lastrxtime = time;
          // set channel to last with reception
          if (!timingfail)
              rf_chan = lastrxchan;
          // advance to next channel
          nextchannel();
          // set flag to discard packet timing
          timingfail = 1;
      }

    if (!timingfail && !telemetry_send && skipchannel < HOPPING_NUMBER + 1
        && rxmode != RX_MODE_BIND)
      {
          unsigned int temp = time - lastrxtime;

          if (temp > 1000
              && (temp - (PACKET_OFFSET)) / ((int) packet_period) >=
              (skipchannel + 1))
            {
                nextchannel();
#ifdef RXDEBUG
                skipstats[skipchannel]++;
#endif
                skipchannel++;
            }
      }

    if (time - failsafetime > FAILSAFETIME)
      {                         //  failsafe
          failsafe = 1;
          rx[0] = 0;
          rx[1] = 0;
          rx[2] = 0;
          rx[3] = 0;
      }

#ifdef RX_BAYANG_EXTENDED_TELEMETRY
    if (failsafe && !telemetry_previous_failsafe && telemetry_failsafe_count < 255U)
        telemetry_failsafe_count++;
    telemetry_previous_failsafe = failsafe;
#endif
      
    if ( !failsafe) autobind_inhibit = 1;
      else if ( !autobind_inhibit && time - autobindtime > 15000000 )
    {
        autobind_inhibit = 1;
        rxmode = RX_MODE_BIND;
        static uint8_t rxaddr[6] = { 0x2a , 0 , 0 , 0 , 0 , 0  };
        writeregs( rxaddr , sizeof(rxaddr) );
        xn_writereg(RF_CH, 0);      // bind on channel 0
    }
 
        
      
    if (gettime() - secondtimer > 1000000)
      {
          packetpersecond = packetrx;
#ifdef RX_BAYANG_EXTENDED_TELEMETRY
          int lost = 200 - packetpersecond;
          if (lost < 0)
              lost = 0;
          telemetry_packets_lost_window = lost > 255 ? 255 : (uint8_t)lost;
          telemetry_link_quality = packetpersecond >= 200 ? 100 : (uint8_t)(packetpersecond * 100 / 200);
          telemetry_max_gap_100us = telemetry_max_gap_window_100us;
          telemetry_max_gap_window_100us = 0;
          telemetry_lost_total += (uint32_t)lost;
#endif
          packetrx = 0;
          secondtimer = gettime();
      }


}


#endif
