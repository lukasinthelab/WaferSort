"""
WaferSort launcher — handles browser compatibility automatically.

Usage:
    python run.py              # default (Unicode labels)
    python run.py --ascii      # force ASCII labels (for Safari/older browsers)
    python run.py --mac        # shortcut: same as --ascii (most Macs use Safari)
"""

import subprocess
import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description="Launch WaferSort")
    parser.add_argument("--ascii", action="store_true",
                        help="Use ASCII-safe column labels (for Safari/older browsers)")
    parser.add_argument("--mac", action="store_true",
                        help="Shortcut for --ascii (Safari is the default Mac browser)")
    parser.add_argument("--port", type=int, default=8501,
                        help="Port to run on (default: 8501)")
    args = parser.parse_args()

    use_ascii = args.ascii or args.mac
    query = "?ascii=1" if use_ascii else ""
    url = f"http://localhost:{args.port}/{query}"

    print(f"Starting WaferSort at {url}")
    if use_ascii:
        print("(ASCII mode — Safari-compatible labels)")

    cmd = [
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.headless", "true",
        "--server.port", str(args.port),
        "--browser.serverAddress", "localhost",
    ]

    # Open the browser with the correct URL (including query params)
    if use_ascii:
        # Disable auto-open so we can open with the right URL
        cmd += ["--server.enableStaticServing", "true"]
        import webbrowser
        import threading
        threading.Timer(2.0, webbrowser.open, args=[url]).start()

    subprocess.run(cmd)


if __name__ == "__main__":
    main()
