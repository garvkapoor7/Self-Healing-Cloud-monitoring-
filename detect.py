import requests
import time
import pandas as pd
import numpy as np
import json
import paramiko
import csv
from datetime import datetime
import os

# Thresholds for anomaly detection
CPU_THRESHOLD = 80.0  # 80% CPU usage
RAM_THRESHOLD = 85.0  # 85% RAM usage
DISK_THRESHOLD = 90.0  # 90% Disk usage

# Prometheus server details
PROMETHEUS_URL = "http://localhost:9090"






# Load server configuration from JSON file

def load_servers(config_file="server_config.json"):
    with open(config_file) as f:
        servers = json.load(f)
        return [f"{server['ip']}:{server['port']}" for server in servers], servers

# Load both endpoints (ip:port) and full server details
server_endpoints, server_details = load_servers()









#Sends a query to Prometheus using PromQL.
#Returns live metrics like CPU, RAM, and Disk usage.
def query_prometheus(promql_query):
    try:
        response = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={'query': promql_query})
        response.raise_for_status()
        data = response.json()
        if 'data' in data and 'result' in data['data']:
            return data['data']['result']
        return []
    except Exception as e:
        print(f"Error querying Prometheus: {str(e)}")
        return []







# Queries CPU, RAM, and Disk usage
# Returns a dictionary of metrics
def get_server_metrics(server):
    metrics = {}
    
    # Query CPU usage (over last 1m)
    cpu_query = f'(1 - avg(rate(node_cpu_seconds_total{{instance="{server}", mode="idle"}}[1m]))) * 100'
    cpu_result = query_prometheus(cpu_query)
    if cpu_result:
        metrics['CPU'] = float(cpu_result[0]['value'][1])
    else:
        metrics['CPU'] = 0.0
    
    # Query Memory usage
    mem_query = f'(1 - (node_memory_MemAvailable_bytes{{instance="{server}"}} / node_memory_MemTotal_bytes{{instance="{server}"}})) * 100'
    mem_result = query_prometheus(mem_query)
    if mem_result:
        metrics['RAM'] = float(mem_result[0]['value'][1])
    else:
        metrics['RAM'] = 0.0
    
    # Query Disk usage
    disk_query = f'(1 - node_filesystem_avail_bytes{{instance="{server}", mountpoint="/"}} / node_filesystem_size_bytes{{instance="{server}", mountpoint="/"}}) * 100'
    disk_result = query_prometheus(disk_query)
    if disk_result:
        metrics['DISK'] = float(disk_result[0]['value'][1])
    else:
        metrics['DISK'] = 0.0
    
    return metrics








# Compares the current CPU, RAM, and Disk usage against the thresholds
# Returns a list of any anomalies
def detect_anomalies(metrics):
    anomalies = []
    print(f"\nCurrent metrics:")
    print(f"CPU: {metrics['CPU']:.2f}% (Threshold: {CPU_THRESHOLD}%)")
    print(f"RAM: {metrics['RAM']:.2f}% (Threshold: {RAM_THRESHOLD}%)")
    print(f"DISK: {metrics['DISK']:.2f}% (Threshold: {DISK_THRESHOLD}%)")
    
    if metrics['CPU'] > CPU_THRESHOLD:
        anomalies.append('High CPU')
    if metrics['RAM'] > RAM_THRESHOLD:
        anomalies.append('High RAM')
    if metrics['DISK'] > DISK_THRESHOLD:
        anomalies.append('High Disk')
    return anomalies















# Appends a row in healing_history.csv
# Logs before and after metrics, issue type, and timestamp

def log_healing_history(ip_address, issue, before_metrics, after_metrics, status):
    try:
        if not os.path.exists('healing_history.csv'):
            with open('healing_history.csv', 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'ip_address', 'issue', 'before_cpu', 'before_ram', 'before_disk', 
                               'after_cpu', 'after_ram', 'after_disk', 'status'])
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open('healing_history.csv', 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp,
                ip_address,
                issue,
                before_metrics['CPU'],
                before_metrics['RAM'],
                before_metrics['DISK'],
                after_metrics['CPU'],
                after_metrics['RAM'],
                after_metrics['DISK'],
                status
            ])
    except Exception as e:
        print(f"Error logging healing history: {str(e)}")





