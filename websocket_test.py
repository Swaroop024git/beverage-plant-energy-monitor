import asyncio
import websockets
import json
import streamlit as st
import os
from datetime import datetime

ROS_WS_URI = "ws://localhost:9090"
TOPIC = "/bottling_energy"

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DATA_FILE = os.path.join(DATA_DIR, "live_sensor.jsonl")

st.set_page_config(page_title="ROS2 WebSocket Data Viewer", layout="centered")

st.title("🔌 ROS2 WebSocket Data Monitor")
status_box = st.empty()
data_box = st.empty()

# Ensure buffer exists for visualization.py
if 'sensor_data' not in st.session_state:
    st.session_state.sensor_data = []

# Ensure data directory
os.makedirs(DATA_DIR, exist_ok=True)

def append_jsonl(record: dict, path: str):
    """Append one JSON object per line, using atomic write."""
    line = json.dumps(record, ensure_ascii=False)
    tmp = f"{path}.tmp"
    # Create file if missing
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            pass
    # Append safely
    with open(tmp, "w", encoding="utf-8") as ftmp:
        ftmp.write(line + "\n")
    # Append tmp to main file
    with open(path, "a", encoding="utf-8") as f:
        with open(tmp, "r", encoding="utf-8") as ftmp_read:
            f.write(ftmp_read.read())
    try:
        os.remove(tmp)
    except OSError:
        pass

async def rosbridge_listener():
    try:
        async with websockets.connect(ROS_WS_URI) as ws:
            status_box.success("Connected to rosbridge on ws://localhost:9090")

            subscribe_msg = {
                "op": "subscribe",
                "topic": TOPIC,
                "type": "std_msgs/msg/String",  # ROS2 type path
            }
            await ws.send(json.dumps(subscribe_msg))

            while True:
                raw_msg = await ws.recv()
                parsed = json.loads(raw_msg)

                # Show only the YAML/JSON data inside msg.data
                content = None
                if isinstance(parsed, dict) and "msg" in parsed:
                    content = parsed["msg"].get("data", "")
                else:
                    content = parsed

                # Display for debugging
                data_box.code(content if isinstance(content, str) else json.dumps(content, indent=2))

                # Normalize into a dict payload for visualization.py buffer
                if isinstance(content, str):
                    # Try JSON first, then simple line-based YAML
                    try:
                        payload = json.loads(content)
                    except Exception:
                        # Parse "key: value" lines
                        payload = {}
                        for line in content.splitlines():
                            if ":" in line:
                                k, v = line.split(":", 1)
                                payload[k.strip()] = v.strip()
                elif isinstance(content, dict):
                    payload = content
                else:
                    payload = {}

                # Coerce types and ensure timestamp
                def to_float(x, default=0.0):
                    try:
                        return float(x)
                    except Exception:
                        return default

                normalized = {
                    "conveyor_drive_motor_kw": to_float(payload.get("conveyor_drive_motor_kw", 0.0)),
                    "co2_pump_current_a": to_float(payload.get("co2_pump_current_a", 0.0)),
                    "rinser_pump_power_w": to_float(payload.get("rinser_pump_power_w", 0.0)),
                    "filler_servo_energy_j": to_float(payload.get("filler_servo_energy_j", 0.0)),
                    "capper_voltage_v": to_float(payload.get("capper_voltage_v", 0.0)),
                    "anomaly_flag": str(payload.get("anomaly_flag", "")).strip(),
                    # Force live timestamp for visualization movement
                    "timestamp": datetime.utcnow().isoformat(),
                }

                # Write to file so visualization.py can read
                append_jsonl(normalized, DATA_FILE)

                # Append to shared buffer for visualization.py
                st.session_state.sensor_data.append(normalized)
                # Keep buffer bounded
                if len(st.session_state.sensor_data) > 5000:
                    st.session_state.sensor_data = st.session_state.sensor_data[-5000:]

    except Exception as e:
        status_box.error(f"❌ Connection Failed: {e}")

def start_listener():
    """Runs the websocket listener safely inside Streamlit."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(rosbridge_listener())

# Run once when Streamlit loads
start_listener()
