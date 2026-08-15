# Sensor Setup Guide for AgriPinya

## Overview
AgriPinya now supports real-time sensor monitoring with data analytics para sa:
- 🌊 **Soil Moisture Sensor** - Monitoring ng halumigmig ng lupa
- 🌡️ **Temperature & Humidity Sensor (DHT22)** - Monitoring ng temperatura at kahalumigmigan

## Current Status
⚠️ **Simulation Mode** - Ang system ay tumatakbo sa simulation mode dahil:
- RPi.GPIO libraries are not installed (for Raspberry Pi GPIO access)
- Adafruit_DHT library is not installed (for DHT sensors)
- Physical sensors are not yet connected

Ang app ay gumagamit ng simulated sensor data para ma-test ang UI at features.

## Hardware Requirements

### 1. Soil Moisture Sensor
- **Sensor**: Capacitive or Resistive Soil Moisture Sensor
- **ADC**: MCP3008 (8-channel 10-bit ADC) - dahil ang Raspberry Pi ay walang built-in analog input
- **Connections**:
  ```
  MCP3008 Pin    →  Raspberry Pi Pin
  VDD            →  3.3V (Pin 1)
  VREF           →  3.3V (Pin 1)
  AGND           →  GND (Pin 6)
  CLK            →  GPIO 11 (SCLK)
  DOUT           →  GPIO 9 (MISO)
  DIN            →  GPIO 10 (MOSI)
  CS/SHDN        →  GPIO 8 (CE0)
  DGND           →  GND (Pin 6)
  
  Soil Sensor    →  MCP3008
  VCC            →  3.3V
  GND            →  GND
  AOUT           →  CH0 (Channel 0)
  ```

### 2. DHT22 Temperature & Humidity Sensor
- **Sensor**: DHT22 (AM2302) - mas accurate kaysa DHT11
- **Connections**:
  ```
  DHT22 Pin      →  Raspberry Pi Pin
  VCC            →  3.3V or 5V (Pin 1 or 2)
  Data           →  GPIO 4 (Pin 7) + 10kΩ pull-up resistor
  GND            →  GND (Pin 6)
  ```
- **Note**: Lagyan ng 10kΩ resistor between VCC at Data pin

## Software Installation

### 1. Install GPIO Libraries
```bash
# Activate virtual environment
cd /home/voicebrain/agripinya
source venv/bin/activate

# Install RPi.GPIO
pip install RPi.GPIO

# Install DHT sensor library
pip install Adafruit_DHT

# Install SPI library for MCP3008 ADC
pip install spidev

# Optional: Install gpiozero for easier GPIO control
pip install gpiozero
```

### 2. Enable SPI on Raspberry Pi
```bash
# Run raspi-config
sudo raspi-config

# Navigate to:
# 3 Interface Options → P4 SPI → Enable

# Reboot
sudo reboot
```

### 3. Test Sensors

#### Test DHT22:
```python
import Adafruit_DHT

sensor = Adafruit_DHT.DHT22
pin = 4

humidity, temperature = Adafruit_DHT.read_retry(sensor, pin)

if humidity is not None and temperature is not None:
    print(f'Temperature: {temperature:.1f}°C')
    print(f'Humidity: {humidity:.1f}%')
else:
    print('Failed to read sensor')
```

#### Test Soil Moisture (with MCP3008):
```python
import spidev

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1350000

def read_adc(channel):
    adc = spi.xfer2([1, (8 + channel) << 4, 0])
    data = ((adc[1] & 3) << 8) + adc[2]
    return data

# Read from channel 0
moisture_raw = read_adc(0)
moisture_percent = (moisture_raw / 1023.0) * 100

print(f'Soil Moisture: {moisture_percent:.1f}%')
```

## Updating sensor_monitor.py for Real Sensors

Once hardware is connected, update `/home/voicebrain/agripinya/sensor_monitor.py`:

### For MCP3008 ADC Integration:
```python
# Add at the top
import spidev

# In __init__ method:
self.spi = spidev.SpiDev()
self.spi.open(0, 0)
self.spi.max_speed_hz = 1350000

# Update _read_adc_channel method:
def _read_adc_channel(self, channel: int) -> int:
    """Read from MCP3008 ADC channel"""
    adc = self.spi.xfer2([1, (8 + channel) << 4, 0])
    data = ((adc[1] & 3) << 8) + adc[2]
    return data
```