def ensure_node_exporter(server_info):
    """Guarantees Node Exporter is running on the server."""
    ip = server_info["ip"]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        key = paramiko.RSAKey.from_private_key_file(server_info["pem_file"])
        ssh.connect(hostname=ip, username=server_info["username"], pkey=key)

        # Check if Node Exporter is active
        stdin, stdout, stderr = ssh.exec_command(
            "systemctl is-active node_exporter || echo 'NOT_INSTALLED'"
        )
        status = stdout.read().decode().strip()

        if status == "NOT_INSTALLED" or "inactive" in status:
            print(f"⚠️ Node Exporter missing on {ip}. Installing...")
            
            # Upload and run your install script
            sftp = ssh.open_sftp()
            sftp.put("install_node_exporter.sh", "/tmp/install_node_exporter.sh")
            sftp.close()

            # Execute installation
            commands = [
                "chmod +x /tmp/install_node_exporter.sh",
                "sudo /tmp/install_node_exporter.sh"
            ]
            for cmd in commands:
                stdin, stdout, stderr = ssh.exec_command(cmd)
                if stderr.read():
                    print(f"Install error: {stderr.read().decode()}")

            # Verify installation
            stdin, stdout, stderr = ssh.exec_command("systemctl is-active node_exporter")
            if "active" not in stdout.read().decode():
                raise Exception("Node Exporter failed to start")

        ssh.close()
        return True

    except Exception as e:
        print(f"❌ Node Exporter setup failed on {ip}: {str(e)}")
        return False




# Connects to a server via SSH
# If Node Exporter is not found, installs it using install_node_exporter.sh
# If found, restarts it
# Logs the healing action and new metrics

def ssh_heal_server(server_info, before_metrics, issue):
    ip_address= server_info["ip"]
    
    
    
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        key = paramiko.RSAKey.from_private_key_file(server_info["pem_file"])
        ssh.connect(
            hostname=ip_address,
            username=server_info["username"],
            pkey=key
            
            
        )
        # First check if node_exporter is installed
        stdin, stdout, stderr = ssh.exec_command('which node_exporter')
        if not stdout.read().decode().strip():
            # Upload and execute the installation script
            sftp = ssh.open_sftp()
            sftp.put('install_node_exporter.sh', '/tmp/install_node_exporter.sh')
            sftp.close()
            
            # Make the script executable and run it
            stdin, stdout, stderr = ssh.exec_command('chmod +x /tmp/install_node_exporter.sh && sudo /tmp/install_node_exporter.sh')
            time.sleep(5)  # Wait for service to start
            # Get metrics after installation
            after_metrics = get_server_metrics(f"{ip_address}:9100")
            log_healing_history(ip_address, issue, before_metrics, after_metrics, "Success: Installed and Started")
            print(f"Success: Installed and Started {ip_address}")
        else:
            # If node_exporter is installed, restart it
            stdin, stdout, stderr = ssh.exec_command('sudo systemctl restart node_exporter')
            time.sleep(2)  # Wait for metrics to stabilize
            # Get metrics after restart
            after_metrics = get_server_metrics(f"{ip_address}:9100")
            log_healing_history(ip_address, issue, before_metrics, after_metrics, "Success: Restarted")
            print(f"Success: Restarted {ip_address}")
        ssh.close()

    except Exception as e:
        print(f"SSH Healing failed for {ip_address}: {str(e)}")
        log_healing_history(ip_address, issue, before_metrics, before_metrics, f"Failed: {str(e)}")

# Continuous Monitoring Loop
while True:
    print("\n--- Checking Server Health ---")
    all_status = []
    
    # Iterate through both endpoints (ip:port) and full server details
    for endpoint, server in zip(server_endpoints, server_details):
        try:
            print(f"\nChecking server: {endpoint}")
            metrics = get_server_metrics(endpoint)
            anomalies = detect_anomalies(metrics)
            
            # Store server status
            status = {
                'server': endpoint,
                'metrics': metrics,
                'anomalies': anomalies
            }
            all_status.append(status)
            
            if anomalies:
                print(f"\n⚠️ Anomalies detected on {server['ip']}:")
                for anomaly in anomalies:
                    print(f"- {anomaly}")
                
                # Heal using full server config (PEM auth)
                print(f"Attempting to heal {server['ip']}...")
                ssh_heal_server(server, metrics, ', '.join(anomalies))
            else:
                print(f"✅ {endpoint} is healthy (CPU: {metrics['CPU']}%, RAM: {metrics['RAM']}%)")
            
        except Exception as e:
            print(f"Error monitoring {endpoint}: {str(e)}")
            continue
    
    # Save status to JSON
    with open('status.json', 'w') as f:
        json.dump(all_status, f, indent=2)
    
    time.sleep(30)  # Check every 30 seconds