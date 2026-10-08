# Raw Real-Hand Logs

Put raw DexH13 SDK logs here if you want to keep them next to the derived calibration CSV.

Suggested raw fields include:

- `timestamp_s`
- `joint_positions_radian`
- `finger_tactile_resultant`
- `finger_tactile_detail_raw`
- `external_force_sensor_raw`
- `fixture_pose`

These raw logs are not consumed directly by the current calibration scripts. Convert them into
`data/calibration/real_press_samples.csv` before running the fitting workflow.
