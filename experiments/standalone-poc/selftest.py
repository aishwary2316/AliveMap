"""Real local HTTP server + SUMO process acceptance run. No MEC server required."""
import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from controller import parser, run
from network import ROOT, build, load


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", default="runs/local-test")
    args = cli.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    build()
    network_id = load()[1]
    build()
    if load()[1] != network_id:
        raise RuntimeError("Repeated builds changed the network fingerprint")
    subprocess.run([sys.executable, "-m", "pytest", "-q", "--tb=short", "test_system.py",
                    "--junitxml", str(output / "tests.xml")], cwd=ROOT, check=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    token = secrets.token_urlsafe(32)
    env = {**os.environ, "POC_TOKEN": token, "POC_DB": str(output / "mec.sqlite3")}
    with (output / "mec.log").open("w") as log:
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "mec_api:create_app", "--factory",
                                    "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT,
                                   env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            url = f"http://127.0.0.1:{port}"
            with httpx.Client(trust_env=False) as http:
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError("Local server failed; see mec.log")
                    try:
                        if http.get(url + "/health", timeout=0.3).status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError("Local server did not become ready")
            options = parser().parse_args(["--mec-url", url, "--token", token,
                                           "--output", str(output), "--pace", "0"])
            run(options)
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
