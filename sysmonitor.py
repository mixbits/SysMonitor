# File directory: /home/user/Documents/SystemMonitor/sysmonitor.py
#!/usr/bin/env python3
import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output, State, ALL
from dash.exceptions import PreventUpdate
import plotly.graph_objs as go
import psutil
import GPUtil
import logging
from collections import deque
from datetime import datetime, timedelta
import pandas as pd
import time
import threading
import os
import glob
import re
import json
import calendar
from dateutil.relativedelta import relativedelta
from flask import Flask, jsonify, request, send_file, send_from_directory
import csv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='.')

# Replace 'user' with your actual username
log_dir = '/home/user/Documents/SystemMonitor/logs'
os.makedirs(log_dir, exist_ok=True)

images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'images')
os.makedirs(images_dir, exist_ok=True)

current_date = datetime.now().date()
csv_log_path = os.path.join(log_dir, f'system_stats_{current_date.strftime("%Y-%m-%d")}.csv')
archive_dir = os.path.join(log_dir, 'archive')
os.makedirs(archive_dir, exist_ok=True)

file_handler = logging.FileHandler(os.path.join(log_dir, 'sysmonitor.log'))
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

NIC_MAX_MBPS = 2500.0

short_history = {
    'time': deque(maxlen=240),
    'cpu': deque(maxlen=240),
    'ram': deque(maxlen=240),
    'net': deque(maxlen=240),
    'gpu0': deque(maxlen=240),
    'gpu1': deque(maxlen=240),
    'gpu2': deque(maxlen=240),
}

long_history = {
    'time': deque(),
    'cpu': deque(),
    'ram': deque(),
    'net': deque(),
    'gpu0': deque(),
    'gpu1': deque(),
    'gpu2': deque(),
}

prev_net_io = None
prev_time = None
rolling_net_buffer = deque(maxlen=3)

available_dates_cache = []
last_date_check = None

history_lock = threading.Lock()

def get_system_stats():
    global prev_net_io, prev_time, rolling_net_buffer
    try:
        cpu_percent = psutil.cpu_percent(interval=0)
        ram_percent = psutil.virtual_memory().percent
        curr_net_io = psutil.net_io_counters()
        now = time.time()
        net_usage_percent = 0.0
        if (prev_net_io is not None) and (prev_time is not None):
            time_diff = now - prev_time
            total_bytes_diff = (
                curr_net_io.bytes_sent - prev_net_io.bytes_sent +
                curr_net_io.bytes_recv - prev_net_io.bytes_recv
            )
            net_mbps = (total_bytes_diff * 8) / time_diff / 1_000_000
            net_usage_percent = (net_mbps / NIC_MAX_MBPS) * 100

        prev_net_io = curr_net_io
        prev_time = now

        rolling_net_buffer.append(net_usage_percent)
        smoothed_net_percent = sum(rolling_net_buffer) / len(rolling_net_buffer)
        smoothed_net_percent = min(smoothed_net_percent, 100.0)

        gpus = GPUtil.getGPUs()
        gpu_loads = [0, 0, 0]
        for i in range(min(3, len(gpus))):
            gpu_loads[i] = gpus[i].load * 100

        return {
            'CPU': cpu_percent,
            'RAM': ram_percent,
            'NET': smoothed_net_percent,
            'GPU0': gpu_loads[0],
            'GPU1': gpu_loads[1],
            'GPU2': gpu_loads[2]
        }
    except Exception as e:
        logging.error(f"Error fetching system stats: {e}")
        return {}

def remove_old_data():
    cutoff = datetime.now() - timedelta(hours=6)
    while long_history['time'] and long_history['time'][0] < cutoff:
        for key in long_history:
            if long_history[key]:
                long_history[key].popleft()

def format_day(dt: datetime) -> str:
    suffix = "th"
    if dt.day in [1, 21, 31]: suffix = "st"
    elif dt.day in [2, 22]: suffix = "nd"
    elif dt.day in [3, 23]: suffix = "rd"
    return f"{dt.strftime('%B')} {dt.day}{suffix}"

def log_csv_header():
    """Create or check CSV log file with headers"""
    if not os.path.exists(csv_log_path) or os.path.getsize(csv_log_path) == 0:
        with open(csv_log_path, 'w') as f:
            f.write("Timestamp,CPU(%),RAM(%),NET(%),GPU0(%),GPU1(%),GPU2(%)\n")

def append_to_csv(timestamp, data):
    """Append a single data point to the CSV log"""
    with open(csv_log_path, 'a') as f:
        f.write(f"{timestamp.strftime('%Y-%m-%d %I:%M:%S %p')},"
                f"{data.get('CPU', 0):.2f},"
                f"{data.get('RAM', 0):.2f},"
                f"{data.get('NET', 0):.2f},"
                f"{data.get('GPU0', 0):.2f},"
                f"{data.get('GPU1', 0):.2f},"
                f"{data.get('GPU2', 0):.2f}\n")

