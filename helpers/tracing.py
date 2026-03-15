import json
import time

TRACE_FILE = f"traces/run_{int(time.time())}.json"
trace_data = []

def trace_event(event_type, data):
    trace_data.append({
        "type": event_type,
        "data": data
    })

def save_trace():
    global trace_data, TRACE_FILE

    with open(TRACE_FILE, "w") as f:
        json.dump(trace_data, f, indent=2)

    trace_data = []
    TRACE_FILE = f"traces/run_{int(time.time())}.json"