## GPIO Pin Configuration

Default pin configuration sa `sensor_monitor.py`:
```python
SOIL_MOISTURE_PIN = 17  # Not directly used - MCP3008 uses SPI
DHT_PIN = 4            # GPIO 4 for DHT22
```

Para baguhin ang pins, i-edit ang `sensor_monitor.py`:
```python
# Change these values sa __init__ method
self.SOIL_MOISTURE_PIN = 17  # Your preferred GPIO
self.DHT_PIN = 4            # Your preferred GPIO
```

## Features

### 1. Sensor Dashboard (`/sensors`)
- Real-time view ng lahat ng sensors
- Auto-refresh every 30 seconds
- Alert indicators para sa out-of-range values

### 2. Soil Moisture Page (`/sensors/soil-moisture`)
- Current moisture level with status (dry/optimal/wet)
- Historical chart (1-48 hours)
- Statistics (average, min, max, alerts)
- Automated recommendations

### 3. Temperature & Humidity Page (`/sensors/temperature-humidity`)
- Dual display for temp at humidity
- Combined historical chart
- Separate statistics for each measurement
- Automated recommendations

### 4. API Endpoints
```
GET /api/sensors/soil-moisture              - Current reading
GET /api/sensors/temperature-humidity       - Current reading
GET /api/sensors/soil-moisture/history      - Historical data
GET /api/sensors/temperature-humidity/history - Historical data
GET /api/sensors/all                        - All sensors at once
```

## Data Storage

Sensor data is automatically saved sa `sensor_data/` folder:
- `soil_moisture_YYYYMMDD.json` - Daily soil moisture readings
- `temp_humidity_YYYYMMDD.json` - Daily temperature & humidity readings
- Keeps last 1000 readings per day
- Automatic cleanup of old data

## Optimal Growing Conditions for Pineapple

### Soil Moisture:
- **Optimal**: 50-70%
- **Dry**: Below 30% (need watering)
- **Wet**: Above 80% (risk of root rot)

### Temperature:
- **Optimal**: 25-32°C
- **Too Cold**: Below 20°C
- **Too Hot**: Above 35°C

### Humidity:
- **Optimal**: 60-80%
- **Too Dry**: Below 40%
- **Too Humid**: Above 90% (risk of disease)

## Troubleshooting

### Issue: "RPi.GPIO not available"
**Solution**: Running on non-Raspberry Pi system or library not installed
- If on Raspberry Pi: `pip install RPi.GPIO`
- If testing on PC: App will use simulation mode (OK for development)

### Issue: "Adafruit_DHT not available"
**Solution**: `pip install Adafruit_DHT`

### Issue: DHT sensor returns None
**Causes**:
- Loose connections
- Wrong GPIO pin
- Missing pull-up resistor (10kΩ)
- Bad sensor

**Fix**:
1. Check all connections
2. Verify GPIO pin number
3. Add pull-up resistor
4. Try different GPIO pin
5. Test with different sensor

### Issue: Soil moisture always 0 or max
**Causes**:
- Sensor not in soil
- Wrong ADC configuration
- Bad connections

**Fix**:
1. Insert sensor properly in soil
2. Verify MCP3008 wiring
3. Test ADC with multimeter
4. Check SPI is enabled

## Next Steps

1. ✅ Connect soil moisture sensor to MCP3008
2. ✅ Connect DHT22 to GPIO 4
3. ✅ Install required libraries
4. ✅ Enable SPI interface
5. ✅ Test individual sensors
6. ✅ Restart Flask app
7. ✅ Monitor data on web interface

## Support

Para sa questions or issues:
- Check terminal output for error messages
- Verify GPIO connections with `gpio readall`
- Test sensors individually before integration
- Check `/var/log/syslog` for system errors

## License & Credits

- Built for AgriPinya Pineapple Farm Monitoring System
- Uses Chart.js for data visualization
- Compatible with Raspberry Pi 3/4/5
