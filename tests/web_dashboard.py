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

def load_existing_results():
    """Load any existing test results from files"""
    global test_results
    test_dir = Path("/app/tests")
    
    # Look for combined test reports
    for report_file in test_dir.glob("combined_test_report_*.yaml"):
        try:
            import yaml
            with open(report_file, 'r') as f:
                data = yaml.safe_load(f)
                timestamp = report_file.stem.split('_')[-1]
                test_results[timestamp] = {
                    'file': report_file.name,
                    'data': data,
                    'timestamp': timestamp
                }
        except Exception as e:
            print(f"Error loading {report_file}: {e}")

def run_test_async(debug=False):
    """Run the triage test in a separate thread"""
    global current_test_process, test_logs
    
    test_logs.clear()
    test_logs.append({"timestamp": datetime.now().isoformat(), "level": "INFO", "message": "Starting triage tests..."})
    
    # Also log to stdout
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting triage tests...")
    
    try:
        # Run the test script with unbuffered output
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        cmd = [sys.executable, "-u", "/app/tests/test_triage.py"]  # -u for unbuffered output
        if debug:
            cmd.append("--debug")
        
        current_test_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Redirect stderr to stdout
            text=True,
            bufsize=0,  # Unbuffered
            universal_newlines=True,
            env=env  # Pass environment with PYTHONUNBUFFERED
        )
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔧 Subprocess started with PID {current_test_process.pid}")
        sys.stdout.flush()
        
        # Read output in real-time
        line_count = 0
        while True:
            output = current_test_process.stdout.readline()
            if output == '' and current_test_process.poll() is not None:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🏁 Subprocess finished, read {line_count} lines total")
                sys.stdout.flush()
                break
            if output:
                line_count += 1
                # Add to web logs
                test_logs.append({
                    "timestamp": datetime.now().isoformat(),
                    "level": "INFO",
                    "message": output.strip()
                })
                # Also print to stdout with timestamp
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {output.strip()}")
                # Force flush to ensure immediate output
                sys.stdout.flush()
        
        # Read any remaining stdout (since stderr is redirected there)
        remaining_output = current_test_process.stdout.read()
        if remaining_output:
            for line in remaining_output.split('\n'):
                if line.strip():
                    test_logs.append({
                        "timestamp": datetime.now().isoformat(),
                        "level": "INFO",
                        "message": line.strip()
                    })
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {line.strip()}")
            sys.stdout.flush()
        
        # Check if test completed successfully
        return_code = current_test_process.poll()
        if return_code == 0:
            test_logs.append({
                "timestamp": datetime.now().isoformat(),
                "level": "SUCCESS",
                "message": "Tests completed successfully!"
            })
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Tests completed successfully!")
            sys.stdout.flush()
            # Reload results
            load_existing_results()
        else:
            test_logs.append({
                "timestamp": datetime.now().isoformat(),
                "level": "ERROR",
                "message": f"Tests failed with return code: {return_code}"
            })
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Tests failed with return code: {return_code}")
            sys.stdout.flush()
            
    except Exception as e:
        test_logs.append({
            "timestamp": datetime.now().isoformat(),
            "level": "ERROR",
            "message": f"Error running tests: {str(e)}"
        })
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Error running tests: {str(e)}")
        sys.stdout.flush()
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
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Test already running, ignoring new request")
        return jsonify({"status": "error", "message": "Test already running"}), 400
    
    data = request.get_json() or {}
    debug = data.get('debug', False)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Starting new test run (debug={'on' if debug else 'off'})")
    
    # Start test in background thread
    thread = threading.Thread(target=run_test_async, args=(debug,))
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "started", "message": "Test started successfully"})

@app.route('/api/test_status')
def test_status():
    """Get current test status"""
    global current_test_process
    
    is_running = current_test_process is not None and current_test_process.poll() is None
    
    return jsonify({
        "running": is_running,
        "logs": test_logs[-50:],  # Last 50 log entries
        "total_logs": len(test_logs)
    })

@app.route('/api/results')
def get_results():
    """Get all test results"""
    return jsonify({
        "results": list(test_results.values()),
        "count": len(test_results)
    })

@app.route('/api/results/<result_id>')
def get_result_detail(result_id):
    """Get detailed results for a specific test run"""
    if result_id in test_results:
        return jsonify(test_results[result_id])
    else:
        return jsonify({"error": "Result not found"}), 404

@app.route('/api/stop_test', methods=['POST'])
def stop_test():
    """Stop the current test run"""
    global current_test_process
    
    if current_test_process and current_test_process.poll() is None:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🛑 User requested test stop")
        current_test_process.terminate()
        test_logs.append({
            "timestamp": datetime.now().isoformat(),
            "level": "WARNING",
            "message": "Test stopped by user"
        })
        return jsonify({"status": "stopped", "message": "Test stopped successfully"})
    else:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Stop requested but no test running")
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