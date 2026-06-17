# Home Assistant Integration Technical Specification

This document provides the extreme technical detail for the Home Assistant integration of the iCharger MPPT 48100 solar polling service.

## 1. Architecture Overview
The system utilizes a Python-based polling service running on a remote node (Copernicus, 10.1.3.13) which exposes real-time solar metrics via a REST API. Home Assistant (on `shelae`, 10.1.3.11) ingests this data, processes it through template sensors, tracks energy usage with utility meters, and visualizes it via a custom Lovelace dashboard.

## 2. Data Ingestion (REST API)
Home Assistant polls the Copernicus API every 20 seconds.

* **Resource:** `http://10.1.3.13:8081/api/v1/latest`
* **Header:** `X-API-Key: supersecretkey`
* **Entity:** `sensor.icharger_mppt_raw_data`
* **Attributes:** `system_v`, `status_code`, `batt_v`, `charge_a`, `charge_w`, `total_energy_wh`, `pv_v`, `temp_f`

## 3. Template Sensors
All template sensors are defined in `configuration.yaml` under the `template` block.

### 3.1. Battery State of Charge (SoC) Calculation
The `sensor.icharger_battery_soc` calculates the SoC for a 16S 48V LiFePO4 battery based on voltage.

```jinja
{% set v = states('sensor.icharger_battery_voltage') | float(-1) %}
{% if v < 0 %}
  unknown
{% elif v >= 54.0 %}
  100
{% elif v >= 53.2 %}
  {{ (90 + (v - 53.2) / (54.0 - 53.2) * 10) | round(0) }}
{% elif v >= 52.8 %}
  {{ (70 + (v - 52.8) / (53.2 - 52.8) * 20) | round(0) }}
{% elif v >= 52.4 %}
  {{ (40 + (v - 52.4) / (52.8 - 52.4) * 30) | round(0) }}
{% elif v >= 52.0 %}
  {{ (20 + (v - 52.0) / (52.4 - 52.0) * 20) | round(0) }}
{% elif v >= 51.2 %}
  {{ (10 + (v - 51.2) / (52.0 - 51.2) * 10) | round(0) }}
{% elif v >= 48.0 %}
  {{ ((v - 48.0) / (51.2 - 48.0) * 10) | round(0) }}
{% else %}
  0
{% endif %}
```

### 3.2. Energy Generation Tracking
* `sensor.green_energy_generated_today`: Tracks daily solar generation in kWh.
* `sensor.green_energy_generated_this_month`: Tracks monthly solar generation in kWh.

## 4. Utility Meters
Defined in `utility_meter.yaml`, these track cumulative energy yield from `sensor.icharger_total_energy` (kWh).

* `icharger_solar_energy_daily`: Resets daily.
* `icharger_solar_energy_weekly`: Resets weekly.
* `icharger_solar_energy_monthly`: Resets monthly (offset: 20 days).

## 5. Automations
Defined in `automations.yaml`.

| Automation ID | Trigger | Action |
| :--- | :--- | :--- |
| `icharger_controller_fault_alert` | `sensor.icharger_status` -> 'Fault' | Persistent Notification |
| `icharger_excess_solar_load_trigger` | `sensor.icharger_charge_power` > 2200W (5m) | Turn on `switch.living_room_smart_plug` |
| `icharger_excess_solar_load_trigger` | `sensor.icharger_charge_power` < 300W (10m) | Turn off `switch.living_room_smart_plug` |
| `icharger_low_battery_voltage_warning` | `sensor.icharger_battery_voltage` < 48.0V (10m) | Persistent Notification |

## 6. Dashboard Styling
The dashboard utilizes `card_mod` for glassmorphism styling across all custom cards (ApexCharts, Mushroom, etc.).

* **Key CSS Properties:**
  * `background: rgba(0, 0, 0, 0.85)`
  * `backdrop-filter: blur(25px)`
  * `border-left: 10px solid [Color]`
  * `box-shadow: 0 0 15px rgba([Color], 0.15)`

## 7. Data Retention
Home Assistant stores state data in `/homeassistant/home-assistant_v2.db` (SQLite). 
* **Detailed History:** 10 days (configurable in `recorder`).
* **Long-Term Statistics:** Infinite retention for sensors with `state_class` (measurement or total_increasing).
