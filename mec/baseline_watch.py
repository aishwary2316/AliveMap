"""Keep the reviewed baseline available without replacing existing processes.

Linux systemd helper. Source, environment and unrelated services stay untouched.
An existing healthy API is monitored; only an absent baseline is started.
"""
import argparse
import hashlib
import json
import socket
import subprocess
import time
from pathlib import Path
from urllib.request import build_opener, ProxyHandler

BASELINE_SHA256 = '45a06e0e9496df0cb2f9a80f330f6da998c787aba3df4c67d8d37407a13708c5'


def healthy():
    try:
        with build_opener(ProxyHandler({})).open('http://127.0.0.1:8765/health', timeout=3) as response:
            data = json.load(response)
        if data.get('status') != 'ok' or data.get('service') != 'mec-av-poc':
            raise RuntimeError('Port 8765 serves an unexpected application; refusing changes')
        return True
    except OSError:
        return False


def start_if_absent(baseline, process_root=Path('/proc')):
    baseline = Path(baseline).resolve()
    if hashlib.sha256((baseline/'main.py').read_bytes()).hexdigest() != BASELINE_SHA256:
        raise RuntimeError('Baseline source changed; refusing automatic startup')
    if healthy():
        return None
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', 8765)) == 0:
            raise RuntimeError('Port 8765 occupied but unhealthy; no process stopped')
    for entry in process_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            argv = (entry/'cmdline').read_bytes().split(b'\0')
            if (entry/'cwd').resolve() == baseline and b'main:app' in argv and any(b'uvicorn' in arg for arg in argv):
                raise RuntimeError('Existing baseline process has no healthy listener; refusing duplication')
        except OSError:
            continue
    return subprocess.Popen([str(baseline/'.venv/bin/python'), '-m', 'uvicorn', 'main:app',
                             '--host', '127.0.0.1', '--port', '8765', '--workers', '1'],
                            cwd=baseline, stdin=subprocess.DEVNULL)


def watch(baseline, lock_path):
    import fcntl
    path = Path(lock_path)
    with path.open('a') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        child = start_if_absent(baseline)
        try:
            if child is not None:
                wait_ready(child)
            while True:
                if child is not None and child.poll() is not None:
                    raise RuntimeError('Owned baseline process exited; systemd will retry startup')
                if not healthy():
                    if child is not None:
                        raise RuntimeError('Owned baseline unhealthy; service restart required')
                    child = start_if_absent(baseline)
                    if child is not None:
                        wait_ready(child)
                time.sleep(3)
        finally:
            # Only a child created by this service is ours to stop.
            if child is not None and child.poll() is None:
                child.terminate()
                child.wait(timeout=10)


def wait_ready(child):
    for _ in range(30):
        if healthy():
            return
        if child.poll() is not None:
            raise RuntimeError('Baseline exited during startup')
        time.sleep(0.5)
    raise RuntimeError('Baseline startup health timeout')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--lock', required=True)
    options = parser.parse_args()
    watch(options.baseline, options.lock)
