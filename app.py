"""
FreshGuard - Launch Entrypoint
GDGoC HITAM Agentic AI Hackathon - Problem Statement 2: Zero-Waste Grocery
"""

import sys
import os
import webbrowser
import threading
import time

from freshguard_db import init_db, seed_data
from server import run_server, PORT

def open_browser():
    time.sleep(1.2)
    url = f"http://localhost:{PORT}"
    print(f"Opening FreshGuard in your default browser: {url}")
    webbrowser.open(url)

def main():
    print("Initializing FreshGuard SQLite Database & Perishable Seed Data...")
    init_db()
    seed_data(force=False)
    
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT

    # Auto-open browser in background thread
    threading.Thread(target=open_browser, daemon=True).start()

    run_server(port)

if __name__ == "__main__":
    main()
