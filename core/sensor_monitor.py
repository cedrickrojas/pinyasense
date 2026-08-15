"""
Sensor Monitor Module for AgriPinya
Handles reading from various sensors connected to Raspberry Pi GPIO
"""

import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import random
import json
from pathlib import Path

from . import notification_service
from .email_service import send_email_notification

# Try to import GPIO libraries (will fallback to simulation if not available)
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
    # Try to actually initialize GPIO to check if hardware access is possible
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO_AVAILABLE = True
        print("✅ RPi.GPIO initialized successfully")
    except Exception as gpio_init_error:
        GPIO_AVAILABLE = False
        print(f"⚠️  RPi.GPIO initialization failed: {gpio_init_error}")
        print("   Using simulation mode for GPIO readings")
except ImportError:
    GPIO_AVAILABLE = False
    print("⚠️  RPi.GPIO not available, using simulation mode")


def _read_pi_model() -> str:
    try:
        with open('/proc/device-tree/model', 'r') as f:
            return (f.read() or '').strip('\x00').strip()
    except Exception:
        return ''


_PI_MODEL = _read_pi_model()
if _PI_MODEL and 'Raspberry Pi 5' in _PI_MODEL:
    # RPi.GPIO is not reliable on Raspberry Pi 5; prefer gpiozero/lgpio.
    if GPIO_AVAILABLE:
        GPIO_AVAILABLE = False
        print("⚠️  Raspberry Pi 5 detected: disabling RPi.GPIO backend; using gpiozero/lgpio")

# Try gpiozero as fallback GPIO backend
try:
    from gpiozero import DigitalInputDevice, OutputDevice, Device
    GPIOZERO_AVAILABLE = True
    print("✅ gpiozero backend available")

    # On newer Raspberry Pi OS (and Pi 5), gpiozero may not auto-select a working
    # backend in venvs. If /dev/gpiochip0 exists and no factory is selected, try lgpio.
    try:
        if Device.pin_factory is None and os.path.exists('/dev/gpiochip0'):
            from gpiozero.pins.lgpio import LGPIOFactory
            Device.pin_factory = LGPIOFactory()
            print("✅ gpiozero LGPIO pin factory initialized")
    except Exception as pin_factory_error:
        print(f"⚠️  gpiozero pin factory init failed: {pin_factory_error}")
except ImportError:
    GPIOZERO_AVAILABLE = False
    print("⚠️  gpiozero not available")

# Try to import DHT sensor library
try:
    import Adafruit_DHT
    DHT_AVAILABLE = True
except ImportError:
    DHT_AVAILABLE = False
    print("⚠️  Adafruit_DHT not available")

# Try CircuitPython DHT backend (works on newer Raspberry Pi models)
try:
    import adafruit_dht
    from adafruit_blinka.microcontroller.bcm283x import pin as blinka_pin
    DHT_CIRCUITPY_AVAILABLE = True
    print("✅ CircuitPython DHT backend available")
except ImportError:
    DHT_CIRCUITPY_AVAILABLE = False
    print("⚠️  CircuitPython DHT backend not available")


