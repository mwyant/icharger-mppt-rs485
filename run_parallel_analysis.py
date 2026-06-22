import json
import subprocess
import concurrent.futures
import os
import sys

SUMMARY_PATH = 'mppt_summary.json'

# Define the system context that all threads must share to avoid flying off the rails
SYSTEM_CONTEXT = """
You are Izzy, an expert solar and battery storage systems engineer.
You are analyzing a 4.5-day dataset of an EASUN iCharger MPPT 48100 solar charge controller.

PHYSICAL SYSTEM CONTEXT:
- Battery Bank: 4x 12.8V 300Ah LiFePO4 batteries in series (nominal 51.2V, 300Ah capacity, 15.36 kWh total storage).
- Load Profile: Inverter runs a 120V system. The Living Room Smart Plug is a direct load off the inverter.
  All other loads are monitored by an Off-Grid Emporia Vue system wired off the inverter's 60A breaker.
- Temperature Physics: The controller temperature sensor measures the INTERNAL heatsink/power stage temperature,
  NOT the ambient outdoor temperature. Under high charging power (up to 3kW), the internal components naturally heat up.
  An internal heatsink temperature of 95-99°F (35-37°C) under a 3kW load is extremely cool and indicates high efficiency.
- Register 0x0101 Discovery: We have discovered that register 0x0101 (previously labeled "Status Code") is actually
  the controller's internal calculated Battery State of Charge (SoC) percentage (ranging from 20 to 100).
"""

PROMPTS = {
    "solar_generation": """
DOMAIN: Solar Generation & Efficiency Analysis

DATA FOR ANALYSIS:
{daily_summaries}

YOUR TASK:
1. Analyze the daily solar generation trend (from June 18 to June 22). Note that June 22 is a partial day (ends at 15:55).
2. Calculate the total energy generated over this period and the average daily yield (excluding the partial day).
3. Evaluate the peak charging power (which reached 3,097W on June 20). Is this pushing the limits of the solar array or the controller?
   (Note: The controller is rated for 60A charge current. At ~53V, 60A is ~3,180W).
4. Analyze the peak times. They seem to occur late in the afternoon (16:30 to 18:00). What does this suggest about the solar panel orientation (e.g., West-facing)?
5. Provide actionable engineering recommendations to optimize solar yield.
""",

    "battery_health": """
DOMAIN: Battery Health & SoC Calibration Audit

DATA FOR ANALYSIS:
{daily_summaries}
{soc_audit}

YOUR TASK:
1. Analyze the battery voltage swings. The nominal voltage is 51.2V. The max voltage reached 54.5V (June 21). Is this a safe absorption voltage for a 16S LiFePO4 bank?
   (Note: 16S LiFePO4 absorption is typically 54.0V - 54.4V, or 3.375V - 3.4V per cell).
2. Perform a calibration audit of the controller's internal SoC (register 0x0101) vs our custom voltage-based SoC.
   The average difference is 15.65%, and the internal SoC is heavily clustered in the 80-89% range (52,817 records), whereas our custom SoC is much more distributed.
   Why is the controller's internal SoC so flat and conservative? How does LiFePO4's flat voltage curve affect this?
3. Evaluate the battery's state of charge over the 4.5 days. Did the bank get fully charged? Did it discharge deeply?
4. Provide recommendations for calibrating the SoC in Home Assistant. Should we rely on the controller's internal SoC, our custom voltage curve, or a hybrid approach?
""",

    "thermal_load": """
DOMAIN: Thermal & Load Management Analysis

DATA FOR ANALYSIS:
{daily_summaries}
{hourly_trends_sample}

YOUR TASK:
1. Correlate the controller's internal temperature with the charging power.
   The max temperature reached 99°F (37.2°C) on June 22, while the average temperature stayed around 95-98°F.
   Explain why the heatsink temperature is so stable and cool, even when converting nearly 3,000W of power.
2. Evaluate the effectiveness of the "iCharger Excess Solar Load Trigger" automation:
   - Trigger ON: Charging Power > 2200W for 5 minutes.
   - Trigger OFF: Charging Power < 300W for 10 minutes.
   Looking at the hourly trends, how often and during what hours would this trigger?
3. Does the 2200W trigger point make sense given the daily peak powers (2703W, 2797W, 3097W, 2634W)?
4. Provide recommendations for optimizing the load-shedding automation to maximize self-consumption of solar energy.
""",

    "anomalies_stability": """
DOMAIN: Operational Anomalies & Communication Stability

DATA FOR ANALYSIS:
{anomalies}

YOUR TASK:
1. Analyze the "low voltage events" where the battery voltage suddenly dropped to 1.6V, 1.9V, or 2.9V.
   Explain why these are clearly communication/Modbus polling glitches rather than actual battery drops.
   (Hint: A 16S LiFePO4 bank dropping to 1.6V would mean 0.1V per cell, which is physically impossible without catastrophic explosion/destruction, and it recovered to 53V instantly).
2. Analyze the "sudden voltage drops" (e.g., 53.1V to 1.9V, or 57.1V to 53.8V).
   Are these drops of 1.1V to 3.3V actual load-induced voltage sags, or are they also part of the serial noise/polling offset issue?
3. Evaluate the "failed polls/gaps" (only 2 gaps of 15.6 seconds over 4.5 days).
   How stable is the RS485-to-USB connection on Copernicus? Is this an acceptable error rate?
4. Provide engineering recommendations to harden the polling script (`poller.py` or `mppt_poll.py`) against these glitches.
   (e.g., filtering out voltage readings < 40V, adding retry logic, or checking packet length).
"""
}

