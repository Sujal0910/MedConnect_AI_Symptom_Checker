# Gunicorn configuration file
import multiprocessing

# Server settings
bind = "0.0.0.0:10000"  # Render will connect to this port
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"  # <-- THIS IS THE FIX
preload_app = True

