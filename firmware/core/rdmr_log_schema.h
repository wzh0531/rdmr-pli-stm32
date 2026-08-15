#ifndef RDMR_LOG_SCHEMA_H
#define RDMR_LOG_SCHEMA_H

#define RDMR_LOG_HEADER \
    "run_id,scenario_id,algorithm,seed,n,input,clean,output," \
    "true_frequency,estimated_frequency,estimated_frequency_next," \
    "tracker_calls,tracker_searches,tracker_grid_evaluations,state," \
    "cycles,block_cycles_total,block_cycles_mean,block_cycles_p95," \
    "residual_ratio,desired_energy,input_error_energy," \
    "output_error_energy,numeric_flags\r\n"

#define RDMR_LOG_EXPECTED_ROWS \
    (RDMR_PROTOCOL_SAMPLE_COUNT / RDMR_BLOCK_SIZE)

#endif
