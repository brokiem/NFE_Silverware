
#include <stdbool.h>
#include "pid.h"
#include "util.h"
#include "config.h"
#include "defines.h"
#include "math.h"

#define APIDNUMBER 2

//**************************** ANGLE PIDS - used in level mode to set leveling strength




//NotFastEnuf dynamic angle mode test settings 

// Leveling algorithm coefficients for small errors  (normal flying)
float apidkp1[APIDNUMBER] = { 10.00 };  // P TERM GAIN ROLL + PITCH 
float apidkd1[APIDNUMBER] = { 3.0 };    // D TERM GAIN ROLL + PITCH

// Leveling algorithm coefficients for large errors  (stick banging or collisions)
float apidkp2[APIDNUMBER] = { 5.00 };   // P TERM GAIN ROLL + PITCH 
const float apidkd2[APIDNUMBER] = { 0.0 }; // D2 is source-configured; const lets Cortex-M0 builds remove the zero term




// code variables below

#define OUTLIMIT_FLOAT (apidkp1[0]+apidkp2[0])   //set angle pid output limit to sum of both P terms just in case

float apidoutput1[APIDNUMBER];
float apidoutput2[APIDNUMBER];
float angleerror[APIDNUMBER];
float lasterror[APIDNUMBER];
float apidoutput[APIDNUMBER];


float apid(int x)
{
	// Cache values shared by both weighted branches.
	float e = angleerror[x];
	float abs_error = fabsf(e);
	float one_minus_abs_error = 1.0f - abs_error;
	float delta_error = e - lasterror[x];

extern float timefactor;
	// Factor each weighted branch.  This is the same controller equation as
	// before, but avoids one soft-float multiply on Cortex-M0.  Keep the two
	// branch-output globals with their original meaning in case debug code
	// observes them.
	float delta_time = delta_error * timefactor;
	apidoutput1[x] = one_minus_abs_error *
		(e * apidkp1[0] + delta_time * apidkd1[0]);

	// apidkd2[] is source-configured as exactly zero by the previous patch,
	// so its D contribution is exactly zero.  Preserve weighted P2 directly.
	apidoutput2[x] = abs_error * (e * apidkp2[0]);
	
  // apidoutput sum
	apidoutput[x] = apidoutput1[x] + apidoutput2[x];
	
	lasterror[x] = e;
	limitf(&apidoutput[x], OUTLIMIT_FLOAT);	
	
	return apidoutput[x];
}

