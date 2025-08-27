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
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory
from pathlib import Path

app = Flask(__name__)

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
    
    try:
        # Run the test script
        cmd = [sys.executable, "/app/tests/test_triage.py"]
        if debug:
            cmd.append("--debug")
        
        current_test_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Read output in real-time
        while True:
            output = current_test_process.stdout.readline()
            if output == '' and current_test_process.poll() is not None:
                break
            if output:
                test_logs.append({
                    "timestamp": datetime.now().isoformat(),
                    "level": "INFO",
                    "message": output.strip()
                })
        
        # Read any remaining stderr
        stderr = current_test_process.stderr.read()
        if stderr:
            test_logs.append({
                "timestamp": datetime.now().isoformat(),
                "level": "ERROR", 
                "message": stderr
            })
        
        # Check if test completed successfully
        return_code = current_test_process.poll()
        if return_code == 0:
            test_logs.append({
                "timestamp": datetime.now().isoformat(),
                "level": "SUCCESS",
                "message": "Tests completed successfully!"
            })
            # Reload results
            load_existing_results()
        else:
            test_logs.append({
                "timestamp": datetime.now().isoformat(),
                "level": "ERROR",
                "message": f"Tests failed with return code: {return_code}"
            })
            
    except Exception as e:
        test_logs.append({
            "timestamp": datetime.now().isoformat(),
            "level": "ERROR",
            "message": f"Error running tests: {str(e)}"
        })
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
    
    data = request.get_json() or {}
    debug = data.get('debug', False)
    
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
        current_test_process.terminate()
        test_logs.append({
            "timestamp": datetime.now().isoformat(),
            "level": "WARNING",
            "message": "Test stopped by user"
        })
        return jsonify({"status": "stopped", "message": "Test stopped successfully"})
    else:
        return jsonify({"status": "error", "message": "No test running"}), 400

@app.route('/download/<filename>')
def download_file(filename):
    """Download test result files"""
    return send_from_directory('/app/tests', filename, as_attachment=True)

if __name__ == '__main__':
    # Load existing results on startup
    load_existing_results()
    
    # Run the Flask app
    app.run(host='0.0.0.0', port=80, debug=False)