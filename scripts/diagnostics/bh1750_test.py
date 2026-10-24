from smbus2 import SMBus
import time

# BH1750 test reader for Raspberry Pi (I2C bus 1)
BUS = 1
ADDR = 0x23

def read_lux():
    with SMBus(BUS) as bus:
        # power on
        bus.write_byte(ADDR, 0x01)
        # continuous high-res mode
        bus.write_byte(ADDR, 0x10)
        time.sleep(0.18)
        data = bus.read_i2c_block_data(ADDR, 0x00, 2)
        raw = (data[0] << 8) | data[1]
        lux = raw / 1.2
        return lux

if __name__ == '__main__':
    try:
        while True:
            try:
                lux = read_lux()
                print(f"Lux: {lux:.2f}")
            except Exception as e:
                print('Sensor read error:', e)
            time.sleep(1)
    except KeyboardInterrupt:
        print('Stopped')
