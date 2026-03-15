import os
import json
from datetime import datetime


def ensure_trace_dir():
    os.makedirs("traces", exist_ok=True)


def save_trace(trace):
    ensure_trace_dir()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"traces/run_{timestamp}.json"

    with open(path, "w") as f:
        json.dump(trace, f, indent=2)

    return path