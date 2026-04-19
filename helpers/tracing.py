import json
import time
import os

ASSISTANT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_traces_dir = os.path.join(ASSISTANT_DIR, "traces")

_trace_file = os.path.join(_traces_dir, f"run_{int(time.time())}.json")
trace_data = []


def trace_event(event_type: str, data):
    trace_data.append({
        "type": event_type,
        "ts": time.time(),
        "data": data,
    })


def save_trace():
    global trace_data, _trace_file
    os.makedirs(_traces_dir, exist_ok=True)
    with open(_trace_file, "w") as f:
        json.dump(trace_data, f, indent=2)
    trace_data = []
    _trace_file = os.path.join(_traces_dir, f"run_{int(time.time())}.json")
