import os

ASSISTANT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ensure_dirs():
    os.makedirs(os.path.join(ASSISTANT_DIR, "memory"), exist_ok=True)
    os.makedirs(os.path.join(ASSISTANT_DIR, "traces"), exist_ok=True)