class SensorMonitor:
    """Monitor and manage sensor readings"""
    
    def __init__(self, data_folder='sensor_data'):
        """Initialize sensor monitor"""
        self.data_folder = data_folder
        os.makedirs(self.data_folder, exist_ok=True)
        
        # GPIO Pin Configuration
        self.SOIL_MOISTURE_PIN = int(os.getenv('SOIL_MOISTURE_PIN', '17'))
        self.SOIL_MOISTURE_ADC_CHANNEL = 0
        self.DHT_PIN = int(os.getenv('DHT_PIN', '4'))  # default GPIO 4 (Physical Pin 7)
        self.DHT_SENSOR = Adafruit_DHT.DHT22 if DHT_AVAILABLE else None
        self.dht_device = None
        self.soil_sensor_device = None
        self.water_pump_device = None
        self.water_pump_breaker_device = None
        # Supported values: digital_do, analog_adc
        self.SOIL_SENSOR_MODE = os.getenv('SOIL_SENSOR_MODE', 'digital_do').strip().lower()

        # Water pump / relay configuration.
        # Default is GPIO27 to keep the relay on the requested pin and avoid
        # conflict with the default soil pin (GPIO17) and default DHT pin (GPIO4).
        self.WATER_PUMP_PIN = int(os.getenv('WATER_PUMP_PIN', '27'))
        self.WATER_PUMP_ACTIVE_LOW = os.getenv('WATER_PUMP_ACTIVE_LOW', '0').strip().lower() in ('1', 'true', 'yes', 'on')
        self.WATER_PUMP_DEFAULT_DURATION = int(os.getenv('WATER_PUMP_DEFAULT_DURATION', '5'))
        breaker_pin_raw = os.getenv('WATER_PUMP_BREAKER_PIN', '').strip()
        self.WATER_PUMP_BREAKER_PIN = int(breaker_pin_raw) if breaker_pin_raw else None
        self.WATER_PUMP_BREAKER_ACTIVE_LOW = os.getenv('WATER_PUMP_BREAKER_ACTIVE_LOW', '1').strip().lower() in ('1', 'true', 'yes', 'on')
        # Default to no breaker requirement unless a breaker pin is actually wired.
        self.WATER_PUMP_BREAKER_REQUIRED = os.getenv('WATER_PUMP_BREAKER_REQUIRED', '0').strip().lower() in ('1', 'true', 'yes', 'on')
        self.water_pump_state = False
        # Pump is always armed and ready for manual control (no re-arm requirement)
        self.water_pump_rearm_required = False
        self._last_water_pump_breaker_on = None

        if self.WATER_PUMP_PIN == self.SOIL_MOISTURE_PIN:
            print(
                f"⚠️  Water pump and soil moisture sensor are both assigned to GPIO {self.WATER_PUMP_PIN}. "
                "Set WATER_PUMP_PIN or SOIL_MOISTURE_PIN to different GPIO pins."
            )

        if self.WATER_PUMP_PIN == self.DHT_PIN:
            print(
                f"⚠️  Water pump relay and DHT sensor are both assigned to GPIO {self.WATER_PUMP_PIN}. "
                "Set WATER_PUMP_PIN or DHT_PIN to different GPIO pins."
            )

        if self.WATER_PUMP_BREAKER_PIN is not None:
            if self.WATER_PUMP_BREAKER_PIN == self.WATER_PUMP_PIN:
                print(
                    f"⚠️  Water pump breaker and relay are both assigned to GPIO {self.WATER_PUMP_BREAKER_PIN}. "
                    "Set WATER_PUMP_BREAKER_PIN to a different GPIO pin."
                )
            if self.WATER_PUMP_BREAKER_PIN == self.SOIL_MOISTURE_PIN:
                print(
                    f"⚠️  Water pump breaker and soil moisture sensor are both assigned to GPIO {self.WATER_PUMP_BREAKER_PIN}. "
                    "Set WATER_PUMP_BREAKER_PIN or SOIL_MOISTURE_PIN to different GPIO pins."
                )
        
        # Allow simulating temperature/humidity when hardware or libraries are missing
        # Developers can enable with env `TEMP_HUMIDITY_SIMULATION=1` but default is off.
        self.ALLOW_TH_SIMULATION = os.getenv('TEMP_HUMIDITY_SIMULATION', '0').strip().lower() == '1'
        
        # Sensor connection verification mode
        # Set STRICT_SENSOR_CHECK=1 to enforce hardware verification
        self.STRICT_SENSOR_CHECK = os.getenv('STRICT_SENSOR_CHECK', '0').strip().lower() == '1'
        self.SENSOR_VERIFICATION_CACHE = {}  # Cache to avoid repeated failing checks
        
        # Setup GPIO if available (already initialized in module import)
        if GPIO_AVAILABLE:
            GPIO.setwarnings(False)
        
        # Sensor thresholds
        self.SOIL_MOISTURE_THRESHOLDS = {
            'dry': 30,
            'optimal': 60,
            'wet': 80
        }
        # User-provided raw ADC thresholds
        # dry: 700-1023, normal: 400-700, wet: 0-400
        self.SOIL_MOISTURE_ADC_THRESHOLDS = {
            'wet_max': 400,
            'normal_max': 700,
            'adc_max': 1023
        }
        
        self.TEMP_THRESHOLDS = {
            'too_cold': 20,
            'optimal_min': 25,
            'optimal_max': 32,
            'too_hot': 35
        }
        
        self.HUMIDITY_THRESHOLDS = {
            'too_dry': 40,
            'optimal_min': 60,
            'optimal_max': 80,
            'too_humid': 90
        }
    
    def _check_sensor_connection(self, gpio_pin: int, num_reads: int = 5) -> bool:
        """
        Check if soil moisture sensor is properly connected by reading multiple times.
        Returns True if readings appear valid (sensor connected), False otherwise.

        The algorithm attempts to detect "floating" pins by toggling the internal
        pull-up / pull-down resistors. A disconnected sensor will be influenced by
        these pulls and produce different values, whereas a connected sensor should
        hold the same value regardless of which pull is selected (unless it's
        actively driving the line).
        
        Can be bypassed with SKIP_SENSOR_CHECK=1 environment variable.
        """
        # Allow users to skip sensor connection check if they know hardware is connected
        skip_check = os.getenv('SKIP_SENSOR_CHECK', '0').strip().lower() == '1'
        if skip_check:
            print(f"✅ Sensor connection check skipped (SKIP_SENSOR_CHECK=1) - assuming GPIO {gpio_pin} is connected")
            return True
        
        try:
            if not GPIO_AVAILABLE and not GPIOZERO_AVAILABLE:
                print(f"❌ No GPIO backend available - cannot read sensor. Install RPi.GPIO or gpiozero.")
                return False

            if GPIO_AVAILABLE:
                # test with pull-up
                try:
                    GPIO.setup(gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                    up_val = GPIO.input(gpio_pin)
                except Exception as e:
                    print(f"❌ Pull-up read failed on GPIO {gpio_pin}: {e}")
                    return False

                # test with pull-down
                try:
                    GPIO.setup(gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
                    down_val = GPIO.input(gpio_pin)
                except Exception as e:
                    print(f"❌ Pull-down read failed on GPIO {gpio_pin}: {e}")
                    return False

                if up_val != down_val:
                    print(f"❌ GPIO {gpio_pin} value changed with pull-up/down ({up_val}->{down_val}) - sensor is disconnected")
                    return False

                # do a few normal reads with no pull to confirm stability
                readings = []
                for _ in range(num_reads):
                    GPIO.setup(gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_OFF)
                    readings.append(GPIO.input(gpio_pin))
                print(f"✅ GPIO {gpio_pin} stable readings: {readings}")
                return True

            elif GPIOZERO_AVAILABLE:
                readings = []
                for _ in range(num_reads):
                    if self.soil_sensor_device is None:
                        self.soil_sensor_device = DigitalInputDevice(gpio_pin)
                    readings.append(1 if self.soil_sensor_device.value else 0)
                if len(set(readings)) == 1:
                    print(f"✅ gpiozero stable readings on GPIO {gpio_pin}: {readings}")
                    return True
                else:
                    print(f"❌ gpiozero unstable readings on GPIO {gpio_pin}: {readings} - sensor may be disconnected")
                    return False

            return False  # If we can't check and reach here, sensor not connected
        except Exception as e:
            print(f"❌ Sensor connection check failed: {e}")
            return False  # Strict mode: if check fails, assume disconnected

    def _pump_on_level(self):
        return GPIO.LOW if self.WATER_PUMP_ACTIVE_LOW else GPIO.HIGH

    def _pump_off_level(self):
        return GPIO.HIGH if self.WATER_PUMP_ACTIVE_LOW else GPIO.LOW

    def _breaker_on_level(self):
        return GPIO.LOW if self.WATER_PUMP_BREAKER_ACTIVE_LOW else GPIO.HIGH

    def _breaker_off_level(self):
        return GPIO.HIGH if self.WATER_PUMP_BREAKER_ACTIVE_LOW else GPIO.LOW

    def _force_water_pump_off(self) -> Dict:
        """Drive the pump output to OFF and clear the logical state."""
        try:
            if GPIOZERO_AVAILABLE:
                if self.water_pump_device is None:
                    self._setup_water_pump()
                if self.water_pump_device is not None:
                    self.water_pump_device.off()
            elif GPIO_AVAILABLE:
                GPIO.setup(self.WATER_PUMP_PIN, GPIO.OUT)
                GPIO.output(self.WATER_PUMP_PIN, self._pump_off_level())

            self.water_pump_state = False
            self.water_pump_rearm_required = True
            return {
                'status': 'off',
                'gpio_pin': self.WATER_PUMP_PIN,
                'breaker_pin': self.WATER_PUMP_BREAKER_PIN,
                'timestamp': datetime.now().isoformat(),
            }
        except Exception as e:
            return {
                'error': str(e),
                'gpio_pin': self.WATER_PUMP_PIN,
                'breaker_pin': self.WATER_PUMP_BREAKER_PIN,
                'timestamp': datetime.now().isoformat(),
            }

    def _safe_pump_state_after_breaker_check(self, breaker_on: bool) -> None:
        """Prevent the relay from remaining energized while the breaker is open."""
        if not breaker_on:
            self._force_water_pump_off()
            self._last_water_pump_breaker_on = False
            return

        if self._last_water_pump_breaker_on is False:
            # Breaker was just restored. Require a fresh ON command from the system
            # so the pump never wakes up automatically on breaker re-closure.
            self._force_water_pump_off()

        self._last_water_pump_breaker_on = True

    def is_water_pump_breaker_on(self) -> bool:
        """Return True only when the pump breaker/switch is enabled."""
        if self.WATER_PUMP_BREAKER_PIN is None:
            return not self.WATER_PUMP_BREAKER_REQUIRED

        try:
            if GPIOZERO_AVAILABLE:
                if self.water_pump_breaker_device is None:
                    self.water_pump_breaker_device = DigitalInputDevice(
                        self.WATER_PUMP_BREAKER_PIN,
                        pull_up=self.WATER_PUMP_BREAKER_ACTIVE_LOW,
                    )
                breaker_on = bool(self.water_pump_breaker_device.value) if not self.WATER_PUMP_BREAKER_ACTIVE_LOW else not bool(self.water_pump_breaker_device.value)
                self._safe_pump_state_after_breaker_check(breaker_on)
                return breaker_on

            if GPIO_AVAILABLE:
                pull_mode = GPIO.PUD_UP if self.WATER_PUMP_BREAKER_ACTIVE_LOW else GPIO.PUD_DOWN
                GPIO.setup(self.WATER_PUMP_BREAKER_PIN, GPIO.IN, pull_up_down=pull_mode)
                raw_value = bool(GPIO.input(self.WATER_PUMP_BREAKER_PIN))
                breaker_on = raw_value if not self.WATER_PUMP_BREAKER_ACTIVE_LOW else not raw_value
                self._safe_pump_state_after_breaker_check(breaker_on)
                return breaker_on

            return False
        except Exception as e:
            print(f"⚠️  Unable to read water pump breaker on GPIO {self.WATER_PUMP_BREAKER_PIN}: {e}")
            return False

    def _setup_water_pump(self) -> bool:
        """Initialize the water pump GPIO pin in a safe OFF state."""
        try:
            if not GPIO_AVAILABLE and not GPIOZERO_AVAILABLE:
                return False

            if self.water_pump_device is not None:
                try:
                    self.water_pump_device.close()
                except Exception:
                    pass
                self.water_pump_device = None

            # Prefer gpiozero for Raspberry Pi 5 and modern kernels.
            if GPIOZERO_AVAILABLE:
                self.water_pump_device = OutputDevice(
                    self.WATER_PUMP_PIN,
                    active_high=not self.WATER_PUMP_ACTIVE_LOW,
                    initial_value=False,
                )
                return True

            if GPIO_AVAILABLE:
                GPIO.setup(self.WATER_PUMP_PIN, GPIO.OUT)
                GPIO.output(self.WATER_PUMP_PIN, self._pump_off_level())
                return True

            return False
        except Exception as e:
            print(f"⚠️  Water pump initialization failed on GPIO {self.WATER_PUMP_PIN}: {e}")
            return False

    def _validate_pump_pin_assignment(self) -> Optional[str]:
        """Return an error message when pump GPIO assignments are unsafe."""
        if self.WATER_PUMP_PIN == self.SOIL_MOISTURE_PIN:
            return (
                f'Invalid pin assignment: WATER_PUMP_PIN ({self.WATER_PUMP_PIN}) '
                f'matches SOIL_MOISTURE_PIN ({self.SOIL_MOISTURE_PIN}). '
                'Assign different GPIO pins before turning on the pump.'
            )

        if self.WATER_PUMP_PIN == self.DHT_PIN:
            return (
                f'Invalid pin assignment: WATER_PUMP_PIN ({self.WATER_PUMP_PIN}) '
                f'matches DHT_PIN ({self.DHT_PIN}). '
                'Assign different GPIO pins before turning on the pump.'
            )

        if self.WATER_PUMP_BREAKER_PIN is not None and self.WATER_PUMP_BREAKER_PIN == self.WATER_PUMP_PIN:
            return (
                f'Invalid pin assignment: WATER_PUMP_BREAKER_PIN ({self.WATER_PUMP_BREAKER_PIN}) '
                f'matches WATER_PUMP_PIN ({self.WATER_PUMP_PIN}). '
                'Assign different GPIO pins before turning on the pump.'
            )

        return None

    def set_water_pump(self, enabled: bool) -> Dict:
        """Turn the water pump on or off."""
        try:
            pin_conflict_error = self._validate_pump_pin_assignment()
            if pin_conflict_error:
                self._force_water_pump_off()
                return {
                    'error': pin_conflict_error,
                    'status': 'blocked',
                    'gpio_pin': self.WATER_PUMP_PIN,
                    'soil_moisture_pin': self.SOIL_MOISTURE_PIN,
                    'dht_pin': self.DHT_PIN,
                    'breaker_pin': self.WATER_PUMP_BREAKER_PIN,
                    'timestamp': datetime.now().isoformat(),
                }

            if not GPIO_AVAILABLE and not GPIOZERO_AVAILABLE:
                return {
                    'error': 'GPIO backend unavailable. Unable to control water pump.',
                    'gpio_pin': self.WATER_PUMP_PIN,
                    'timestamp': datetime.now().isoformat(),
                }

            breaker_on = self.is_water_pump_breaker_on()
            if enabled and not breaker_on:
                self._force_water_pump_off()
                return {
                    'error': 'Water pump breaker is off. Turn on the breaker before running the pump.',
                    'status': 'blocked',
                    'gpio_pin': self.WATER_PUMP_PIN,
                    'breaker_pin': self.WATER_PUMP_BREAKER_PIN,
                    'breaker_required': self.WATER_PUMP_BREAKER_REQUIRED,
                    'breaker_on': breaker_on,
                    'timestamp': datetime.now().isoformat(),
                }

            if GPIOZERO_AVAILABLE:
                if self.water_pump_device is None:
                    self._setup_water_pump()
                if self.water_pump_device is None:
                    return {
                        'error': 'Unable to initialize water pump device.',
                        'gpio_pin': self.WATER_PUMP_PIN,
                        'timestamp': datetime.now().isoformat(),
                    }
                if enabled:
                    self.water_pump_device.on()
                else:
                    self.water_pump_device.off()
            elif GPIO_AVAILABLE:
                GPIO.setup(self.WATER_PUMP_PIN, GPIO.OUT)
                GPIO.output(self.WATER_PUMP_PIN, self._pump_on_level() if enabled else self._pump_off_level())

            self.water_pump_state = enabled
            # No re-arm requirement - pump is always ready for manual control
            self.water_pump_rearm_required = False
            return {
                'status': 'on' if enabled else 'off',
                'gpio_pin': self.WATER_PUMP_PIN,
                'active_low': self.WATER_PUMP_ACTIVE_LOW,
                'breaker_pin': self.WATER_PUMP_BREAKER_PIN,
                'breaker_required': self.WATER_PUMP_BREAKER_REQUIRED,
                'breaker_on': breaker_on,
                'rearm_required': self.water_pump_rearm_required,
                'timestamp': datetime.now().isoformat(),
            }
        except Exception as e:
            print(f"❌ Error controlling water pump: {e}")
            return {
                'error': str(e),
                'gpio_pin': self.WATER_PUMP_PIN,
                'breaker_pin': self.WATER_PUMP_BREAKER_PIN,
                'rearm_required': self.water_pump_rearm_required,
                'timestamp': datetime.now().isoformat(),
            }

    def water_pump_on(self) -> Dict:
        """Turn the water pump on."""
        return self.set_water_pump(True)

    def water_pump_off(self) -> Dict:
        """Turn the water pump off."""
        return self.set_water_pump(False)

    def run_water_pump_for_seconds(self, duration_seconds: Optional[int] = None) -> Dict:
        """Run the pump for a fixed number of seconds, then stop it."""
        run_seconds = self.WATER_PUMP_DEFAULT_DURATION if duration_seconds is None else max(1, int(duration_seconds))

        start_result = self.water_pump_on()
        if start_result.get('error'):
            return start_result

        time.sleep(run_seconds)
        stop_result = self.water_pump_off()

        return {
            'status': 'completed',
            'gpio_pin': self.WATER_PUMP_PIN,
            'duration_seconds': run_seconds,
            'start': start_result,
            'stop': stop_result,
            'breaker_pin': self.WATER_PUMP_BREAKER_PIN,
            'rearm_required': self.water_pump_rearm_required,
            'timestamp': datetime.now().isoformat(),
        }

    def read_soil_moisture(self) -> Dict:
        """Read soil moisture sensor (Digital DO pin)"""
        try:
            sensor_value = None

            if self.SOIL_SENSOR_MODE == 'analog_adc':
                adc_value = int(self._read_adc_channel(self.SOIL_MOISTURE_ADC_CHANNEL))
                adc_value = max(0, min(self.SOIL_MOISTURE_ADC_THRESHOLDS['adc_max'], adc_value))

                if adc_value <= self.SOIL_MOISTURE_ADC_THRESHOLDS['wet_max']:
                    status = 'wet'
                    state = 'WET'
                    recommendation = 'Soil is wet. Reduce irrigation.'
                    alert = True
                elif adc_value <= self.SOIL_MOISTURE_ADC_THRESHOLDS['normal_max']:
                    status = 'optimal'
                    state = 'NORMAL'
                    recommendation = 'Soil moisture is normal.'
                    alert = False
                else:
                    status = 'dry'
                    state = 'DRY'
                    recommendation = 'Soil is dry. Irrigation is needed.'
                    alert = True

                print(f"🌱 Soil Moisture Sensor ADC - CH{self.SOIL_MOISTURE_ADC_CHANNEL}: raw={adc_value}, state={state}")

                return {
                    'value': adc_value,
                    'unit': 'ADC',
                    'status': status,
                    'state': state,
                    'raw_value': adc_value,
                    'adc_channel': self.SOIL_MOISTURE_ADC_CHANNEL,
                    'sensor_mode': 'analog_adc',
                    'thresholds': {
                        'dry_min': 700,
                        'normal_min': 400,
                        'normal_max': 700,
                        'wet_max': 400
                    },
                    'recommendation': recommendation,
                    'alert': alert,
                    'timestamp': datetime.now().isoformat()
                }

            # For digital mode, check if sensor is properly connected
            if not self._check_sensor_connection(self.SOIL_MOISTURE_PIN):
                print(f"❌ Soil moisture sensor not detected on GPIO {self.SOIL_MOISTURE_PIN}")
                return {
                    'error': f'Soil moisture sensor not connected. Check GPIO {self.SOIL_MOISTURE_PIN} connection.',
                    'status': 'disconnected',
                    'gpio_pin': self.SOIL_MOISTURE_PIN,
                    'sensor_mode': 'digital_do',
                    'timestamp': datetime.now().isoformat()
                }

            if GPIO_AVAILABLE:
                try:
                    # Read exact value from digital sensor (DO pin)
                    GPIO.setup(self.SOIL_MOISTURE_PIN, GPIO.IN)
                    sensor_value = GPIO.input(self.SOIL_MOISTURE_PIN)
                except Exception as gpio_runtime_error:
                    print(f"⚠️  RPi.GPIO runtime read failed: {gpio_runtime_error}")
                    if GPIOZERO_AVAILABLE:
                        try:
                            if self.soil_sensor_device is None:
                                self.soil_sensor_device = DigitalInputDevice(self.SOIL_MOISTURE_PIN)
                                print(f"✅ gpiozero DigitalInputDevice initialized on GPIO {self.SOIL_MOISTURE_PIN}")
                            sensor_value = 1 if self.soil_sensor_device.value else 0
                        except Exception as fallback_error:
                            print(f"⚠️  gpiozero fallback failed: {fallback_error}")
            elif GPIOZERO_AVAILABLE:
                try:
                    if self.soil_sensor_device is None:
                        self.soil_sensor_device = DigitalInputDevice(self.SOIL_MOISTURE_PIN)
                        print(f"✅ gpiozero DigitalInputDevice initialized on GPIO {self.SOIL_MOISTURE_PIN}")
                    # gpiozero returns bool-like value: True(1) / False(0)
                    sensor_value = 1 if self.soil_sensor_device.value else 0
                except Exception as fallback_error:
                    print(f"⚠️  gpiozero read failed: {fallback_error}")

            if sensor_value is None:
                return {
                    'error': 'GPIO backend unavailable. Unable to read actual sensor.',
                    'timestamp': datetime.now().isoformat()
                }

            # DO pin convention: LOW (0) = wet/moist, HIGH (1) = dry
            if sensor_value == 0:
                status = 'wet'
                state = 'WET'
                recommendation = 'Soil is moist. No watering needed now.'
                alert = False
            else:
                status = 'dry'
                state = 'DRY'
                recommendation = 'Soil is dry. Irrigation is needed.'
                alert = True

            print(f"🌱 Soil Moisture Sensor - GPIO {self.SOIL_MOISTURE_PIN}: raw={sensor_value}, state={state}")

            return {
                'value': int(sensor_value),
                'unit': 'DO',
                'status': status,
                'state': state,
                'raw_value': int(sensor_value),
                'gpio_pin': self.SOIL_MOISTURE_PIN,
                'sensor_mode': 'digital_do',
                'recommendation': recommendation,
                'alert': alert,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Error reading soil moisture: {str(e)}")
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def read_temperature_humidity(self) -> Dict:
        """Read temperature and humidity sensor (DHT22)"""
        try:
            dht_source = 'simulation'
            is_live = False

            if DHT_AVAILABLE:
                # Read from actual DHT sensor
                humidity, temperature = Adafruit_DHT.read_retry(self.DHT_SENSOR, self.DHT_PIN)
                
                if humidity is None or temperature is None:
                    # Sensor likely disconnected
                    return {
                        'error': 'DHT sensor not connected or failed to respond',
                        'status': 'disconnected',
                        'sensor': 'dht22',
                        'timestamp': datetime.now().isoformat()
                    }
                dht_source = f'adafruit_dht_gpio{self.DHT_PIN}'
                is_live = True
            elif DHT_CIRCUITPY_AVAILABLE:
                # Read using CircuitPython backend (recommended for newer Pi)
                if self.dht_device is None:
                    if self.DHT_PIN == 27:
                        dht_pin = blinka_pin.D27
                    elif self.DHT_PIN == 4:
                        dht_pin = blinka_pin.D4
                    else:
                        raise Exception(f"Unsupported DHT pin for CircuitPython backend: GPIO {self.DHT_PIN}")
                    self.dht_device = adafruit_dht.DHT22(dht_pin, use_pulseio=False)

                temperature = None
                humidity = None
                last_error = None
                for _ in range(3):
                    try:
                        temperature = self.dht_device.temperature
                        humidity = self.dht_device.humidity
                        if humidity is not None and temperature is not None:
                            break
                    except Exception as read_error:
                        last_error = read_error

                if humidity is None or temperature is None:
                    # no response from sensor
                    if last_error:
                        raise Exception(str(last_error))
                    return {
                        'error': 'DHT sensor not connected or failed to respond',
                        'status': 'disconnected',
                        'sensor': 'dht22',
                        'timestamp': datetime.now().isoformat()
                    }
                dht_source = f'live_dht22_gpio{self.DHT_PIN}'
                is_live = True
            else:
                # No library available
                if self.ALLOW_TH_SIMULATION:
                    temperature = random.uniform(22, 35)
                    humidity = random.uniform(40, 90)
                else:
                    return {
                        'error': 'Temperature/humidity library not installed; sensor unavailable',
                        'status': 'disconnected',
                        'sensor': 'dht22',
                        'timestamp': datetime.now().isoformat()
                    }
            
            # Determine temperature status
            if temperature < self.TEMP_THRESHOLDS['too_cold']:
                temp_status = 'too_cold'
                temp_recommendation = 'Temperature too cold for optimal growth.'
                temp_alert = True
            elif temperature > self.TEMP_THRESHOLDS['too_hot']:
                temp_status = 'too_hot'
                temp_recommendation = 'Temperature too hot! Provide shade.'
                temp_alert = True
            else:
                temp_status = 'optimal'
                temp_recommendation = 'Perfect temperature range.'
                temp_alert = False
            
            # Determine humidity status
            if humidity < self.HUMIDITY_THRESHOLDS['too_dry']:
                humidity_status = 'too_dry'
                humidity_recommendation = 'Air too dry. Increase humidity.'
                humidity_alert = True
            elif humidity > self.HUMIDITY_THRESHOLDS['too_humid']:
                humidity_status = 'too_humid'
                humidity_recommendation = 'Too humid! Improve ventilation.'
                humidity_alert = True
            else:
                humidity_status = 'optimal'
                humidity_recommendation = 'Perfect humidity level.'
                humidity_alert = False
            
            return {
                'temperature': {
                    'value': round(temperature, 1),
                    'unit': '°C',
                    'status': temp_status,
                    'recommendation': temp_recommendation,
                    'alert': temp_alert
                },
                'humidity': {
                    'value': round(humidity, 1),
                    'unit': '%',
                    'status': humidity_status,
                    'recommendation': humidity_recommendation,
                    'alert': humidity_alert
                },
                'sensor_source': dht_source,
                'sensor_live': is_live,
                'gpio_pin': self.DHT_PIN,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def _read_adc_channel(self, channel: int) -> int:
        """
        Read from ADC channel (placeholder for actual ADC implementation)
        You'll need to implement this based on your ADC setup (e.g., MCP3008)
        """
        # This is a simulation
        return random.randint(200, 900)
    
    def save_reading(self, sensor_type: str, data: Dict):
        """Save sensor reading to file"""
        try:
            filename = f"{sensor_type}_{datetime.now().strftime('%Y%m%d')}.json"
            filepath = os.path.join(self.data_folder, filename)
            
            # Load existing data
            readings = []
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    readings = json.load(f)
            
            # Append new reading
            readings.append(data)
            
            # Keep only last 1000 readings per day
            readings = readings[-1000:]
            
            # Save
            with open(filepath, 'w') as f:
                json.dump(readings, f, indent=2)
                
        except Exception as e:
            print(f"Error saving reading: {e}")
    
    def diagnose_soil_moisture_sensor(self) -> Dict:
        """
        Diagnostic function to test soil moisture sensor connectivity.
        Provides detailed information about GPIO access and sensor readings.
        """
        diagnosis = {
            'gpio_backend': 'unavailable',
            'gpio_pin': self.SOIL_MOISTURE_PIN,
            'sensor_mode': self.SOIL_SENSOR_MODE,
            'readings': [],
            'diagnosis': 'Unable to perform diagnosis',
            'recommendations': []
        }
        
        try:
            if not GPIO_AVAILABLE and not GPIOZERO_AVAILABLE:
                diagnosis['diagnosis'] = 'GPIO backend not available'
                diagnosis['recommendations'].append('Install RPi.GPIO or gpiozero package')
                return diagnosis
            
            diagnosis['gpio_backend'] = 'RPi.GPIO' if GPIO_AVAILABLE else 'gpiozero'
            
            # Try to read from the sensor multiple times
            successful_reads = 0
            for i in range(10):
                try:
                    if GPIO_AVAILABLE:
                        GPIO.setup(self.SOIL_MOISTURE_PIN, GPIO.IN)
                        value = GPIO.input(self.SOIL_MOISTURE_PIN)
                    else:
                        if self.soil_sensor_device is None:
                            self.soil_sensor_device = DigitalInputDevice(self.SOIL_MOISTURE_PIN)
                        value = 1 if self.soil_sensor_device.value else 0
                    
                    diagnosis['readings'].append({
                        'attempt': i + 1,
                        'value': value,
                        'interpretation': 'WET' if value == 0 else 'DRY'
                    })
                    successful_reads += 1
                except Exception as e:
                    diagnosis['readings'].append({
                        'attempt': i + 1,
                        'error': str(e)
                    })
            
            if successful_reads == 0:
                diagnosis['diagnosis'] = 'CRITICAL: Cannot access GPIO pin {self.SOIL_MOISTURE_PIN}'
                diagnosis['recommendations'] = [
                    'Check if GPIO pin is correctly configured',
                    'Verify Raspberry Pi GPIO is enabled',
                    'Check if pin is not in use by another process'
                ]
            elif successful_reads < 8:
                diagnosis['diagnosis'] = 'WARNING: Partial GPIO access (inconsistent reads)'
                diagnosis['recommendations'] = [
                    'Sensor may be disconnected or loose',
                    'Check pin and sensor wiring',
                    'Verify pull-up/pull-down resistor is installed'
                ]
            else:
                # All reads succeeded, check if values change or are static
                values = [r.get('value') for r in diagnosis['readings'] if 'value' in r]
                unique_values = set(values)
                
                if len(unique_values) == 1:
                    # All values are the same - could be normal or floating
                    diagnosis['diagnosis'] = 'OK: GPIO accessible, readings are stable'
                    wet_or_dry = 'WET' if values[0] == 0 else 'DRY'
                    diagnosis['recommendations'] = [
                        'Sensor appears to be connected and responsive',
                        f'Current reading is consistently {wet_or_dry}',
                        'If you suspect the reading is wrong, check the soil moisture'
                    ]
                else:
                    diagnosis['diagnosis'] = 'OK: GPIO accessible, readings are variable'
                    diagnosis['recommendations'] = [
                        'Sensor is connected and appears to be working',
                        f'Readings fluctuated between {list(unique_values)}',
                        'This is normal behavior for analog soil conditions'
                    ]
            
            return diagnosis
            
        except Exception as e:
            diagnosis['diagnosis'] = f'Error during diagnosis: {str(e)}'
            return diagnosis
    
    def get_readings(self, sensor_type: str, hours: int = 24) -> List[Dict]:
        """Get readings for the specified time period"""
        try:
            all_readings = []
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            # Get all relevant files (last few days)
            for i in range(hours // 24 + 2):
                date = datetime.now() - timedelta(days=i)
                filename = f"{sensor_type}_{date.strftime('%Y%m%d')}.json"
                filepath = os.path.join(self.data_folder, filename)
                
                if os.path.exists(filepath):
                    with open(filepath, 'r') as f:
                        readings = json.load(f)
                        # Filter by time
                        for reading in readings:
                            try:
                                reading_time = datetime.fromisoformat(reading['timestamp'])
                                if reading_time >= cutoff_time:
                                    if sensor_type == 'temp_humidity':
                                        has_values = 'temperature' in reading and 'humidity' in reading
                                        is_live = reading.get('sensor_live', False)
                                        if not (has_values and is_live):
                                            continue
                                    all_readings.append(reading)
                            except:
                                pass
            
            # Sort by timestamp
            all_readings.sort(key=lambda x: x['timestamp'])
            
            return all_readings
            
        except Exception as e:
            print(f"Error getting readings: {e}")
            return []
    
    def get_statistics(self, sensor_type: str, hours: int = 24) -> Dict:
        """Get statistics for sensor readings"""
        readings = self.get_readings(sensor_type, hours)
        
        if not readings:
            return {
                'count': 0,
                'error': 'No data available'
            }
        
        try:
            if sensor_type == 'soil_moisture':
                values = [r['value'] for r in readings if 'value' in r]
                alerts = sum(1 for r in readings if r.get('alert', False))
                dry_count = sum(1 for r in readings if r.get('status') == 'dry')
                wet_count = sum(1 for r in readings if r.get('status') == 'wet')
                if not values:
                    return {
                        'count': 0,
                        'error': 'No valid soil moisture values available'
                    }
                latest = next((r for r in reversed(readings) if 'value' in r), readings[-1])
                sensor_mode = latest.get('sensor_mode', 'unknown')
                
                return {
                    'count': len(readings),
                    'average': round(sum(values) / len(values), 2),
                    'min': round(min(values), 2),
                    'max': round(max(values), 2),
                    'alerts': alerts,
                    'dry_count': dry_count,
                    'wet_count': wet_count,
                    'sensor_mode': sensor_mode,
                    'latest': latest
                }
                
            elif sensor_type == 'temp_humidity':
                temps = [r['temperature']['value'] for r in readings if 'temperature' in r]
                humids = [r['humidity']['value'] for r in readings if 'humidity' in r]
                if not temps or not humids:
                    return {
                        'count': 0,
                        'error': 'No valid live temperature/humidity data available'
                    }
                temp_alerts = sum(1 for r in readings if r.get('temperature', {}).get('alert', False))
                humid_alerts = sum(1 for r in readings if r.get('humidity', {}).get('alert', False))
                
                return {
                    'count': len(temps),
                    'temperature': {
                        'average': round(sum(temps) / len(temps), 1),
                        'min': round(min(temps), 1),
                        'max': round(max(temps), 1),
                        'alerts': temp_alerts
                    },
                    'humidity': {
                        'average': round(sum(humids) / len(humids), 1),
                        'min': round(min(humids), 1),
                        'max': round(max(humids), 1),
                        'alerts': humid_alerts
                    },
                    'latest': readings[-1],
                    'sensor_source': readings[-1].get('sensor_source', 'unknown'),
                    'sensor_live': readings[-1].get('sensor_live', False),
                    'gpio_pin': readings[-1].get('gpio_pin')
                }
                
        except Exception as e:
            return {
                'error': str(e)
            }
    
    def get_fertilization_recommendations(self, hours: int = 24) -> Dict:
        """Get fertilization recommendations based on sensor data"""
        try:
            # Get sensor statistics
            soil_stats = self.get_statistics('soil_moisture', hours)
            temp_humid_stats = self.get_statistics('temp_humidity', hours)
            
            recommendations = {
                'priority': 'Medium',
                'conditions_analysis': {},
                'recommendations': [],
                'fertilizer_schedule': [],
                'warnings': []
            }
            
            # Analyze soil moisture
            if not soil_stats.get('error') and soil_stats.get('count', 0) > 0:
                if soil_stats.get('sensor_mode') == 'digital_do':
                    latest_state = soil_stats.get('latest', {}).get('state', 'UNKNOWN')
                    dry_ratio = (soil_stats.get('dry_count', 0) / soil_stats['count']) * 100
                    recommendations['conditions_analysis']['soil_moisture'] = {
                        'value': soil_stats.get('latest', {}).get('raw_value', 0),
                        'status': 'dry' if latest_state == 'DRY' else 'wet',
                        'state': latest_state,
                        'dry_ratio': round(dry_ratio, 2)
                    }

                    if latest_state == 'DRY':
                        recommendations['warnings'].append('Digital moisture sensor state is DRY. Water before fertilizing.')
                        recommendations['recommendations'].append('⚠️ Current state: DRY (DO=1). Irrigate before fertilizing.')
                    else:
                        recommendations['recommendations'].append('✅ Current state: WET (DO=0). Soil is moist enough for fertilizer.')
                else:
                    avg_moisture = soil_stats['average']
                    recommendations['conditions_analysis']['soil_moisture'] = {
                        'value': avg_moisture,
                        'status': 'dry' if avg_moisture < 40 else ('wet' if avg_moisture > 80 else 'optimal')
                    }
                    
                    if avg_moisture < 30:
                        recommendations['warnings'].append('Soil is very dry. Water before fertilizing to prevent root burn.')
                        recommendations['recommendations'].append('⚠️ Apply water first, then fertilize after 24 hours')
                    elif avg_moisture > 85:
                        recommendations['warnings'].append('Soil is waterlogged. Improve drainage before fertilizing.')
                        recommendations['recommendations'].append('⚠️ Delay fertilization until soil dries (60-70% moisture)')
                    else:
                        recommendations['recommendations'].append('✅ Soil moisture is good for fertilizer application')
            
            # Analyze temperature
            if not temp_humid_stats.get('error') and temp_humid_stats.get('count', 0) > 0:
                avg_temp = temp_humid_stats['temperature']['average']
                avg_humidity = temp_humid_stats['humidity']['average']
                
                recommendations['conditions_analysis']['temperature'] = {
                    'value': avg_temp,
                    'status': 'optimal' if 25 <= avg_temp <= 32 else ('cold' if avg_temp < 25 else 'hot')
                }
                recommendations['conditions_analysis']['humidity'] = {
                    'value': avg_humidity,
                    'status': 'optimal' if 60 <= avg_humidity <= 80 else ('dry' if avg_humidity < 60 else 'humid')
                }
                
                if avg_temp > 35:
                    recommendations['warnings'].append('Temperature is too high. Avoid fertilizing during extreme heat.')
                    recommendations['recommendations'].append('⚠️ Fertilize early morning (6-8 AM) or late afternoon (4-6 PM)')
                elif avg_temp < 18:
                    recommendations['warnings'].append('Temperature is too low. Nutrient uptake may be slow.')
                    recommendations['recommendations'].append('⚠️ Wait for warmer weather or use foliar application')
                else:
                    recommendations['recommendations'].append('✅ Temperature is ideal for fertilizer application')
                
                if avg_humidity > 90:
                    recommendations['warnings'].append('Very high humidity may increase disease risk.')
                    recommendations['recommendations'].append('⚠️ Use granular fertilizers, avoid foliar spray')
                elif avg_humidity < 40:
                    recommendations['recommendations'].append('💧 Low humidity - water well after fertilizing')
            
            # Determine fertilization schedule based on current conditions
            if not recommendations['warnings']:
                recommendations['priority'] = 'High'
                recommendations['fertilizer_schedule'] = [
                    {
                        'type': 'Balanced NPK (14-14-14)',
                        'amount': '60-70g per plant',
                        'method': 'Side dressing around base',
                        'timing': 'Best applied now - conditions are optimal',
                        'application_tips': [
                            'Apply 15-20cm away from plant base',
                            'Mix lightly with soil surface',
                            'Water thoroughly after application',
                            'Apply early morning for best results'
                        ]
                    },
                    {
                        'type': 'Foliar fertilizer (NPK + micronutrients)',
                        'amount': '2-3g per liter water',
                        'method': 'Spray on leaves',
                        'timing': 'Apply bi-weekly',
                        'application_tips': [
                            'Spray undersides of leaves',
                            'Apply when no rain expected for 4-6 hours',
                            'Early morning or late afternoon application',
                            'Use fine mist sprayer'
                        ]
                    }
                ]
            elif len(recommendations['warnings']) == 1:
                recommendations['priority'] = 'Medium'
                recommendations['fertilizer_schedule'] = [
                    {
                        'type': 'Adjust application based on warnings above',
                        'amount': '50g per plant (reduced)',
                        'method': 'Soil application only',
                        'timing': 'Wait for better conditions if possible',
                        'application_tips': [
                            'Monitor conditions closely',
                            'Apply when warnings are resolved',
                            'Use slow-release fertilizers'
                        ]
                    }
                ]
            else:
                recommendations['priority'] = 'Low'
                recommendations['fertilizer_schedule'] = [
                    {
                        'type': 'Hold fertilization',
                        'amount': 'N/A',
                        'method': 'N/A',
                        'timing': 'Wait until conditions improve',
                        'application_tips': [
                            'Resolve environmental issues first',
                            'Focus on water management',
                            'Check again in 2-3 days'
                        ]
                    }
                ]
            
            # General recommendations
            recommendations['general_guidelines'] = [
                '🌱 Young plants (1-6 months): High nitrogen (20-10-10)',
                '🌸 Pre-flowering (7-10 months): Balanced NPK (14-14-14)',
                '🍍 Fruiting stage (11-18 months): High potassium (10-10-30)',
                '📅 Apply every 6-8 weeks during active growth',
                '💧 Always water before and after fertilizing',
                '🌤️ Avoid application before heavy rain',
                '🔬 Soil test every 6 months for optimal feeding'
            ]
            
            # Micronutrient recommendations
            recommendations['micronutrients'] = {
                'essential': ['Iron', 'Zinc', 'Manganese', 'Boron', 'Copper'],
                'application': 'Foliar spray or chelated soil application',
                'frequency': 'Every 2-3 months or when deficiency symptoms appear',
                'signs_of_deficiency': {
                    'Iron': 'Young leaves turn yellow, veins remain green',
                    'Zinc': 'Small, narrow leaves; stunted growth',
                    'Manganese': 'Yellowing between leaf veins',
                    'Boron': 'Brittle leaves, poor fruit development',
                    'Copper': 'Wilting, leaf burn on tips'
                }
            }
            
            # Organic alternatives
            recommendations['organic_options'] = [
                {
                    'type': 'Compost',
                    'amount': '2-3 kg per plant',
                    'frequency': 'Every 3 months',
                    'benefits': 'Improves soil structure and water retention'
                },
                {
                    'type': 'Vermicast',
                    'amount': '1 kg per plant',
                    'frequency': 'Monthly',
                    'benefits': 'Rich in beneficial microorganisms'
                },
                {
                    'type': 'Chicken manure (composted)',
                    'amount': '500g per plant',
                    'frequency': 'Every 2-3 months',
                    'benefits': 'High nitrogen content, slow release'
                },
                {
                    'type': 'Seaweed extract',
                    'amount': '50ml per liter (diluted)',
                    'frequency': 'Bi-weekly foliar spray',
                    'benefits': 'Growth hormones and trace minerals'
                }
            ]
            
            return recommendations
            
        except Exception as e:
            return {
                'error': str(e),
                'priority': 'Unknown',
                'recommendations': ['Unable to generate recommendations']
            }
    
    def cleanup(self):
        """Cleanup GPIO resources"""
        if GPIO_AVAILABLE:
            GPIO.cleanup()

    # ===== Notification helpers =====
    def _repo_root(self) -> str:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    def _load_users(self) -> Dict:
        try:
            path = os.path.join(self._repo_root(), 'users.json')
            if not os.path.exists(path):
                return {}
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            return {}

    def _load_notifications(self) -> Dict:
        try:
            path = os.path.join(self._repo_root(), 'notifications.json')
            if not os.path.exists(path):
                return {}
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_notifications(self, data: Dict):
        try:
            path = os.path.join(self._repo_root(), 'notifications.json')
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"⚠️  Failed to save notifications file: {e}")

    def _get_notification_message(self, dry_days: int) -> str:
        """Get SMS message template from env or return default message.

        Environment variable: SOIL_DRY_NOTIFICATION_MESSAGE
        Placeholder: {dry_days} will be substituted with the number of days.
        """
        default_msg = (
            "SYSTEM ALERT: Soil moisture critically low. Ang pinya ay nakaranas ng {dry_days} araw na dryness. "
            "I-activate na ang irrigation system."
        )
        template = os.getenv('SOIL_DRY_NOTIFICATION_MESSAGE', default_msg)
        return template.format(dry_days=dry_days)

    def check_and_notify_all_users(self, dry_days: int = 3) -> None:
        """Check last `dry_days` calendar days and notify registered users via EMAIL

        For each user with an `email` field in `users.json`, if there is at least
        one `dry` soil_moisture reading on each of the last `dry_days` calendar
        days, send an EMAIL (once per day) informing the owner to water the plant.
        """
        users = self._load_users()
        if not users:
            return

        notifications = self._load_notifications()

        for email, profile in users.items():
            # Determine consecutive dry days
            today = datetime.now().date()
            consecutive = 0
            for d in range(dry_days):
                day = today - timedelta(days=d)
                filename = f"soil_moisture_{day.strftime('%Y%m%d')}.json"
                filepath = os.path.join(self.data_folder, filename)
                if not os.path.exists(filepath):
                    # No data for the day -> treat as not dry
                    break
                try:
                    with open(filepath, 'r') as f:
                        readings = json.load(f)
                    # If any reading that day is dry -> count the day
                    day_has_dry = any((r.get('status') == 'dry' or r.get('state') == 'DRY') for r in readings)
                    if day_has_dry:
                        consecutive += 1
                    else:
                        break
                except Exception:
                    break

            if consecutive >= dry_days:
                # Only notify once per calendar day per user
                last = notifications.get(email, {}).get('last_notified')
                last_notified_date = None
                if last:
                    try:
                        last_notified_date = datetime.fromisoformat(last).date()
                    except Exception:
                        last_notified_date = None

                if last_notified_date == today:
                    # already notified today
                    continue

                # Get message and send email
                message = self._get_notification_message(dry_days)
                fullname = profile.get('fullname', 'User')
                
                success = send_email_notification(email, fullname, message)
                if success:
                    notifications.setdefault(email, {})['last_notified'] = datetime.now().isoformat()
                    self._save_notifications(notifications)


# Create global sensor monitor instance
sensor_monitor = SensorMonitor()
