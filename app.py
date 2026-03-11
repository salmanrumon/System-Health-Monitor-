"""
System Health Monitor - Real-time system metrics API with email alerts
"""
from flask import Flask, jsonify, send_from_directory
import psutil
import platform
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from configparser import ConfigParser
from pathlib import Path
import threading
import time
import os

app = Flask(__name__, static_folder="static")

# Alert state
alert_cooldown = {}  # metric -> last_alert_time
recent_alerts = []   # last 10 alerts for dashboard
alerts_lock = threading.Lock()
CHECK_INTERVAL = 60  # seconds between threshold checks


def load_config():
    """Load config.ini, create from example if missing"""
    config_path = Path(__file__).parent / "config.ini"
    example_path = Path(__file__).parent / "config.example.ini"
    if not config_path.exists() and example_path.exists():
        import shutil
        shutil.copy(example_path, config_path)
    cfg = ConfigParser()
    if config_path.exists():
        cfg.read(config_path, encoding="utf-8")
    return cfg


def get_config_int(cfg, section, key, default):
    try:
        return cfg.getint(section, key)
    except (AttributeError, ValueError, TypeError):
        return default


def get_config_str(cfg, section, key, default=""):
    try:
        return cfg.get(section, key, fallback=default).strip()
    except (AttributeError, TypeError):
        return default


def get_config_bool(cfg, section, key, default=False):
    val = get_config_str(cfg, section, key, str(default)).lower()
    return val in ("1", "true", "yes", "on")


def send_alert_email(subject, body):
    """Send alert email via SMTP"""
    cfg = load_config()
    if not get_config_bool(cfg, "alerts", "enabled", False):
        return False
    smtp_server = get_config_str(cfg, "email", "smtp_server")
    smtp_port = get_config_int(cfg, "email", "smtp_port", 587)
    username = get_config_str(cfg, "email", "username")
    password = get_config_str(cfg, "email", "password") or os.environ.get("SMTP_PASSWORD")
    recipient = get_config_str(cfg, "email", "recipient")
    if not all([smtp_server, username, password, recipient]):
        return False
    try:
        msg = MIMEMultipart()
        msg["From"] = username
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(username, password)
            server.sendmail(username, recipient, msg.as_string())
        return True
    except Exception as e:
        with alerts_lock:
            recent_alerts.append({
                "time": datetime.now().isoformat(),
                "metric": "email",
                "message": f"Failed to send email: {e}",
            })
            recent_alerts[:] = recent_alerts[-10:]
        return False


def check_thresholds():
    """Check CPU, RAM, disk against thresholds and send alerts if exceeded"""
    cfg = load_config()
    if not get_config_bool(cfg, "alerts", "enabled", False):
        return
    cpu_thresh = get_config_int(cfg, "thresholds", "cpu", 90)
    ram_thresh = get_config_int(cfg, "thresholds", "ram", 90)
    disk_thresh = get_config_int(cfg, "thresholds", "disk", 90)
    cooldown_mins = get_config_int(cfg, "alerts", "cooldown_minutes", 15)
    cooldown = timedelta(minutes=cooldown_mins)
    now = datetime.now()
    hostname = platform.node()
    disk_path = "C:\\" if platform.system() == "Windows" else "/"

    alerts_to_send = []

    try:
        cpu_pct = psutil.cpu_percent(interval=2)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(disk_path)

        with alerts_lock:
            for metric, value, thresh, name in [
                ("cpu", cpu_pct, cpu_thresh, "CPU"),
                ("ram", memory.percent, ram_thresh, "RAM"),
                ("disk", disk.percent, disk_thresh, "Disk"),
            ]:
                if value >= thresh:
                    last = alert_cooldown.get(metric)
                    if last is None or (now - last) >= cooldown:
                        alert_cooldown[metric] = now
                        alerts_to_send.append((name, value, thresh))

        for name, value, thresh in alerts_to_send:
            subject = f"[Alert] {hostname}: {name} usage at {value:.1f}%"
            body = (
                f"System Health Monitor Alert\n"
                f"Host: {hostname}\n"
                f"Metric: {name}\n"
                f"Current: {value:.1f}%\n"
                f"Threshold: {thresh}%\n"
                f"Time: {now.isoformat()}\n"
            )
            if send_alert_email(subject, body):
                with alerts_lock:
                    recent_alerts.append({
                        "time": now.isoformat(),
                        "metric": name.lower(),
                        "value": round(value, 1),
                        "threshold": thresh,
                        "message": f"{name} at {value:.1f}% (threshold {thresh}%)",
                    })
                    recent_alerts[:] = recent_alerts[-10:]

    except Exception as e:
        with alerts_lock:
            recent_alerts.append({
                "time": now.isoformat(),
                "metric": "error",
                "message": str(e),
            })
            recent_alerts[:] = recent_alerts[-10:]


