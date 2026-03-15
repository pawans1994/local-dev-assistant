import os

def ensure_dirs():
    os.makedirs("memory", exist_ok=True)
    os.makedirs("traces", exist_ok=True)