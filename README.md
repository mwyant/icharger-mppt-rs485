# iCharger MPPT RS485 Modbus Protocol

This repository contains the reverse-engineered Modbus RTU register map and Python scripts for the **EASUN iCharger MPPT 48100** (and compatible models like 4860, 8048).

Since official documentation for the RS485 port on these units is virtually non-existent, this project serves as the definitive community resource for polling real-time solar metrics.

## Hardware Setup

### 1. RS485 Adapter
Use a high-quality USB-to-RS485 adapter (Industrial FTDI-based recommended). 
* **A+ (D+)**: Connect to the controller's A+ terminal.
* **B- (D-)**: Connect to the controller's B- terminal.
* **GND**: Optional, but avoid chassis ground loops.

### 2. Serial Parameters
* **Baud Rate**: 9600
* **Data Bits**: 8
* **Stop Bits**: 1
* **Parity**: None (8N1)
* **Slave ID**: 1 (Default)

## Modbus Register Map (Function Code 03)

| Register (Hex) | Register (Dec) | Description | Scaling | Unit |
|----------------|----------------|-------------|---------|------|
| `0x0100` | 256 | System Voltage | 1 | V |
| `0x0101` | 257 | Status Code | 1 | - |
| `0x0102` | 258 | Battery Voltage | 0.1 | V |
| `0x0103` | 259 | Charging Current | 0.01 | A |
| `0x0104` | 260 | Charging Power | 1 | W |
| `0x0105` | 261 | Energy Generated (Low Word) | 1 | Wh |
| `0x0106` | 262 | Energy Generated (High Word) | 1 | Wh |
| `0x0109` | 265 | PV Input Voltage | 0.1 | V |
| `0x010F` | 271 | Controller Temperature | 1 | °F |

## Usage

Ensure you have `pyserial` installed:
```bash
pip install pyserial
```

Run the provided `mppt_poll.py` script to see live data.

## Home Assistant Integration

For details on integrating this data into Home Assistant, see [docs/HA_INTEGRATION.md](docs/HA_INTEGRATION.md).

---

## Disclaimer

**Vibe Coded with ❤️.** 

This project is the result of reverse-engineering and experimental "vibe coding." It is provided "as is" without any warranty of any kind, express or implied. The authors and contributors are not liable for any damage to your hardware, data loss, or any other issues arising from the use of this information or the provided scripts. 

**Use at your own risk.** Always verify your wiring and parameters before connecting to high-voltage solar equipment.
