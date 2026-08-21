#include "project.h"
#include "config.h"
#include "defines.h"

#include <stdint.h>

#define BENCHMARK_ITERATIONS 2048u
#define BENCHMARK_FLOATS_PER_RECORD 17u
#define BENCHMARK_MAGIC 0x4e464542u

/* Globals normally owned by main.c or peripheral-facing translation units. */
float rx[4];
float gyro[3];
float accel[3];
float accelcal[3];
float looptime;
float vbattfilt;
float vbatt_comp;
float lipo_cell_count;
float aux_analog[AUXNUMBER];
float lastaux_analog[AUXNUMBER];
float rx_override[4];

char aux[AUXNUMBER];
char lastaux[AUXNUMBER];
char auxchange[AUXNUMBER];
char aux_analogchange[AUXNUMBER];

int armed_state;
int in_air;
int arming_release;
int binding_while_armed;
int rx_ready;
int failsafe;
int ledcommand;
int ledblink;
int controls_override;
int acro_override;
int flash_feature_2;
int flash_feature_3;

static unsigned long benchmark_time_us;
static float captured_motors[4];

/* Exposed symbols read by benchmark/run_elf.py. */
volatile uint32_t benchmark_magic;
volatile uint32_t benchmark_completed;
volatile uint32_t benchmark_iteration_count;
volatile uint32_t benchmark_floats_per_record;
volatile float benchmark_output[BENCHMARK_ITERATIONS][BENCHMARK_FLOATS_PER_RECORD];
volatile uint32_t benchmark_modes[BENCHMARK_ITERATIONS];

extern float pidoutput[PIDNUMBER];
extern float setpoint[PIDNUMBER];
extern float GEstG[3];
extern float thrsum;
extern int onground;
extern int onground_long;

extern float lpffilter(float in, int num);
extern float lpffilter2(float in, int num);
extern void control(void);
extern void imu_calc(void);
extern void __cpp_initialize__aeabi_(void);

unsigned long gettime(void)
{
	benchmark_time_us += LOOPTIME;
	return benchmark_time_us;
}

void delay(uint32_t value)
{
	(void)value;
}

/* imu_init() is not a benchmark root, but armclang keeps its reference while
 * resolving imu.o.  Keep it hardware-free if the linker retains that section. */
void sixaxis_read(void)
{
}

void pwm_set(uint8_t number, float value)
{
	if (number < 4u) {
		captured_motors[number] = value;
	}
}

static uint32_t xorshift32(uint32_t *state)
{
	uint32_t value = *state;
	value ^= value << 13;
	value ^= value >> 17;
	value ^= value << 5;
	*state = value;
	return value;
}

static float signed_unit(uint32_t *state)
{
	uint32_t value = xorshift32(state) & 0xffffu;
	return ((float)value - 32768.0f) * (1.0f / 32768.0f);
}

static void clear_state(void)
{
	for (uint32_t i = 0; i < AUXNUMBER; ++i) {
		aux[i] = 0;
		lastaux[i] = 0;
		auxchange[i] = 0;
		aux_analog[i] = 0.0f;
		lastaux_analog[i] = 0.0f;
		aux_analogchange[i] = 0;
	}

	for (uint32_t i = 0; i < 4u; ++i) {
		rx[i] = 0.0f;
		rx_override[i] = 0.0f;
		captured_motors[i] = 0.0f;
	}

	for (uint32_t i = 0; i < 3u; ++i) {
		gyro[i] = 0.0f;
		accel[i] = 0.0f;
		accelcal[i] = 0.0f;
	}

	looptime = 0.001f;
	vbattfilt = 4.0f;
	vbatt_comp = 4.0f;
	lipo_cell_count = 1.0f;
	armed_state = 1;
	in_air = 1;
	arming_release = 1;
	binding_while_armed = 0;
	rx_ready = 1;
	failsafe = 0;
	ledcommand = 0;
	ledblink = 0;
	controls_override = 0;
	acro_override = 0;
	flash_feature_2 = 0;
	flash_feature_3 = 1;
	onground = 0;
	onground_long = 0;
	benchmark_time_us = 0;
	GEstG[0] = 0.0f;
	GEstG[1] = 0.0f;
	GEstG[2] = 1.0f;
}

