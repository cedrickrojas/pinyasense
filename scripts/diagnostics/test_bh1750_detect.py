#!/usr/bin/env python3
"""
Test if BH1750 light sensor is detected on Raspberry Pi I2C bus.
"""
import sys

def detect_bh1750():
    """
    Try to detect BH1750 light sensor on I2C bus 1.
    Returns: (detected: bool, message: str)
    """
    try:
        from smbus2 import SMBus
    except ImportError:
        return False, "smbus2 not installed. Run: sudo pip3 install smbus2"
    
    BUS = 1
    ADDR = 0x23
    
    try:
        with SMBus(BUS) as bus:
            # Try to read from the sensor address
            try:
                data = bus.read_byte(ADDR)
                return True, f"✓ BH1750 DETECTED at address 0x{ADDR:02x}"
            except OSError as e:
                if "Remote I/O error" in str(e) or e.errno == 121:
                    # Device not responding (common if not powered or wired yet)
                    return False, f"✗ No response from address 0x{ADDR:02x} - check wiring/power"
                raise
    except PermissionError:
        return False, "✗ Permission denied. Run with: sudo python3 -m scripts.diagnostics.test_bh1750_detect"
    except FileNotFoundError:
        return False, "✗ I2C bus not found. Enable I2C in raspi-config"
    except Exception as e:
        return False, f"✗ Error: {e}"

def main():
    detected, msg = detect_bh1750()
    print(msg)
    
    if detected:
        print("\n✓ Sensor is ready to use!")
        print("  Run: python3 -m scripts.diagnostics.bh1750_test")
        return 0
    else:
        print("\n✗ No source available")
        return 1

if __name__ == '__main__':
    sys.exit(main())
