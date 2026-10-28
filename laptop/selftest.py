"""Run local contract tests and real SUMO against the original API and semantic view."""
import argparse
import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx

from .controller import parser, run
from .network import build, load

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def server(target, output, env=None, factory=False):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    command = [sys.executable, "-m", "uvicorn", target, "--host", "127.0.0.1", "--port", str(port)]
    if factory:
        command.append("--factory")
    with output.open("w") as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            url = f"http://127.0.0.1:{port}"
            with httpx.Client(trust_env=False) as http:
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError(f"Local test service exited; see {output}")
                    try:
                        if http.get(url + "/health", timeout=0.5).status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError(f"Local service did not become ready; see {output}")
            yield url
        finally:
            process.terminate()
            process.wait(timeout=10)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", default="runs/local-verification")
    args = cli.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    build()
    network_id = load()[1]
    build()
    if load()[1] != network_id:
        raise RuntimeError("Repeated network generation changed its fingerprint")
    subprocess.run([sys.executable, "-m", "pytest", "tests", "-q", "--tb=short",
                    "--junitxml", str(output / "tests.xml")], cwd=ROOT, check=True)
    with server("mec.baseline.main:app", output / "baseline.log") as url:
        options = parser().parse_args(["--mec-url", url, "--mode", "local", "--pace", "0",
                                       "--output", str(output / "direct")])
        run(options)
        with server("mec.semantic_view:create_app", output / "view.log",
                    env={**os.environ, "ALIVEMAP_UPSTREAM": url}, factory=True) as view:
            options.semantics_url = view + "/semantics"
            options.output = str(output / "with-view")
            run(options)


if __name__ == "__main__":
    main()
