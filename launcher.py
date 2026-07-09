from __future__ import annotations

import subprocess
import sys
import time


def main() -> None:
    while True:
        print("Launching MomentumMaster...")
        process = subprocess.Popen([sys.executable, "main.py"])
        exit_code = process.wait()
        if exit_code == 0:
            print("MomentumMaster exited cleanly.")
            break
        print(f"MomentumMaster crashed with exit code {exit_code}. Restarting in 30 seconds.")
        time.sleep(30)


if __name__ == "__main__":
    main()
