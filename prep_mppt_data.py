import sqlite3
import json
import os
from datetime import datetime

DB_PATH = '/home/izzy_ai/rs485-mppt-monitor/data/mppt_metrics.db'
OUTPUT_PATH = '/home/izzy_ai/mppt_summary.json'

def calculate_custom_soc(v):
    if v is None or v < 0:
        return 0.0
    elif v >= 54.0:
        return 100.0
    elif v >= 53.2:
        return round(90.0 + (v - 53.2) / (54.0 - 53.2) * 10.0, 1)
    elif v >= 52.8:
        return round(70.0 + (v - 52.8) / (53.2 - 52.8) * 20.0, 1)
    elif v >= 52.4:
        return round(40.0 + (v - 52.4) / (52.8 - 52.4) * 30.0, 1)
    elif v >= 52.0:
        return round(20.0 + (v - 52.0) / (52.4 - 52.0) * 20.0, 1)
    elif v >= 51.2:
        return round(10.0 + (v - 51.2) / (52.0 - 51.2) * 10.0, 1)
    elif v >= 48.0:
        return round((v - 48.0) / (51.2 - 48.0) * 10.0, 1)
    else:
        return 0.0

def main():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Overall metadata
    cursor.execute("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM metrics")
    total_rows, min_time, max_t = cursor.fetchone()
    print(f"Processing {total_rows} rows from {min_time} to {max_t}...")

    # 2. Daily Summaries
    cursor.execute("""
        SELECT strftime('%Y-%m-%d', timestamp) as day,
               MIN(batt_v) as min_batt_v,
               MAX(batt_v) as max_batt_v,
               AVG(batt_v) as avg_batt_v,
               MAX(charge_w) as max_charge_w,
               AVG(charge_w) as avg_charge_w,
               MAX(charge_a) as max_charge_a,
               MIN(temp_f) as min_temp_f,
               MAX(temp_f) as max_temp_f,
               AVG(temp_f) as avg_temp_f,
               MIN(status_code) as min_internal_soc,
               MAX(status_code) as max_internal_soc,
               AVG(status_code) as avg_internal_soc,
               MIN(total_energy_wh) as min_energy,
               MAX(total_energy_wh) as max_energy
        FROM metrics
        GROUP BY day
        ORDER BY day
    """)
    daily_rows = cursor.fetchall()
    daily_summaries = []
    for row in daily_rows:
        day = row['day']
        # Find the exact timestamp of peak power for this day
        cursor.execute("SELECT timestamp FROM metrics WHERE strftime('%Y-%m-%d', timestamp) = ? AND charge_w = ? LIMIT 1", (day, row['max_charge_w']))
        peak_row = cursor.fetchone()
        peak_time = peak_row['timestamp'] if peak_row else "Unknown"

        gen_wh = row['max_energy'] - row['min_energy'] if row['max_energy'] is not None and row['min_energy'] is not None else 0

        daily_summaries.append({
            "day": day,
            "battery_voltage": {
                "min": row['min_batt_v'],
                "max": row['max_batt_v'],
                "avg": round(row['avg_batt_v'], 2)
            },
            "charging_power": {
                "max": row['max_charge_w'],
                "avg": round(row['avg_charge_w'], 2),
                "peak_time": peak_time
            },
            "max_charging_current_a": row['max_charge_a'],
            "temperature_f": {
                "min": row['min_temp_f'],
                "max": row['max_temp_f'],
                "avg": round(row['avg_temp_f'], 2)
            },
            "internal_soc_percent": {
                "min": row['min_internal_soc'],
                "max": row['max_internal_soc'],
                "avg": round(row['avg_internal_soc'], 1)
            },
            "energy_generated_wh": gen_wh,
            "energy_generated_kwh": round(gen_wh / 1000.0, 2)
        })

    # 3. Hourly Summaries (for detailed trend analysis)
    cursor.execute("""
        SELECT strftime('%Y-%m-%d %H:00:00', timestamp) as hour_bucket,
               AVG(batt_v) as avg_batt_v,
               AVG(charge_w) as avg_charge_w,
               AVG(pv_v) as avg_pv_v,
               AVG(temp_f) as avg_temp_f,
               AVG(status_code) as avg_internal_soc,
               MAX(total_energy_wh) - MIN(total_energy_wh) as gen_wh
        FROM metrics
        GROUP BY hour_bucket
        ORDER BY hour_bucket
    """)
    hourly_rows = cursor.fetchall()
    hourly_summaries = []
    for row in hourly_rows:
        hourly_summaries.append({
            "hour": row['hour_bucket'],
            "avg_batt_v": round(row['avg_batt_v'], 2) if row['avg_batt_v'] else 0,
            "avg_charge_w": round(row['avg_charge_w'], 2) if row['avg_charge_w'] else 0,
            "avg_pv_v": round(row['avg_pv_v'], 2) if row['avg_pv_v'] else 0,
            "avg_temp_f": round(row['avg_temp_f'], 2) if row['avg_temp_f'] else 0,
            "avg_internal_soc": round(row['avg_internal_soc'], 1) if row['avg_internal_soc'] else 0,
            "energy_gen_wh": row['gen_wh'] if row['gen_wh'] else 0
        })

    # 4. SoC Comparison and Calibration Audit
    # Let's sample records to see how the internal SoC compares to our custom SoC
    cursor.execute("SELECT timestamp, batt_v, status_code FROM metrics WHERE status_code IS NOT NULL AND batt_v IS NOT NULL")
    all_soc_records = cursor.fetchall()
    
    soc_diffs = []
    custom_soc_distribution = {}
    internal_soc_distribution = {}
    
    for r in all_soc_records:
        v = r['batt_v']
        internal_soc = r['status_code']
        custom_soc = calculate_custom_soc(v)
        diff = internal_soc - custom_soc
        soc_diffs.append(diff)
        
        # Distribution buckets
        int_bucket = int(internal_soc // 10 * 10)
        cust_bucket = int(custom_soc // 10 * 10)
        internal_soc_distribution[int_bucket] = internal_soc_distribution.get(int_bucket, 0) + 1
        custom_soc_distribution[cust_bucket] = custom_soc_distribution.get(cust_bucket, 0) + 1

    avg_diff = sum(soc_diffs) / len(soc_diffs) if soc_diffs else 0
    max_diff = max(soc_diffs, key=abs) if soc_diffs else 0

    soc_audit = {
        "avg_difference_percent": round(avg_diff, 2),
        "max_difference_percent": round(max_diff, 2),
        "internal_soc_distribution": {f"{k}-{k+9}%": v for k, v in sorted(internal_soc_distribution.items())},
        "custom_soc_distribution": {f"{k}-{k+9}%": v for k, v in sorted(custom_soc_distribution.items())}
    }

    # 5. Anomalies & Events
    anomalies = {
        "failed_polls_gaps": [],
        "low_voltage_events": [],
        "high_temp_events": [],
        "sudden_voltage_drops": []
    }

    # Detect gaps in polling (interval is 5s, so gap > 15s is a failed poll)
    cursor.execute("SELECT timestamp FROM metrics ORDER BY timestamp ASC")
    timestamps = [datetime.fromisoformat(r['timestamp']) for r in cursor.fetchall()]
    
    for i in range(1, len(timestamps)):
        diff_sec = (timestamps[i] - timestamps[i-1]).total_seconds()
        if diff_sec > 15.0:
            anomalies["failed_polls_gaps"].append({
                "start": timestamps[i-1].isoformat(),
                "end": timestamps[i].isoformat(),
                "duration_seconds": round(diff_sec, 1)
            })

    # Detect low voltage events (< 48.0V)
    cursor.execute("SELECT timestamp, batt_v FROM metrics WHERE batt_v < 48.0 ORDER BY timestamp ASC")
    low_v_rows = cursor.fetchall()
    for r in low_v_rows:
        anomalies["low_voltage_events"].append({
            "timestamp": r['timestamp'],
            "voltage": r['batt_v']
        })

    # Detect high temperature events (> 110F)
    cursor.execute("SELECT timestamp, temp_f, charge_w FROM metrics WHERE temp_f > 110 ORDER BY timestamp ASC")
    high_t_rows = cursor.fetchall()
    for r in high_t_rows:
        anomalies["high_temp_events"].append({
            "timestamp": r['timestamp'],
            "temp_f": r['temp_f'],
            "charge_w": r['charge_w']
        })

    # Detect sudden voltage drops (> 1.0V drop in 10 seconds)
    # We can query records and compare consecutive ones
    cursor.execute("SELECT timestamp, batt_v FROM metrics ORDER BY timestamp ASC")
    v_records = cursor.fetchall()
    for i in range(2, len(v_records)):
        v_prev = v_records[i-2]['batt_v']
        v_curr = v_records[i]['batt_v']
        if v_prev is not None and v_curr is not None:
            drop = v_prev - v_curr
            if drop > 1.0:
                anomalies["sudden_voltage_drops"].append({
                    "timestamp": v_records[i]['timestamp'],
                    "voltage_before": v_prev,
                    "voltage_after": v_curr,
                    "drop": round(drop, 2)
                })

    # Limit anomalies count to keep JSON small
    anomalies["failed_polls_gaps"] = anomalies["failed_polls_gaps"][:20]  # top 20
    anomalies["low_voltage_events"] = anomalies["low_voltage_events"][:20]
    anomalies["high_temp_events"] = anomalies["high_temp_events"][:20]
    anomalies["sudden_voltage_drops"] = anomalies["sudden_voltage_drops"][:20]

    # Assemble summary
    summary = {
        "metadata": {
            "total_records": total_rows,
            "start_time": min_time,
            "end_time": max_t,
            "battery_capacity_ah": 300,
            "battery_capacity_kwh": 15.36,
            "battery_chemistry": "16S LiFePO4"
        },
        "daily_summaries": daily_summaries,
        "soc_audit": soc_audit,
        "anomalies": anomalies,
        "hourly_trends_sample": hourly_summaries[::4] # Sample every 4 hours to keep the JSON extremely compact (under 5KB)
    }

    with open(OUTPUT_PATH, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"Successfully generated summary JSON at {OUTPUT_PATH}")
    conn.close()

if __name__ == '__main__':
    main()