def alert_worker():
    """Background thread to check thresholds periodically"""
    time.sleep(10)  # Let server start first
    while True:
        check_thresholds()
        time.sleep(CHECK_INTERVAL)


def _get_alert_info():
    """Get alert config and recent alerts for API"""
    cfg = load_config()
    with alerts_lock:
        recent = list(recent_alerts)
    return {
        "enabled": get_config_bool(cfg, "alerts", "enabled", False),
        "thresholds": {
            "cpu": get_config_int(cfg, "thresholds", "cpu", 90),
            "ram": get_config_int(cfg, "thresholds", "ram", 90),
            "disk": get_config_int(cfg, "thresholds", "disk", 90),
        },
        "cooldown_minutes": get_config_int(cfg, "alerts", "cooldown_minutes", 15),
        "recent": recent,
    }


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/health")
def get_health():
    """Get comprehensive system health metrics"""
    try:
        # CPU
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_freq = psutil.cpu_freq()
        cpu_count = psutil.cpu_count(logical=False) or psutil.cpu_count()
        cpu_count_logical = psutil.cpu_count(logical=True)

        # Memory
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()

        # Disk (use C:\ on Windows, / elsewhere)
        disk_path = "C:\\" if platform.system() == "Windows" else "/"
        disk_c = psutil.disk_usage(disk_path)

        # Boot time
        boot_time = datetime.fromtimestamp(psutil.boot_time())

        return jsonify({
            "timestamp": datetime.now().isoformat(),
            "system": {
                "platform": platform.system(),
                "platform_release": platform.release(),
                "platform_version": platform.version(),
                "architecture": platform.machine(),
                "hostname": platform.node(),
                "processor": platform.processor() or "Unknown",
                "boot_time": boot_time.isoformat(),
            },
            "cpu": {
                "percent": round(cpu_percent, 1),
                "count_physical": cpu_count,
                "count_logical": cpu_count_logical,
                "frequency_current_mhz": round(cpu_freq.current, 1) if cpu_freq else None,
                "frequency_min_mhz": round(cpu_freq.min, 1) if cpu_freq else None,
                "frequency_max_mhz": round(cpu_freq.max, 1) if cpu_freq else None,
            },
            "memory": {
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "used_gb": round(memory.used / (1024**3), 2),
                "percent": round(memory.percent, 1),
                "swap_total_gb": round(swap.total / (1024**3), 2),
                "swap_used_gb": round(swap.used / (1024**3), 2),
                "swap_percent": round(swap.percent, 1),
            },
            "disk": {
                "total_gb": round(disk_c.total / (1024**3), 2),
                "used_gb": round(disk_c.used / (1024**3), 2),
                "free_gb": round(disk_c.free / (1024**3), 2),
                "percent": round(disk_c.percent, 1),
            },
            "network": {
                "bytes_sent_mb": round(psutil.net_io_counters().bytes_sent / (1024**2), 2),
                "bytes_recv_mb": round(psutil.net_io_counters().bytes_recv / (1024**2), 2),
                "packets_sent": psutil.net_io_counters().packets_sent,
                "packets_recv": psutil.net_io_counters().packets_recv,
            },
            "alerts": _get_alert_info(),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/processes")
def get_processes():
    """Get top processes by CPU and memory usage"""
    try:
        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "memory_info"]):
            try:
                pinfo = proc.info
                processes.append({
                    "pid": pinfo["pid"],
                    "name": pinfo.get("name", "Unknown"),
                    "cpu_percent": round(pinfo.get("cpu_percent") or 0, 1),
                    "memory_percent": round(pinfo.get("memory_percent") or 0, 1),
                    "memory_mb": round((pinfo.get("memory_info") or type("_", (), {"rss": 0})()).rss / (1024**2), 2),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Sort by CPU, then memory
        processes.sort(key=lambda x: (x["cpu_percent"], x["memory_percent"]), reverse=True)
        return jsonify({"processes": processes[:25]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    t = threading.Thread(target=alert_worker, daemon=True)
    t.start()
    print("System Health Monitor starting at http://127.0.0.1:5000")
    print("Email alerts: edit config.ini and set enabled=true to enable")
    app.run(host="127.0.0.1", port=5000, debug=False)
