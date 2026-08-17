import os

# Must be set before anything imports app.config, which reads this at import time.
os.environ.setdefault("INPUT_BACKEND", "simulation")