static uint32_t configure_mode(uint32_t iteration)
{
	uint32_t phase = (iteration / 256u) & 3u;
	aux[ARMING] = 1;
	aux[IDLE_UP] = 1;
	aux[RATES] = 1;
	aux[LEVELMODE] = phase != 0u;
	aux[RACEMODE] = phase == 2u;
	aux[HORIZON] = phase == 3u;
	aux[PIDPROFILE] = (iteration / 512u) & 1u;
	return phase | ((uint32_t)aux[PIDPROFILE] << 8);
}

void benchmark_run(void)
{
	uint32_t random_state = 0x13579bdfu;
	clear_state();
	benchmark_magic = BENCHMARK_MAGIC;
	benchmark_completed = 0;
	benchmark_iteration_count = BENCHMARK_ITERATIONS;
	benchmark_floats_per_record = BENCHMARK_FLOATS_PER_RECORD;

	for (uint32_t iteration = 0; iteration < BENCHMARK_ITERATIONS; ++iteration) {
		uint32_t mode = configure_mode(iteration);
		float roll_input = signed_unit(&random_state) * 0.85f;
		float pitch_input = signed_unit(&random_state) * 0.85f;
		float yaw_input = signed_unit(&random_state) * 0.70f;
		float throttle_input = 0.15f + (float)(xorshift32(&random_state) & 0xffffu) * (0.75f / 65535.0f);

		rx[0] = roll_input;
		rx[1] = pitch_input;
		rx[2] = yaw_input;
		rx[3] = throttle_input;

		for (uint32_t axis = 0; axis < 3u; ++axis) {
			float sensor_noise = signed_unit(&random_state) * 0.08f;
			float stimulus = (axis == 0u ? roll_input : (axis == 1u ? pitch_input : yaw_input));
			float gyro_sample = stimulus * 5.0f + sensor_noise;
			gyro[axis] = lpffilter(gyro_sample, (int)axis);
			gyro[axis] = lpffilter2(gyro[axis], (int)axis);
		}

		/* sixaxis_read() supplies raw MPU6050 counts; imu_calc() performs the
		 * production 1/2048 scaling. */
		accel[0] = roll_input * 368.0f + signed_unit(&random_state) * 30.0f;
		accel[1] = pitch_input * 368.0f + signed_unit(&random_state) * 30.0f;
		accel[2] = 2048.0f + signed_unit(&random_state) * 52.0f;
		vbattfilt = 4.2f - (float)iteration * (0.7f / (float)BENCHMARK_ITERATIONS);
		vbatt_comp = vbattfilt + throttle_input * 0.10f;

		/* Preserve production main-loop ordering: control consumes prior attitude. */
		control();
		imu_calc();

		for (uint32_t motor = 0; motor < 4u; ++motor) {
			benchmark_output[iteration][motor] = captured_motors[motor];
		}
		for (uint32_t axis = 0; axis < 3u; ++axis) {
			benchmark_output[iteration][4u + axis] = gyro[axis];
			benchmark_output[iteration][7u + axis] = pidoutput[axis];
			benchmark_output[iteration][10u + axis] = setpoint[axis];
			benchmark_output[iteration][13u + axis] = GEstG[axis];
		}
		benchmark_output[iteration][16] = thrsum;
		benchmark_modes[iteration] = mode;
	}

	benchmark_completed = 1;
}

/* The firmware startup calls the Arm C++ initializer before main().  The
 * harness has a custom entry point, so preserve that initialization here for
 * filter.cpp's production objects. */
void benchmark_entry(void)
{
	__cpp_initialize__aeabi_();
	benchmark_run();
}
