"""
Energy Prediction System - Next-Day Operational Forecasting
Uses time-based linear regression to predict key metrics
Supports both CSV and YAML input formats
"""
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
import matplotlib.pyplot as plt
import os

# ============================================================================
# DATA LOADING & PREPROCESSING
# ============================================================================
def load_data(file_path='\\wsl.localhost\Ubuntu-22.04\home\swaroop\hackathon_ws\src\bottling_energy_sim\bottling_energy_sim\data\bottling_sim.yaml'):
    """Load data from YAML or CSV format with automatic fallback"""
    file_path = file_path if os.path.exists(file_path) else 'data.csv'
    
    if file_path.endswith(('.yaml', '.yml')):
        records, current = [], {}
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('- '):
                    if current: records.append(current)
                    key, val = line[2:].split(': ', 1)
                    current = {key: _parse_val(val)}
                elif ': ' in line:
                    key, val = line.split(': ', 1)
                    current[key] = _parse_val(val)
            if current: records.append(current)
        df = pd.DataFrame(records)
        print(f"✓ Loaded {len(df)} records (YAML)")
    else:
        df = pd.read_csv(file_path)
        print(f"✓ Loaded {len(df)} records (CSV)")
    return df

def _parse_val(val):
    """Parse YAML value as float or string"""
    try: return float(val)
    except ValueError: return val

df = load_data('data.yaml')
t = ((pd.to_datetime(df['Date']) - pd.to_datetime(df['Date']).min()).dt.days.values.reshape(-1, 1) 
     if 'Date' in df.columns else np.arange(len(df)).reshape(-1, 1))

# ============================================================================
# TIME-BASED PREDICTIONS (Next Day)
# ============================================================================
predict_cols = ['Energy_kWh', 'Line_Consumption_kWh', 'CO2']
next_t = np.array([[t.max() + 1]])

predicted_values = {col: LinearRegression().fit(t, df[col]).predict(next_t)[0] 
                    for col in predict_cols if col in df.columns}

# ============================================================================
# OPERATIONAL METRICS CALCULATION
# ============================================================================
total_plant_energy = predicted_values.get('Energy_kWh', np.nan)
line_consumption = predicted_values.get('Line_Consumption_kWh', np.nan)
co2_saved = max(0, df['CO2'].mean() - predicted_values.get('CO2', np.nan))

# ============================================================================
# VISUALIZATION - MATPLOTLIB TABLE
# ============================================================================
fig, ax = plt.subplots(figsize=(10, 4))
ax.axis('off')
ax.set_title('Next-Day Predictions (Linear Regression)', fontsize=16, fontweight='bold', pad=15)

metrics = [
    ['Predicted Total Plant Energy', f"{total_plant_energy:.2f} kWh"],
    ['Predicted Line Consumption (Bottling)', f"{line_consumption:.2f} kWh"],
    ['Predicted CO2 Savings', f"{co2_saved:.2f} ppm"]
]

table = ax.table(cellText=metrics, colLabels=['Metric', 'Predicted Value'], loc='center')
table.scale(1, 1.3)
for (row, col), cell in table.get_celld().items():
    cell.set_fontsize(13 if row == 0 else 12)
    if row == 0: cell.set_text_props(weight='bold')

ax.text(0.0, 0.05, f"Generated: {pd.Timestamp.now():%Y-%m-%d %H:%M}", fontsize=9, color='gray')
plt.tight_layout()
plt.show()

# ============================================================================
# CONSOLE OUTPUT
# ============================================================================
print("\nNext-Day Predictions:")
print(f"  Predicted Total Plant Energy: {total_plant_energy:.2f} kWh")
print(f"  Predicted Line Consumption (Bottling): {line_consumption:.2f} kWh")
print(f"  Predicted CO2 Savings: {co2_saved:.2f} ppm")
print("\n" + "="*50)
print("Model Training Complete!")
print("="*50)

