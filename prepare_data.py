import pandas as pd
import random

# Load existing healing log
df = pd.read_csv('healing_log.csv')

# Add random CPU, RAM, Disk usage
df['CPU Usage (%)'] = [random.randint(20, 100) for _ in range(len(df))]
df['RAM Usage (%)'] = [random.randint(30, 90) for _ in range(len(df))]
df['Disk Usage (%)'] = [random.randint(20, 70) for _ in range(len(df))]

# Add Anomaly Label
# If Action Taken contains "Restarted", label as 1 (Anomaly), else 0
df['Anomaly'] = df['Action Taken'].apply(lambda x: 1 if 'Restarted' in x else 0)

# Save the updated CSV
df.to_csv('healing_log_ml_ready.csv', index=False)

print("✅ healing_log_ml_ready.csv created successfully!")
