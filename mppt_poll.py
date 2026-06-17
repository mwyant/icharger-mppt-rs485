#!/usr/bin/env python3
import serial
import time
import sys
import json
import os
from datetime import datetime

# Modbus RTU CRC16
def crc16(data):
    crc = 0xFFFF
    for pos in data:
        crc ^= pos
        for _ in range(8):
            if (crc & 1) != 0:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc.to_bytes(2, byteorder='little')

def read_registers(ser, slave_id, start_address, count):
    req = bytearray([slave_id, 3])
    req.extend(start_address.to_bytes(2, byteorder='big'))
    req.extend(count.to_bytes(2, byteorder='big'))
    req.extend(crc16(req))
    
    ser.reset_input_buffer()
    ser.write(req)
    ser.flush()
    
    # Wait for response
    time.sleep(0.15)
    
    in_waiting = ser.in_waiting
    if in_waiting > 0:
        resp = ser.read(in_waiting)
        if len(resp) >= 5:
            calc_crc = crc16(resp[:-2])
            if resp[-2:] == calc_crc:
                return resp[3:-2]
    return None

def main():
    port = '/dev/ttyUSB0'
    baud = 9600
    slave_id = 1
    
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=1.0
        )
    except Exception as e:
        print(f"Error opening serial port {port}: {e}", file=sys.stderr)
        sys.exit(1)
        
    print(f"Connected to iCharger MPPT on {port} at {baud} baud.")
    print("Press Ctrl+C to stop polling.\n")
    
    try:
        while True:
            data = read_registers(ser, slave_id, 0x0100, 16)
            if data:
                timestamp = datetime.now().isoformat()
                
                # Parse registers
                sys_voltage = int.from_bytes(data[0:2], byteorder='big')
                status_code = int.from_bytes(data[2:4], byteorder='big')
                batt_voltage = int.from_bytes(data[4:6], byteorder='big') * 0.1
                charge_current = int.from_bytes(data[6:8], byteorder='big') * 0.01
                charge_power = int.from_bytes(data[8:10], byteorder='big')
                
                # Energy registers (0x0105 and 0x0106 might be 32-bit total energy)
                energy_high = int.from_bytes(data[10:12], byteorder='big')
                energy_low = int.from_bytes(data[12:14], byteorder='big')
                total_energy = (energy_high << 16) | energy_low
                
                pv_voltage = int.from_bytes(data[18:20], byteorder='big') * 0.1
                
                # Temperature (0x010F is at byte offset 30)
                temp_raw = int.from_bytes(data[30:32], byteorder='big')
                
                # Format output
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
                print(f"  System Voltage:      {sys_voltage} V")
                print(f"  Status Code:         {status_code}")
                print(f"  Battery Voltage:     {batt_voltage:.2f} V")
                print(f"  Charging Current:    {charge_current:.2f} A")
                print(f"  Charging Power:      {charge_power} W")
                print(f"  PV Input Voltage:    {pv_voltage:.2f} V")
                print(f"  Controller Temp:     {temp_raw} °F")
                print(f"  Total Energy:        {total_energy} Wh")
                print("-" * 40)
                
                # Save to live status file
                status = {
                    "timestamp": timestamp,
                    "system_voltage": sys_voltage,
                    "status_code": status_code,
                    "battery_voltage": batt_voltage,
                    "charging_current": charge_current,
                    "charging_power": charge_power,
                    "pv_voltage": pv_voltage,
                    "temperature_f": temp_raw,
                    "total_energy_wh": total_energy
                }
                
                try:
                    with open('/home/izzy_ai/mppt_status.json', 'w') as f:
                        json.dump(status, f, indent=2)
                except Exception as e:
                    print(f"Error writing status file: {e}", file=sys.stderr)
            else:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Failed to poll controller.")
                
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("\nPolling stopped by user.")
    finally:
        ser.close()

if __name__ == '__main__':
    main()
