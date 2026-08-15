# Soil Moisture Sensor Connection Guide

## Overview
The AgriPinya soil moisture sensor system can detect when sensors are not properly connected using diagnostic tools and optional strict verification mode.

## Diagnosing Sensor Connection Issues

### Quick Diagnostic Check
Your system provides an automatic diagnostic function to verify sensor connectivity:

```bash
# Via API endpoint
curl http://localhost:5000/api/sensors/soil-moisture/diagnose

# Or test directly in Python
python3 -c "from agripinya.sensor_monitor import sensor_monitor; import json; print(json.dumps(sensor_monitor.diagnose_soil_moisture_sensor(), indent=2))"
```

### Understanding Diagnostic Output

The diagnostic function will return:

#### GPIO CRITICAL (Sensor Not Detectable)
- **Status**: "CRITICAL: Cannot access GPIO pin 17"
- **Cause**: GPIO pin not accessible
- **Solution**: 
  - Check if Raspberry Pi GPIO is enabled
  - Verify pin number in `sensor_monitor.py` (line ~66)
  - Check if pin is in use by another process

#### GPIO WARNING (Unstable Connection)
- **Status**: "WARNING: Partial GPIO access (inconsistent reads)"
- **Cause**: Intermittent GPIO access, likely loose connection
- **Solution**:
  - Verify physical wiring between sensor and Raspberry Pi
  - Check if pull-up/pull-down resistors are properly installed
  - Reseat connector pins

#### GPIO OK (Sensor Accessible)
- **Status**: "OK: GPIO accessible, readings are stable"
- **Interpretation**: GPIO pin is working correctly
- **Note**: This doesn't guarantee the sensor is wet/dry as indicated - verify by checking actual soil moisture

## Hardware Setup Verification

### Proper Connection Checklist
- [ ] Sensor VCC connected to Raspberry Pi 3.3V or 5V
- [ ] Sensor GND connected to Raspberry Pi GND
- [ ] Sensor DO (Digital Output) connected to GPIO 17
- [ ] Pull-up/Pull-down resistors installed (typically 10kΩ)
- [ ] All connections are secure and not loose

### Pull-Up/Pull-Down Resistor Installation
The digital output pin requires proper resistor configuration:

1. **If not already on sensor PCB**: Install a 10kΩ resistor
   - Between DO pin and VCC (pull-up) for active-low sensors
   - Between DO pin and GND (pull-down) for active-high sensors

2. **Check your sensor's datasheet** for the correct configuration

## Enabling Strict Sensor Verification

If you want the system to enforce strict sensor connectivity checks:

```bash
# Set environment variable before running the app
export STRICT_SENSOR_CHECK=1
python3 agripinya/app.py
```

When strict mode is enabled:
- The system will perform more rigorous hardware verification
- False positives from floating pins are reduced
- Sensors must show stable, realistic readings

## Common Issues

| Issue | Symptom | Solution |
|-------|---------|----------|
| Sensor not connected | Always reads "WET" but sensor is dry | Run diagnostic, verify physical connections |
| Loose connection | Readings fluctuate randomly | Reseat connectors, check for corrosion |
| Wrong GPIO pin | Invalid GPIO access error | Check config, verify pin numbering |
| Missing resistor | Unstable readings | Install pull-up/pull-down resistor |
| Wrong sensor voltage | No readings detected | Check VCC connection (3.3V or 5V as needed) |

## Testing Sensor Response

After setting up hardware, test the sensor response:

1. **Run diagnostic**: Get baseline readings
2. **Apply water**: Dip sensor in water, run diagnostic again
3. **Dry sensor**: Let sensor dry, run diagnostic again
4. **Verify changes**: Readings should change when soil moisture changes

## Support & Debugging

For detailed sensor reading information:
```bash
# Get current reading with GPIO details
curl http://localhost:5000/api/sensors/soil-moisture

# Run extended diagnostic
python3 -c "from agripinya.sensor_monitor import sensor_monitor; diag = sensor_monitor.diagnose_soil_moisture_sensor(); print('Readings:', [r.get('interpretation') for r in diag['readings']])"
```

## GPIO Pin Reference

Default configuration:
- **Soil Moisture DO Pin**: GPIO 17 (Physical Pin 11)
- **Temperature/Humidity Pin**: GPIO 27 (Physical Pin 13)

To change pins, edit `agripinya/sensor_monitor.py` and modify the `SOIL_MOISTURE_PIN` and `DHT_PIN` variables.