def check_and_rotate_log_file():
    """Check if the day has changed and rotate log file if needed"""
    global csv_log_path, current_date
    
    now = datetime.now()
    today = now.date()
    
    if today != current_date:
        logger.info(f"Day changed from {current_date} to {today}, rotating log file")
        
        current_date = today
        
        csv_log_path = os.path.join(log_dir, f'system_stats_{today.strftime("%Y-%m-%d")}.csv')
        
        log_csv_header()
        
        archive_old_logs()
        
        return True
    
    return False

def archive_old_logs(max_days=30):
    """Archive log files older than max_days"""
    try:
        stat_files = glob.glob(os.path.join(log_dir, "system_stats_*.csv"))
        
        today = datetime.now().date()
        cutoff_date = today - timedelta(days=max_days)
        
        for file_path in stat_files:
            filename = os.path.basename(file_path)
            match = re.search(r'system_stats_(\d{4}-\d{2}-\d{2})\.csv', filename)
            
            if match:
                file_date_str = match.group(1)
                try:
                    file_date = datetime.strptime(file_date_str, "%Y-%m-%d").date()
                    
                    if file_date < cutoff_date:
                        year_month_dir = os.path.join(archive_dir, file_date.strftime("%Y-%m"))
                        os.makedirs(year_month_dir, exist_ok=True)
                        
                        archive_path = os.path.join(year_month_dir, filename)
                        os.rename(file_path, archive_path)
                        logger.info(f"Archived old log file: {filename} to {year_month_dir}")
                except Exception as e:
                    logger.error(f"Failed to parse date from filename {filename}: {e}")
    except Exception as e:
        logger.error(f"Error during log archiving: {e}")

def background_monitoring():
    """Background thread function to continuously collect system stats"""
    log_csv_header()
    logger.info("Background monitoring thread started")
    
    while True:
        try:
            data = get_system_stats()
            if data:
                now = datetime.now()
                
                check_and_rotate_log_file()
                
                with history_lock:
                    for k in short_history:
                        short_history[k].append(data.get(k.upper(), 0.0) if k != 'time' else now)
                    for k in long_history:
                        long_history[k].append(data.get(k.upper(), 0.0) if k != 'time' else now)
                    remove_old_data()
                
                append_to_csv(now, data)
                
            time.sleep(4)
        except Exception as e:
            logger.error(f"Error in background monitoring: {e}")
            time.sleep(4)

def get_log_files():
    """Get a list of CSV files in the logs directory including archives"""
    main_log_files = glob.glob(os.path.join(log_dir, "*.csv"))
    
    archive_files = []
    for year_month_dir in glob.glob(os.path.join(archive_dir, "*")):
        if os.path.isdir(year_month_dir):
            archive_files.extend(glob.glob(os.path.join(year_month_dir, "*.csv")))
    
    return [os.path.basename(f) for f in main_log_files + archive_files]

def get_available_log_dates():
    """Extract unique dates from log files and timestamp columns"""
    global available_dates_cache, last_date_check
    
    current_time = time.time()
    if last_date_check is None or (current_time - last_date_check > 60):
        all_dates = []
        today = datetime.now().date()
        
        if os.path.exists(csv_log_path):
            try:
                df = pd.read_csv(csv_log_path)
                if 'Timestamp' in df.columns:
                    df['Date'] = pd.to_datetime(df['Timestamp']).dt.date
                    valid_dates = [date for date in df['Date'].unique() if date <= today]
                    all_dates.extend(valid_dates)
            except Exception as e:
                logger.error(f"Error reading dates from system_stats.csv: {e}")
        
        for log_file in get_log_files():
            if log_file == 'system_stats.csv':
                continue
                
            file_path = os.path.join(log_dir, log_file)
            try:
                df = pd.read_csv(file_path)
                time_col = next((col for col in df.columns if 'time' in col.lower() or 'date' in col.lower() or 'timestamp' in col.lower()), None)
                if time_col:
                    df['Date'] = pd.to_datetime(df[time_col]).dt.date
                    valid_dates = [date for date in df['Date'].unique() if date <= today]
                    all_dates.extend(valid_dates)
            except Exception as e:
                logger.error(f"Error reading dates from {log_file}: {e}")
        
        available_dates_cache = sorted(list(set(all_dates)))
        last_date_check = current_time
        
        try:
            with open(os.path.join(log_dir, 'available_dates.json'), 'w') as f:
                json.dump([d.strftime('%Y-%m-%d') for d in available_dates_cache], f)
        except Exception as e:
            logger.error(f"Error writing available dates to JSON: {e}")
    
    return available_dates_cache

