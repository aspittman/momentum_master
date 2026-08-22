from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
CONFIGURATION_ERROR_EXIT_CODE = 78
ALREADY_RUNNING_EXIT_CODE = 73


def main() -> None:
    while True:
        print("Launching MomentumMaster...", flush=True)
        process = subprocess.Popen([sys.executable, str(BASE_DIR / "main.py")], cwd=BASE_DIR)
        exit_code = process.wait()
        if exit_code == 0:
            print("MomentumMaster exited cleanly.")
            break
        if exit_code == CONFIGURATION_ERROR_EXIT_CODE:
            print("MomentumMaster stopped because configuration is incomplete. Fix .env and run again.")
            break
        if exit_code == ALREADY_RUNNING_EXIT_CODE:
            print("MomentumMaster stopped because another instance is already running.")
            break
        print(f"MomentumMaster crashed with exit code {exit_code}. Restarting in 30 seconds.")
        time.sleep(30)


if __name__ == "__main__":
    main()
