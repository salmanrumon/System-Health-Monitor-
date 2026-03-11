# System Health Monitor

A real-time system health dashboard that monitors CPU, memory, disk, network, and running processes, with **email alerts** when thresholds are exceeded.

## Features

- **CPU** – Usage percentage, core count, frequency
- **Memory (RAM)** – Used/available, swap usage
- **Disk** – C: drive usage on Windows
- **Network** – Bytes sent/received, packet counts
- **Processes** – Top 25 processes by CPU and memory usage
- **Email Alerts** – Sends alerts when CPU, RAM, or disk exceeds configurable thresholds

## Requirements

- Python 3.8+
- Windows (disk monitor uses C: drive; other metrics work cross-platform)

## Setup

1. Create a virtual environment (recommended):

   ```bash
   cd system-health-monitor
   python -m venv venv
   venv\Scripts\activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## Run

**One-click:** Double-click `run.bat` – it creates the virtual environment, installs dependencies, and starts the server.

Or run manually:
```bash
python app.py
```

Open **http://127.0.0.1:5000** in your browser. The dashboard refreshes every 2 seconds.

## Email Alerts

1. Copy `config.example.ini` to `config.ini` (or edit the existing `config.ini`)
2. Set thresholds (default: 90% for CPU, RAM, disk)
3. Configure your SMTP settings:
   - **Gmail**: Use an [App Password](https://support.google.com/accounts/answer/185833), not your normal password
   - **Outlook**: `smtp.outlook.com`, port 587
4. Set `enabled = true` in the `[alerts]` section
5. For security, use the environment variable for password:
   ```powershell
   $env:SMTP_PASSWORD = "your-app-password"
   ```

The monitor checks every 60 seconds. Alerts are rate-limited by `cooldown_minutes` (default 15) so you won't be spammed for the same issue.

## API Endpoints

- `GET /` – Dashboard UI
- `GET /api/health` – Full system metrics including alert config and recent alerts (JSON)
- `GET /api/processes` – Top processes (JSON)
