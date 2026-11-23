# Retired high-rate experiment, 21 October 2026

The user ultimately requested a maximum of 500 Hz for accelerometer/gyroscope and 100 Hz for magnetometer. Options 750/1000/1125 Hz and the rate matrix runner were removed. API validation and a boot migration also enforce the supported 50/100/200/500 Hz choices.

Temporary 1125 Hz firmware read the sensor FIFO without overflows but exceeded sustained CSV/SD writer throughput. See logger-profile-before.json and logger-profile-after.json. These are failed experiments, not supported performance claims. Temporary logger profiling, ROM CRC optimisation and larger stdio buffers were reverted to the proven 500 Hz path.

The first capture in hardware-rates-1125-1125.json was interrupted while the user changed settings/restarted the device (confirmed in chat); it is not a successful CSV integrity test. The original 500 Hz configuration was restored, retaining the user's current LCD orientation.

The final supported firmware and its verification are described in ../release/firmware.json.