def run_local_query(domain, prompt_content):
    print(f"[Thread - {domain}] Starting local LLM analysis...")
    
    # Write prompt to a temp file to avoid Windows command line character limits
    temp_prompt_file = f"temp_prompt_{domain}.txt"
    full_prompt = f"{SYSTEM_CONTEXT}\n\n{prompt_content}"
    
    with open(temp_prompt_file, 'w', encoding='utf-8') as f:
        f.write(full_prompt)
        
    try:
        # Call local-llm-query.bat using the temporary prompt file
        cmd = ['local-llm-query.bat', '--model', 'heavy', '--prompt-file', temp_prompt_file, '--temperature', '0.2']
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', shell=True)
        
        if result.returncode != 0:
            print(f"[Thread - {domain}] Error running local query: {result.stderr}", file=sys.stderr)
            return f"Error: {result.stderr}"
            
        output = result.stdout.strip()
        print(f"[Thread - {domain}] Completed successfully.")
        return output
    except Exception as e:
        print(f"[Thread - {domain}] Exception: {e}", file=sys.stderr)
        return f"Exception: {e}"
    finally:
        if os.path.exists(temp_prompt_file):
            os.remove(temp_prompt_file)

def main():
    if not os.path.exists(SUMMARY_PATH):
        print(f"Error: Summary file {SUMMARY_PATH} not found. Run prep_mppt_data.py first.")
        sys.exit(1)
        
    with open(SUMMARY_PATH, 'r') as f:
        data = json.load(f)
        
    # Format data blocks for insertion into prompts
    daily_summaries_str = json.dumps(data["daily_summaries"], indent=2)
    soc_audit_str = json.dumps(data["soc_audit"], indent=2)
    anomalies_str = json.dumps(data["anomalies"], indent=2)
    hourly_trends_str = json.dumps(data["hourly_trends_sample"], indent=2)
    
    # Populate prompts with data
    populated_prompts = {
        "solar_generation": PROMPTS["solar_generation"].format(daily_summaries=daily_summaries_str),
        "battery_health": PROMPTS["battery_health"].format(daily_summaries=daily_summaries_str, soc_audit=soc_audit_str),
        "thermal_load": PROMPTS["thermal_load"].format(daily_summaries=daily_summaries_str, hourly_trends_sample=hourly_trends_str),
        "anomalies_stability": PROMPTS["anomalies_stability"].format(anomalies=anomalies_str)
    }
    
    print(f"Executing sequential analysis domains using local GPU-accelerated Qwen 2.5 7B...")
    
    for domain, prompt in populated_prompts.items():
        print(f"\n--- Starting Domain: {domain} ---")
        output = run_local_query(domain, prompt)
        
        # Save individual domain output immediately
        with open(f"analysis_{domain}.txt", 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"--- Completed Domain: {domain} and saved to analysis_{domain}.txt ---")
                
    print("\nAll analysis domains completed. Ready for final synthesis.")

if __name__ == '__main__':
    main()
