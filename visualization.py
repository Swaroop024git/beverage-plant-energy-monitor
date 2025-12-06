import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import random
import os
import json
import time

# Page configuration
st.set_page_config(
    page_title="Beverage Bottle Production - Energy Dashboard",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .main { padding: 0rem 1rem; }
    .metric-card { background: linear-gradient(135deg,#667eea 0%,#764ba2 100%);
        padding:20px;border-radius:10px;color:white;text-align:center;}
    .stMetric { background-color:#f0f2f6;padding:15px;border-radius:8px; }
    </style>
""", unsafe_allow_html=True)

# --- Data paths (live + historical) ---
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
LIVE_FILE = os.path.join(DATA_DIR, "live_sensor.jsonl")
HIST_FILE = os.path.join(DATA_DIR, "historical_months.json")

# --- Session state buffers ---
if 'sensor_data' not in st.session_state:
    st.session_state.sensor_data = []
if 'jsonl_offset' not in st.session_state:
    st.session_state.jsonl_offset = 0

# --- Live tail helpers (from visualization.py, adapted) ---
def tail_jsonl(path: str, offset: int):
    if not os.path.exists(path):
        return [], 0
    try:
        size = os.path.getsize(path)
    except OSError:
        return [], offset
    if offset > size:  # rotation
        offset = 0
    new_rows = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            f.seek(offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    new_rows.append(json.loads(line))
                except:
                    continue
            new_offset = f.tell()
    except:
        return [], offset
    return new_rows, new_offset

def drain_live():
    rows, new_off = tail_jsonl(LIVE_FILE, st.session_state.jsonl_offset)
    if rows:
        st.session_state.sensor_data.extend(rows)
        # cap buffer
        if len(st.session_state.sensor_data) > 30000:
            st.session_state.sensor_data = st.session_state.sensor_data[-30000:]
    st.session_state.jsonl_offset = new_off

# --- Synthetic bottling plant fallback (replaced) ---
@st.cache_data
def generate_bottling_plant_data(hours=24*30):
    """Generate hourly synthetic bottling plant data without inverter/diff model."""
    dates = pd.date_range(end=datetime.utcnow(), periods=hours, freq='H')
    rows = []
    for dt in dates:
        hour = dt.hour
        prod_factor = (0.8 + random.uniform(-0.05, 0.1)) if 6 <= hour <= 22 else random.uniform(0.1, 0.3)
        conveyor_kw = 5.0 * prod_factor + random.uniform(0.1, 0.5)
        co2_current_a = (3.0 * prod_factor + random.uniform(0.05, 0.3)) * 10  # scaled
        rinser_w = 2500 * prod_factor + random.uniform(100, 400)
        filler_j = (4500 * prod_factor + random.uniform(200, 600)) * 3600 / 1000.0
        capper_v = 230 + random.uniform(-5, 5)

        # Approx total instantaneous power (W)
        approx_voltage = 230.0
        load_power = conveyor_kw*1000 + rinser_w + co2_current_a * approx_voltage

        # Simple proportional energy flows (kWh per hour)
        interval_hours = 1.0
        base_kwh = load_power/1000.0 * interval_hours
        selfuse_energy = base_kwh * 0.7
        grid_consumption = base_kwh * 0.3
        exported_energy = 0.0
        yield_energy = selfuse_energy + exported_energy  # treat yield as on‑site usable

        bottles = int(load_power / 50 * random.uniform(0.9, 1.1))

        rows.append({
            "timestamp": dt,
            "conveyor_drive_motor_kw": conveyor_kw,
            "co2_pump_current_a": co2_current_a,
            "rinser_pump_power_w": rinser_w,
            "filler_servo_energy_j": filler_j,
            "capper_voltage_v": capper_v,
            "bottles_produced": bottles,
            "load_power": load_power,
            "exported_energy": exported_energy,
            "grid_consumption": grid_consumption,
            "selfuse_energy": selfuse_energy,
            "yield_energy": yield_energy
        })
    return pd.DataFrame(rows)


# --- Historical synthetic daily aggregates ---
def generate_historical(days_back=90):
    end = datetime.utcnow().date()
    start = end - timedelta(days=days_back)
    rng = pd.date_range(start=start, end=end, freq="D")
    out = []
    for d in rng:
        base = 400 + 50 * np.sin((d.timetuple().tm_yday % 30) * np.pi/15)
        exported = base * random.uniform(0.35, 0.55)
        selfuse = base * random.uniform(0.30, 0.45)
        grid_c = base * random.uniform(0.10, 0.25)
        yield_e = exported + selfuse
        out.append({
            "date": d.strftime("%Y-%m-%d"),
            "exported_energy": round(exported, 2),
            "selfuse_energy": round(selfuse, 2),
            "grid_consumption": round(grid_c, 2),
            "yield_energy": round(yield_e, 2)
        })
    return out

def ensure_historical():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(HIST_FILE):
        data = {"daily_history": generate_historical()}
        with open(HIST_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    with open(HIST_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("daily_history", [])

historical_daily = ensure_historical()
historical_df = pd.DataFrame(historical_daily)
if not historical_df.empty:
    historical_df['date'] = pd.to_datetime(historical_df['date']).dt.date

# --- Build DataFrame from live buffer (replaced) ---
def build_live_df():
    if not st.session_state.sensor_data:
        return None
    df = pd.DataFrame(st.session_state.sensor_data).copy()
    defaults = {
        'conveyor_drive_motor_kw': 0.0,
        'co2_pump_current_a': 0.0,
        'rinser_pump_power_w': 0.0,
        'filler_servo_energy_j': 0.0,
        'capper_voltage_v': 230.0,
        'timestamp': datetime.utcnow().isoformat()
    }
    for c, d in defaults.items():
        if c not in df.columns:
            df[c] = d
        df[c] = df[c].fillna(d)

    try:
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None)
    except:
        df['timestamp'] = pd.to_datetime(datetime.utcnow())

    # Interval inference (fallback 1 min)
    interval_hours = 1.0 / 60.0
    try:
        ts_sorted = df['timestamp'].sort_values()
        if len(ts_sorted) >= 2:
            dt_avg = (ts_sorted.iloc[-1] - ts_sorted.iloc[0]) / max(len(ts_sorted)-1, 1)
            interval_hours = max(dt_avg.total_seconds()/3600.0, 1.0/3600.0)
    except:
        pass

    approx_voltage = float(df['capper_voltage_v'].median() or 230.0)
    load_power = (
        df['conveyor_drive_motor_kw'] * 1000.0 +
        df['rinser_pump_power_w'] +
        df['co2_pump_current_a'] * approx_voltage
    )
    df['load_power'] = load_power

    # Simplified energy partition (no inverter/diff):
    base_kwh = load_power/1000.0 * interval_hours
    df['selfuse_energy'] = base_kwh * 0.7
    df['grid_consumption'] = base_kwh * 0.3
    df['exported_energy'] = 0.0
    df['yield_energy'] = df['selfuse_energy']  # treat yield as onsite usable

    df['bottles_produced'] = (load_power / 50.0 * np.random.uniform(0.9, 1.1, size=len(df))).astype(int)
    return df.sort_values('timestamp')

# --- Sidebar ---
with st.sidebar:
    st.title("Bottling Plant Monitor")
    st.markdown("---")
    st.subheader("Facility Info")
    facility = st.selectbox("Select Facility", ["Main Plant - Munich", "Bottling Line A", "Bottling Line B"])
    st.markdown("---")
    st.subheader("Time Range")
    time_range = st.selectbox("Select Period", ["Today", "Last 7 Days", "Last 30 Days", "This Month"])
    st.markdown("---")
    st.subheader("Production Line / Zone")
    zone_select = st.selectbox("Select Zone", ["Beverage Bottling Line", "Zone B", "Zone C"])
    st.markdown("---")
    live_enable = st.checkbox("Live update (1s)", value=True)
    st.caption("Streams new lines from data/live_sensor.jsonl when available.")


# --- Acquire data (live or synthetic) ---
drain_live()
df_live = build_live_df()

if df_live is None or df_live.empty:
    st.info("ℹ️ Demo Mode: Using synthetic bottling plant fallback (no live lines).")
    df = generate_bottling_plant_data()
else:
    # Removed success banner per request
    df = df_live

# Normalize and ensure columns exist
needed_cols = ['exported_energy', 'selfuse_energy', 'grid_consumption', 'yield_energy', 'load_power']
for c in needed_cols:
    if c not in df.columns:
        df[c] = 0.0

df['timestamp'] = pd.to_datetime(df['timestamp'])
df['date'] = df['timestamp'].dt.date

# Zone factor (scaling)
zone_factor_map = {"Beverage Bottling Line": 1.0, "Zone B": 1.0, "Zone C": 1.0}
zone_factor = zone_factor_map.get(zone_select, 1.0)

# CO2 factor
co2_factor = 0.233

# Slices
utc_today = datetime.utcnow().date()
today_data = df[df['date'] == utc_today]
this_month_data = df[df['timestamp'].dt.month == datetime.utcnow().month]

# --- Title ---
st.title("🏭 Beverage Bottling Plant Energy Dashboard")

# --- Key Metrics (extended) ---
yesterday_date = utc_today - timedelta(days=1)
yesterday_data = df[df['date'] == yesterday_date]

def pct_change(cur, prev):
    if prev == 0:
        return "N/A"
    return f"{(cur - prev)/prev*100:+.1f}% vs yesterday"

today_total_energy = today_data['yield_energy'].sum()  # production yield energy (kWh)
today_total_load_energy = today_data['selfuse_energy'].sum() + today_data['grid_consumption'].sum()
today_bottles = today_data['bottles_produced'].sum()

yesterday_total_energy = yesterday_data['yield_energy'].sum()
yesterday_bottles = yesterday_data['bottles_produced'].sum()

# Generic lightweight predictor using recent readings
def predict_next_recent(df_src: pd.DataFrame, column: str, window_points: int = 60) -> float:
    if df_src is None or df_src.empty or column not in df_src:
        return 0.0
    s = df_src.sort_values('timestamp')[column].astype(float).replace([np.inf, -np.inf], np.nan).dropna()
    if len(s) == 0:
        return 0.0
    if len(s) == 1:
        return float(s.iloc[-1])
    s_recent = s.iloc[-min(window_points, len(s)):]
    x = np.arange(len(s_recent))
    try:
        m, b = np.polyfit(x, s_recent.values, 1)
        pred = float(m * len(s_recent) + b)
        if np.isnan(pred) or np.isinf(pred):
            return float(s_recent.iloc[-1])
        return pred
    except Exception:
        return float(s_recent.iloc[-1])

# --- Lightweight prediction of Energy per Bottle (next interval) using recent points ---
def predict_energy_per_bottle_recent(df_src: pd.DataFrame, window_points: int = 24):
    if df_src is None or df_src.empty:
        return 0.0
    df_sorted = df_src.sort_values('timestamp').copy()
    df_sorted['cons_kwh'] = df_sorted['selfuse_energy'].fillna(0) + df_sorted['grid_consumption'].fillna(0)
    df_sorted['epb_wh'] = np.where(df_sorted['bottles_produced'] > 0,
                                   df_sorted['cons_kwh'] / df_sorted['bottles_produced'] * 1000.0, 0.0)
    s = df_sorted['epb_wh'].replace([np.inf, -np.inf], np.nan).dropna()
    if len(s) < 2:
        return float(s.iloc[-1]) if len(s) == 1 else 0.0
    s_recent = s.iloc[-min(window_points, len(s)):]
    x = np.arange(len(s_recent))
    try:
        m, b = np.polyfit(x, s_recent.values, 1)
        next_x = len(s_recent)
        pred = float(m * next_x + b)
        if np.isnan(pred) or np.isinf(pred):
            return float(s_recent.iloc[-1])
        return max(0.0, pred)
    except Exception:
        return float(s_recent.iloc[-1])

# Predictions for metrics
pred_yield_next_kwh = max(0.0, predict_next_recent(df, 'yield_energy', 120))
pred_load_next_kw = max(0.0, predict_next_recent(df, 'load_power', 120) / 1000.0)  # W -> kW
pred_bottles_next = max(0.0, predict_next_recent(df, 'bottles_produced', 120))
pred_epb_wh = predict_energy_per_bottle_recent(df)

col1, col2, col3, col4 = st.columns(4)
with col1:
    delta1 = f"{pct_change(today_total_energy, yesterday_total_energy)} | next ≈ {pred_yield_next_kwh:.2f} kWh"
    st.metric("Total Production Yield (kWh)", f"{today_total_energy:.2f}", delta1)
with col2:
    avg_power = (today_data['load_power'].mean()/1000.0) if not today_data.empty else 0
    delta2 = f"next ≈ {pred_load_next_kw:.2f} kW"
    st.metric("Average Load Power (kW)", f"{avg_power:.2f}", delta2)
with col3:
    delta3 = f"{pct_change(today_bottles, yesterday_bottles)} | next ≈ {pred_bottles_next:.0f}"
    st.metric("Bottles Produced Today", f"{today_bottles:,}", delta3)
with col4:
    energy_per_bottle = (today_total_load_energy / today_bottles * 1000) if today_bottles > 0 else 0
    delta4 = f"Efficiency | next ≈ {pred_epb_wh:.2f} Wh"
    st.metric("Energy per Bottle", f"{energy_per_bottle:.2f} Wh", delta4)

st.markdown("---")

# --- Real-Time Power (per-second vs yesterday hourly) ---
st.subheader("Real-Time Power")
def enhance_fluctuation(series: pd.Series):
    if series is None or series.empty:
        return series
    s = series.astype(float)
    if s.std() == 0 or (s.max() - s.min()) < 1e-6:
        scale = max(0.01, abs(s.mean())*0.01)
        jitter = np.random.normal(0.0, scale, len(s))
        return pd.Series(s.values + jitter, index=s.index)
    return s

now_naive = pd.Timestamp.utcnow().tz_localize(None)
recent_mask = df['timestamp'] >= (now_naive - pd.Timedelta(seconds=120))
recent_df = df[recent_mask].copy()

if not recent_df.empty:
    recent_df['second'] = recent_df['timestamp'].dt.floor('s')  # FIX: 'S' -> 's'
    sec_series = recent_df.groupby('second')['load_power'].mean().sort_index() * zone_factor / 1000.0
    sec_series = enhance_fluctuation(sec_series)
else:
    sec_series = pd.Series([], dtype=float)

# Create a simulated "previous 2-min baseline" for visual comparison
prev_sec_series = None
if len(sec_series) > 0:
    noise_scale = max(0.01, abs(sec_series.mean()) * 0.02)
    prev_sec_series = sec_series.rolling(5, min_periods=1).mean() * 0.97
    prev_sec_series = prev_sec_series + np.random.normal(0.0, noise_scale, len(prev_sec_series))

hours = list(range(24))
hour_labels = [f"{h:02d}:00" for h in hours]
yesterday_hourly = (df[df['date'] == (utc_today - timedelta(days=1))]
                    .groupby(df['timestamp'].dt.hour)['load_power']
                    .mean()
                    .reindex(hours, fill_value=0)/1000.0)

fig_power_seconds = go.Figure()
fig_power_seconds.add_trace(go.Scatter(
    x=sec_series.index, y=sec_series.values,
    name=f"{zone_select} (kW per-second)", line=dict(color='#f59e0b', width=3)
))
if prev_sec_series is not None:
    fig_power_seconds.add_trace(go.Scatter(
        x=prev_sec_series.index, y=prev_sec_series.values,
        name="Previous 2-min Baseline (simulated)",
        line=dict(color='#94a3b8', width=2, dash='dash'),
        opacity=0.9
    ))
fig_power_seconds.add_trace(go.Bar(
    x=hour_labels, y=yesterday_hourly.values,
    name="Yesterday Hourly Avg (kW)", marker_color='#6366f1', opacity=0.3
))
fig_power_seconds.update_layout(
    height=350, hovermode='x unified',
    xaxis_title="Recent Seconds & Yesterday Hours", yaxis_title="Power (kW)",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    template="plotly_white", paper_bgcolor="#f3f4f6", plot_bgcolor="#f3f4f6"
)
st.plotly_chart(fig_power_seconds, width="stretch")  # FIX: use_container_width -> width
#st.caption("Comparing real-time load with a simulated previous 2‑minute baseline and yesterday’s hourly average.")

# Helper: device energy computation (place before any usage)
def device_energy_kwh(df_sel: pd.DataFrame):
    if df_sel is None or df_sel.empty:
        return [0]*5
    approx_voltage = max(df_sel['capper_voltage_v'].median() if 'capper_voltage_v' in df_sel else 230, 1)
    conv_kwh = (df_sel['conveyor_drive_motor_kw'] * 1.0).sum()
    co2_kwh = (df_sel['co2_pump_current_a'] * approx_voltage / 1000.0).sum()
    rinser_kwh = (df_sel['rinser_pump_power_w'] / 1000.0).sum()
    filler_kwh = (df_sel['filler_servo_energy_j'] / 3600.0 / 1000.0).sum()  # joules-ish approx to kWh
    capper_kwh = (approx_voltage * 0.2 * len(df_sel) / 1000.0)  # placeholder
    return [conv_kwh, co2_kwh, rinser_kwh, filler_kwh, capper_kwh]

# Device consumption pie chart + Energy grid side-by-side
st.markdown("---")
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Device Power Distribution (This Month)")
    # Ensure labels/columns are defined
    device_names = [
        "Conveyor Drive Motor", "CO₂ Pump", "Rinser Pump",
        "Filler Carousel Servo", "Capper Motor Pack"
    ]
    device_columns_live = [
        "conveyor_drive_motor_kw",
        "co2_pump_current_a",
        "rinser_pump_power_w",
        "filler_servo_energy_j",
        "capper_voltage_v"
    ]
    device_totals = [this_month_data[col].sum() for col in device_columns_live]
    fig_pie = go.Figure(data=[go.Pie(
        labels=device_names,
        values=device_totals,
        marker=dict(colors=['#ef4444', '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6'])
    )])
    fig_pie.update_traces(textinfo='percent+label', pull=[0.02, 0, 0, 0, 0])
    fig_pie.update_layout(height=360, template="plotly_white", margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig_pie, width="stretch")

with col_right:
    st.subheader("Device Energy Consumption Grid")
    box_kwh = 10
    max_kwh = 200  # reduce for faster redraw
    max_boxes = int(max_kwh/box_kwh)
    green_boxes = int(60/box_kwh)
    yellow_boxes = int(120/box_kwh)

    # Robust aggregation
    df_month_clean = this_month_data.replace([np.inf, -np.inf], np.nan).fillna(0)
    device_values = device_energy_kwh(df_month_clean)

    z_matrix, hover_text = [], []
    for i, val in enumerate(device_values):
        val = float(val) if np.isfinite(val) else 0.0
        row, h_row = [], []
        boxes = max(0, min(int(round(val / box_kwh)), max_boxes))
        for b in range(max_boxes):
            if b < boxes:
                if b < green_boxes:
                    row.append(1); color_label = "Green"
                elif b < yellow_boxes:
                    row.append(2); color_label = "Yellow"
                else:
                    row.append(3); color_label = "Red"
                h_row.append(f"{device_names[i]}: {(b+1)*box_kwh:.0f} kWh ({color_label})")
            else:
                row.append(0); h_row.append(f"{device_names[i]}: 0 kWh")
        z_matrix.append(row)
        hover_text.append(h_row)

    colorscale = [
        [0, '#2a2a2a'], [0.25, '#2a2a2a'],
        [0.25, '#22c55e'], [0.5, '#22c55e'],
        [0.5, '#fbbf24'], [0.75, '#fbbf24'],
        [0.75, '#dc2626'], [1, '#dc2626']
    ]

    fig_grid = go.Figure()
    fig_grid.add_trace(go.Heatmap(
        z=z_matrix,
        text=hover_text,
        hovertemplate='%{text}<extra></extra>',
        colorscale=colorscale,
        showscale=False,
        xgap=1, ygap=1
    ))

    # Remove per-cell annotations; use device total labels on y-axis
    totals_labels = [f"{name} ({val:.1f} kWh)" for name, val in zip(device_names, device_values)]
    fig_grid.update_yaxes(
        tickmode='array',
        tickvals=list(range(len(device_names))),
        ticktext=totals_labels,
        side='left'
    )
    fig_grid.update_xaxes(title="Energy (kWh boxes)", visible=True, range=[-0.5, max_boxes - 0.5])

    fig_grid.update_layout(
        height=360,
        margin=dict(l=60, r=20, t=20, b=40),
        template='plotly_dark',
        plot_bgcolor="#fffafa",
        paper_bgcolor="#fffefe",
        font=dict(color='white', size=11)
    )
    st.plotly_chart(fig_grid, width="stretch")


# Device-specific analysis
st.markdown("---")
col_device, col_notification = st.columns(2)

with col_device:
    st.subheader("Real-Time Device Power Monitoring")
    selected_device = st.selectbox(
        "Select Device",
        device_names
    )

    device_columns = device_columns_live  # FIX: ensure variable exists
    device_idx = device_names.index(selected_device)
    device_col = device_columns[device_idx]
    
    st.markdown("**Today's Hourly Power**")
    
    today_hourly_device = today_data.copy()
    
    fig_device = go.Figure()
    
    fig_device.add_trace(go.Scatter(
        x=today_hourly_device['timestamp'],
        y=today_hourly_device[device_col],
        name=f'{selected_device} Power (kW)',
        mode='lines',
        line=dict(color='#3b82f6', width=2),
        fill='tozeroy'
    ))
    
    fig_device.update_layout(
        height=300,
        title=f"{selected_device} - Power vs Time",
        xaxis_title="Time",
        yaxis_title="Power (kW)",
        hovermode='x unified',
        template="plotly_white"
    )
    
    st.plotly_chart(fig_device, width="stretch")  # FIX

with col_notification:
    st.subheader("⚠️ Alerts & Notifications")
    power_threshold = st.number_input(
        "Set Power Peak Limit (kW)",
        min_value=1.0,
        max_value=30.0,
        value=15.0,
        step=0.5,
        help="Alert when total power consumption exceeds this limit"
    )
    today_analysis = today_data.copy()
    # FIX: use existing load_power (kW) instead of missing total_power_kw
    peaks = today_analysis[today_analysis['load_power']/1000.0 > power_threshold].copy()
    if len(peaks) > 0:
        st.warning(f"🚨 **{len(peaks)} Peak Power Events Detected**")
        for idx, peak in peaks.head(5).iterrows():
            peak_time = peak['timestamp'].strftime("%H:%M")
            peak_power = peak['load_power']/1000.0  # kW
            device_columns = device_columns_live
            device_powers = [peak[col] for col in device_columns]
            primary_device = device_names[device_powers.index(max(device_powers))]
            st.info(
                f"⚡ **Power Peak Alert**\n\n"
                f"**Time**: {peak_time}\n"
                f"**Current Power**: {peak_power:.2f} kW\n"
                f"**Threshold**: {power_threshold:.2f} kW\n"
                f"**Primary Device**: {primary_device}\n"
                f"**Excess**: {peak_power - power_threshold:.2f} kW"
            )
    else:
        st.success(f"✅ All power consumption within limit ({power_threshold:.2f} kW)")

# --- Historical Aggregation Explorer (dropdown) ---
st.markdown("---")
with st.expander("📦 Historical Aggregation Explorer", expanded=False):

    agg_choice = st.selectbox(
        "Aggregation Level",
        ["Daily", "Weekly", "Monthly", "Compare Current vs Previous Month"],
        help="Choose how to aggregate energy flows."
    )

    if historical_df.empty:
        st.warning("No historical data available.")
    else:
        hist = historical_df.copy()

        def summarize(df_in, by):
            if by == "Daily":
                df_in['period'] = df_in['date']
            elif by == "Weekly":
                df_in['period'] = pd.to_datetime(df_in['date']).dt.to_period("W").apply(lambda p: p.start_time.date())
            elif by == "Monthly":
                df_in['period'] = pd.to_datetime(df_in['date']).dt.to_period("M").apply(lambda p: p.start_time.date())
            grouped = df_in.groupby('period').agg({
                'exported_energy': 'sum',      # Grid Export
                'selfuse_energy': 'sum',       # Internal Use
                'grid_consumption': 'sum',     # Grid Import
                'yield_energy': 'sum'          # Production Yield
            }).reset_index()
            return grouped

        if agg_choice in ["Daily", "Weekly", "Monthly"]:
            g = summarize(hist.copy(), agg_choice)
            fig_hist_agg = go.Figure()
            fig_hist_agg.add_trace(go.Bar(x=g['period'], y=g['yield_energy'], name="Conveyor Drive", marker_color="#6366f1"))
            fig_hist_agg.add_trace(go.Bar(x=g['period'], y=g['selfuse_energy'], name="CO2 Pump", marker_color="#10b981"))
            fig_hist_agg.add_trace(go.Bar(x=g['period'], y=g['grid_consumption'], name="Capper Voltage", marker_color="#f87171"))
            fig_hist_agg.add_trace(go.Bar(x=g['period'], y=g['exported_energy'], name="Filler Servo Energy", marker_color="#fbbf24"))
            fig_hist_agg.update_layout(
                barmode='stack', height=380,
                xaxis_title=agg_choice, yaxis_title="Energy (kWh)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                template="plotly_white"
            )
            st.plotly_chart(fig_hist_agg, width="stretch")

            total_row = {
                "Production Yield": g['yield_energy'].sum(),
                "Internal Use": g['selfuse_energy'].sum(),
                "Grid Import": g['grid_consumption'].sum(),
                "Grid Export": g['exported_energy'].sum()
            }
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Production Yield", f"{total_row['Production Yield']:.1f} kWh")
            c2.metric("Internal Use", f"{total_row['Internal Use']:.1f} kWh")
            c3.metric("Grid Import", f"{total_row['Grid Import']:.1f} kWh")
            c4.metric("Grid Export", f"{total_row['Grid Export']:.1f} kWh")

        else:  # Compare Current vs Previous Month
            current_month = datetime.utcnow().month
            prev_month = (datetime.utcnow().replace(day=1) - timedelta(days=1)).month
            cur_df = hist[pd.to_datetime(hist['date']).dt.month == current_month]
            prev_df = hist[pd.to_datetime(hist['date']).dt.month == prev_month]
            cur_sum = cur_df[['exported_energy','selfuse_energy','grid_consumption','yield_energy']].sum()
            prev_sum = prev_df[['exported_energy','selfuse_energy','grid_consumption','yield_energy']].sum()

            fig_cmp = go.Figure()
            metrics = ['yield_energy','selfuse_energy','grid_consumption','exported_energy']
            labels = {
                'yield_energy':'Production Yield',
                'selfuse_energy':'Internal Use',
                'grid_consumption':'Grid Import',
                'exported_energy':'Grid Export'
            }
            fig_cmp.add_trace(go.Bar(
                x=[labels[m] for m in metrics], y=[cur_sum[m] for m in metrics],
                name="Current Month", marker_color="#3b82f6"
            ))
            fig_cmp.add_trace(go.Bar(
                x=[labels[m] for m in metrics], y=[prev_sum[m] for m in metrics],
                name="Previous Month", marker_color="#94a3b8"
            ))
            fig_cmp.update_layout(
                barmode='group', height=380,
                xaxis_title="Metric", yaxis_title="Energy (kWh)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                template="plotly_white"
            )
            st.plotly_chart(fig_cmp, width="stretch")

           
# --- Footer / System Info ---
st.markdown("---")
# --- Added CO2 & Cost Metrics + Tomorrow Predictions ---
grid_today = today_data['grid_consumption'].sum()
exported_today = today_data['exported_energy'].sum()
selfuse_today = today_data['selfuse_energy'].sum()

co2_emissions_today = grid_today * co2_factor              # kg CO2 emitted from grid energy
co2_avoided_today = (selfuse_today + exported_today) * co2_factor  # assume self-use/export offsets grid
# Tariffs / rates (adjust as needed)
grid_rate = 0.22          # €/kWh cost from grid
export_rate = 0.08        # €/kWh revenue for exported energy
internal_value_rate = 0.22 # €/kWh value of self-use (avoided purchase)

baseline_cost_if_all_grid = (grid_today + selfuse_today + exported_today) * grid_rate
actual_cost_today = grid_today * grid_rate - exported_today * export_rate  # self-use offsets purchase
net_cost_today = actual_cost_today  # already net of export revenue
cost_saved_today = baseline_cost_if_all_grid - actual_cost_today

# Daily aggregates for prediction
daily_agg = (df.groupby('date')
               .agg({'yield_energy':'sum',
                     'grid_consumption':'sum',
                     'selfuse_energy':'sum',
                     'exported_energy':'sum'})
               .sort_index())

def _predict_next(series: pd.Series) -> float:
    s = series.dropna()
    if len(s) == 0:
        return 0.0
    if len(s) == 1:
        return float(s.iloc[-1])
    x = np.arange(len(s))
    try:
        m, b = np.polyfit(x, s.values, 1)
        return max(0.0, float(m * len(s) + b))
    except:
        return float(s.iloc[-1])

pred_yield_daily_next = _predict_next(daily_agg['yield_energy'])        # kWh
pred_grid_daily_next = _predict_next(daily_agg['grid_consumption'])     # kWh

# Use today's proportional split to estimate self-use & export tomorrow
if today_total_energy > 0:
    selfuse_ratio = selfuse_today / today_total_energy
    export_ratio = exported_today / today_total_energy
else:
    selfuse_ratio = export_ratio = 0.0

pred_selfuse_next = pred_yield_daily_next * selfuse_ratio
pred_export_next = pred_yield_daily_next * export_ratio
pred_co2_next = pred_grid_daily_next * co2_factor
pred_net_cost_next = (pred_grid_daily_next * grid_rate) - (pred_export_next * export_rate)

# Replace the 5-column block with a 4-column block combining today's CO₂ and tomorrow's predicted CO₂
colc1, colc2, colc3 = st.columns(3)
with colc1:
    # Combined: today's CO₂ as value, tomorrow's predicted CO₂ in delta
    st.metric("CO₂ Emissions Today", f"{co2_emissions_today:.1f} kg", f"Tomorrow ≈ {pred_co2_next:.1f} kg")
with colc2:
    st.metric("Net Energy Cost Today", f"€{net_cost_today:.2f}", f"Saved €{cost_saved_today:.2f}")
with colc3:
    st.metric("Predicted Net Cost Tomorrow", f"€{pred_net_cost_next:.2f}", f"Yield ≈ {pred_yield_daily_next:.1f} kWh")