def get_log_data_for_date(selected_date):
    """Get log data for the selected date"""
    date_obj = pd.to_datetime(selected_date).date() if isinstance(selected_date, str) else selected_date
    
    date_specific_log = os.path.join(log_dir, f'system_stats_{date_obj.strftime("%Y-%m-%d")}.csv')
    
    archive_month_dir = os.path.join(archive_dir, date_obj.strftime("%Y-%m"))
    archive_specific_log = os.path.join(archive_month_dir, f'system_stats_{date_obj.strftime("%Y-%m-%d")}.csv')
    
    if os.path.exists(date_specific_log):
        log_file = date_specific_log
    elif os.path.exists(archive_specific_log):
        log_file = archive_specific_log
    elif os.path.exists(csv_log_path):
        log_file = csv_log_path
    else:
        logger.warning(f"No log file found for date {date_obj}")
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(log_file)
        if 'Timestamp' in df.columns:
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
            df['Date'] = df['Timestamp'].dt.date
            
            return df[df['Date'] == date_obj].sort_values('Timestamp')
        else:
            logger.error(f"Log file {log_file} has no Timestamp column")
            return pd.DataFrame()
    except Exception as e:
        logger.error(f"Error reading log file for date {date_obj}: {e}")
        return pd.DataFrame()

@app.route('/')
def index():
    return send_file('dashboard.html')

@app.route('/logs')
def logs_view():
    return send_file('logviewer.html')

@app.route('/favicon.ico')
def favicon():
    """Serve the favicon from the images directory"""
    try:
        images_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'images')
        response = send_from_directory(images_path, 'sysmonitor.ico')
        response.headers['Content-Type'] = 'image/x-icon'
        response.headers['Cache-Control'] = 'public, max-age=86400'
        logger.info(f"Serving favicon from {os.path.join(images_path, 'sysmonitor.ico')}")
        return response
    except Exception as e:
        logger.error(f"Error serving favicon: {e}")
        return "", 404

@app.route('/images/<path:filename>')
def serve_image(filename):
    """Serve image files from the images directory"""
    try:
        images_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'images')
        return send_from_directory(images_path, filename)
    except Exception as e:
        logger.error(f"Error serving image {filename}: {e}")
        return f"Image not found: {filename}", 404

@app.route('/api/current')
def get_current_stats():
    """Return the current system statistics"""
    return jsonify(get_system_stats())

@app.route('/api/short-history')
def get_short_history():
    """Return the short history data for the dashboard"""
    with history_lock:
        history_data = {
            'time': [t.isoformat() for t in short_history['time']],
            'cpu': list(short_history['cpu']),
            'ram': list(short_history['ram']),
            'net': list(short_history['net']),
            'gpu0': list(short_history['gpu0']),
            'gpu1': list(short_history['gpu1']),
            'gpu2': list(short_history['gpu2'])
        }
    return jsonify(history_data)

@app.route('/api/long-history')
def get_long_history():
    """Return the long history data for the dashboard"""
    with history_lock:
        history_data = {
            'time': [t.isoformat() for t in long_history['time']],
            'cpu': list(long_history['cpu']),
            'ram': list(long_history['ram']),
            'net': list(long_history['net']),
            'gpu0': list(long_history['gpu0']),
            'gpu1': list(long_history['gpu1']),
            'gpu2': list(long_history['gpu2'])
        }
    return jsonify(history_data)

@app.route('/api/available-dates')
def get_available_dates_api():
    """Return the available log dates"""
    dates = get_available_log_dates()
    return jsonify([d.strftime('%Y-%m-%d') for d in dates])

@app.route('/api/log-data/<date>')
def get_log_data_api(date):
    """Return log data for the specified date"""
    try:
        df = get_log_data_for_date(date)
        if df.empty:
            return jsonify({'error': f'No data available for date {date}'}), 404
        
        data = {
            'time': [t.isoformat() for t in df['Timestamp']],
            'cpu': df['CPU(%)'].tolist(),
            'ram': df['RAM(%)'].tolist(),
            'net': df['NET(%)'].tolist(),
            'gpu0': df['GPU0(%)'].tolist(),
            'gpu1': df['GPU1(%)'].tolist(),
            'gpu2': df['GPU2(%)'].tolist()
        }
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error getting log data for date {date}: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    monitor_thread = threading.Thread(target=background_monitoring, daemon=True)
    monitor_thread.start()
    
    app.run(debug=False, host='0.0.0.0', port=5500)