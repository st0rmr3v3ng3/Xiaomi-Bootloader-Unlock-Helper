# Xiaomi Bootloader Unlock Helper

This project is a small utility script that automates **official Xiaomi bootloader unlock requests** by replaying requests from the Xiaomi Community App at precisely timed intervals.

It was originally written in **Spring 2025** and relies on the behavior of Xiaomi’s unlock API at that time.  
Any changes made by Xiaomi since then **may break this script**.

---

## ⚠️ Important Notes & Disclaimer

- This tool **does not bypass Xiaomi security**.
- It uses the **official unlock API** and requires valid authentication headers captured from your own device.
- You are responsible for complying with Xiaomi’s terms of service and local laws.
- Excessive requests may trigger rate limits or account restrictions.

**Use at your own risk.**

---

## What this script does

- Sends a **single test request** on startup to verify correctness
- Measures real HTTP latency to the Xiaomi endpoint
- Schedules a **precisely timed wave of unlock requests**
- Targets **Beijing midnight (00:00 CST)** when daily quotas reset
- Automatically aborts when:
  - Your unlock request succeeds
  - The daily quota is exhausted
  - Xiaomi returns an unexpected response
- Logs all requests, responses, and timing data

---

## How it works (high level)

1. You intercept a legitimate bootloader unlock request from the **Xiaomi Community App** using a tool like **[HTTP Toolkit](https://httptoolkit.com/)** 
   [HTTP Toolkit Android App](https://play.google.com/store/apps/details?id=tech.httptoolkit.android.v1)
   [HTTP Toolkit Windows App]([https://play.google.com/store/apps/details?id=tech.httptoolkit.android.v1](https://httptoolkit.com/download/win-exe/))
2. Extract request headers into headers.txt
3. The script:
   - Reconstructs the endpoint
   - Measures latency
   - Adjusts timing
   - Sends a staggered request wave at the quota reset boundary

---

## Requirements

- Python **3.10+**
- Valid Xiaomi account that has been active for at least 30 days
- HTTP Toolkit (or similar) for request interception

### Python dependencies

```bash
pip install aiohttp pytz
