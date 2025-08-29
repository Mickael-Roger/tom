#!/usr/bin/env python3
"""
Tom Triage Testing Web Dashboard
Web interface for running triage tests and visualizing results
"""

import json
import os
import sys
import subprocess
import threading
import time
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory
from pathlib import Path

app = Flask(__name__)

# Disable Flask's request logging
import logging
logging.getLogger('werkzeug').setLevel(logging.WARNING)

# Global variables for test state
current_test_process = None
test_results = {}
test_logs = []

STATUS_FILE = '/app/tests/triage_status.json'

def load_existing_results():
    """Load any existing test results from files"""
    global test_results
    test_dir = Path("/app/tests")
    test_results = {}
    
    # Look for combined test reports
    for report_file in sorted(test_dir.glob("combined_test_report_*.yaml"), reverse=True):
        try:
            import yaml
            with open(report_file, 'r') as f:
                data = yaml.safe_load(f)
                timestamp_str = report_file.stem.replace('combined_test_report_', '')
                # Reformat timestamp for display if needed
                try:
                    dt_obj = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
                    display_ts = dt_obj.strftime('%Y-%m-%d %H:%M:%S')
                except ValueError:
                    display_ts = timestamp_str

                test_results[display_ts] = {
                    'file': report_file.name,
                    'data': data,
                    'timestamp': display_ts
                }
        except Exception as e:
            print(f"Error loading {report_file}: {e}")

def run_test_async(debug=False):
    """Run the triage test in a separate thread"""
    global current_test_process
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting triage tests...")
    
    try:
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        cmd = [sys.executable, "-u", "/app/tests/test_triage.py"]
        if debug:
            cmd.append("--debug")
        
        current_test_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=env
        )
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔧 Subprocess started with PID {current_test_process.pid}")
        
        # Log stdout/stderr to console for debugging, but don't parse it
        for line in iter(current_test_process.stdout.readline, ''):
            print(f"[test_triage.py] {line.strip()}")
            sys.stdout.flush()

        current_test_process.wait()
        return_code = current_test_process.poll()
        
        if return_code == 0:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Tests completed successfully!")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Tests failed with return code: {return_code}")
        
        # Reload results from files
        load_existing_results()
            
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Error running tests: {str(e)}")
        # Update status file to reflect error
        try:
            with open(STATUS_FILE, 'r+') as f:
                data = json.load(f)
                data['status'] = 'error'
                data['error'] = str(e)
                f.seek(0)
                json.dump(data, f, indent=2)
        except Exception as file_e:
            print(f"Could not update status file with error: {file_e}")

    finally:
        current_test_process = None

@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/start_test', methods=['POST'])
def start_test():
    """Start a new test run"""
    global current_test_process
    
    if current_test_process and current_test_process.poll() is None:
        return jsonify({"status": "error", "message": "Test already running"}), 400
    
    # Clean up old status file
    if os.path.exists(STATUS_FILE):
        os.remove(STATUS_FILE)

    data = request.get_json() or {}
    debug = data.get('debug', False)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Starting new test run (debug={'on' if debug else 'off'})")
    
    thread = threading.Thread(target=run_test_async, args=(debug,))
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "started", "message": "Test started successfully"})

@app.route('/api/test_status')
def test_status():
    """Get current test status from JSON file"""
    is_running = current_test_process is not None and current_test_process.poll() is None

    if not os.path.exists(STATUS_FILE):
        if is_running:
            return jsonify({"status": "initializing", "logs": []})
        else:
            return jsonify({"status": "idle"})

    try:
        with open(STATUS_FILE, 'r') as f:
            data = json.load(f)
        
        # If process died, update status
        if not is_running and data.get('status') in ['initializing', 'running']:
            data['status'] = 'error'
            data['error'] = 'Test process terminated unexpectedly.'
            with open(STATUS_FILE, 'w') as f:
                json.dump(data, f, indent=2)

        return jsonify(data)
    except (IOError, json.JSONDecodeError) as e:
        return jsonify({"status": "error", "error": f"Could not read status file: {e}"}), 500

@app.route('/api/results')
def get_results():
    """Get all test results"""
    load_existing_results() # Reload from files
    return jsonify({
        "results": sorted(list(test_results.values()), key=lambda x: x['timestamp'], reverse=True),
        "count": len(test_results)
    })

@app.route('/api/results/<result_id>')
def get_result_detail(result_id):
    """Get detailed results for a specific test run"""
    # The result_id is the timestamp string
    if result_id in test_results:
        return jsonify(test_results[result_id])
    else:
        # Try loading again in case it's a new result
        load_existing_results()
        if result_id in test_results:
            return jsonify(test_results[result_id])
        return jsonify({"error": "Result not found"}), 404

@app.route('/api/stop_test', methods=['POST'])
def stop_test():
    """Stop the current test run"""
    global current_test_process
    
    if current_test_process and current_test_process.poll() is None:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🛑 User requested test stop")
        current_test_process.terminate()
        
        # Update status file
        try:
            if os.path.exists(STATUS_FILE):
                with open(STATUS_FILE, 'r+') as f:
                    data = json.load(f)
                    data['status'] = 'stopped'
                    data['error'] = 'Test stopped by user.'
                    data['end_time'] = datetime.now().isoformat()
                    f.seek(0)
                    f.truncate()
                    json.dump(data, f, indent=2)
            else:
                # Create status file if it doesn't exist
                with open(STATUS_FILE, 'w') as f:
                    json.dump({
                        'status': 'stopped',
                        'error': 'Test stopped by user.',
                        'end_time': datetime.now().isoformat()
                    }, f, indent=2)
        except Exception as e:
            print(f"Error updating status file on stop: {e}")

        return jsonify({"status": "stopped", "message": "Test stopped successfully"})
    else:
        return jsonify({"status": "error", "message": "No test running"}), 400

@app.route('/download/<filename>')
def download_file(filename):
    """Download test result files"""
    return send_from_directory('/app/tests', filename, as_attachment=True)

if __name__ == '__main__':
    # Additional logging cleanup
    logging.getLogger('werkzeug').disabled = True
    
    print("🎯 Tom Triage Testing Web Dashboard")
    print("=" * 40)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Starting web server on http://0.0.0.0:80")
    
    # Load existing results on startup
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📊 Loading existing test results...")
    load_existing_results()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📋 Found {len(test_results)} existing test results")
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Web dashboard ready - Open your browser to http://localhost:8080")
    print("=" * 40)
    
    # Run the Flask app with minimal logging
    app.run(host='0.0.0.0', port=80, debug=False, use_reloader=False)