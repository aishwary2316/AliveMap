"""Build a guarded additive deployment; SSH connection remains interactive."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def package(recover_baseline=False):
    source = (ROOT/'mec/playground_api.py').read_text(encoding='utf-8').replace('\r\n', '\n')
    digest = hashlib.sha256(source.encode()).hexdigest()
    baseline = hashlib.sha256((ROOT/'mec/baseline/main.py').read_bytes()).hexdigest()
    delimiter = 'ALIVEMAP_SOURCE_'+digest[:16]
    recovery = '''"$legacy_dir/.venv/bin/python" - "$legacy_dir" <<'ALIVEMAP_RECOVER_BASELINE'
import fcntl, json, os, socket, subprocess, sys, time
from pathlib import Path
from urllib.request import build_opener, ProxyHandler
legacy = Path(sys.argv[1]).resolve()
runtime = Path.home()/"alivemap-playground/runtime"
runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
opener = build_opener(ProxyHandler({}))
def health():
    with opener.open("http://127.0.0.1:8765/health", timeout=2) as response:
        data = json.load(response)
    if data.get("status") != "ok" or data.get("service") != "mec-av-poc":
        raise SystemExit("STOP: port 8765 is not the reviewed MEC API")
    return data
with (runtime/"baseline-start.lock").open("a") as guard:
    fcntl.flock(guard, fcntl.LOCK_EX)
    try:
        ready = health()
    except (OSError, ValueError):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", 8765)) == 0:
                raise SystemExit("STOP: port 8765 occupied but unhealthy; no process stopped")
        # A stopped/starting process must be inspected, not duplicated.
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                argv = (entry/"cmdline").read_bytes().split(b"\\0")
                cwd = (entry/"cwd").resolve()
                if cwd == legacy and b"main:app" in argv and any(b"uvicorn" in arg for arg in argv):
                    raise SystemExit("STOP: existing baseline process has no healthy listener; inspection required")
            except (OSError, RuntimeError):
                continue
        command = [str(legacy/".venv/bin/python"), "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8765"]
        with (runtime/"baseline-recovery.log").open("ab", buffering=0) as log:
            process = subprocess.Popen(command, cwd=legacy, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        print("Started the unchanged baseline API; PID", process.pid, flush=True)
        for attempt in range(30):
            try:
                ready = health()
                break
            except (OSError, ValueError):
                if process.poll() is not None:
                    raise SystemExit("Baseline exited; inspect ~/alivemap-playground/runtime/baseline-recovery.log")
                time.sleep(0.5)
        else:
            raise SystemExit("Baseline health timeout; inspect process/log before retrying; nothing killed")
    print("BASELINE_READY", json.dumps(ready), flush=True)
ALIVEMAP_RECOVER_BASELINE
''' if recover_baseline else ''
    script = f'''set -eu
legacy_dir="$HOME/mec-av-poc"
test "$(sha256sum "$legacy_dir/main.py" | cut -d ' ' -f 1)" = '{baseline}' || {{ echo 'STOP: original source changed'; exit 1; }}
test -x "$legacy_dir/.venv/bin/python"
test -z "$(ss -H -ltn 'sport = :8767')" || {{ echo 'STOP: port 8767 occupied; nothing stopped'; exit 1; }}
umask 077
{recovery}\
curl --noproxy '*' --fail --silent --show-error --max-time 5 http://127.0.0.1:8765/health
"$legacy_dir/.venv/bin/python" -c 'import h3,fastapi,pydantic; assert hasattr(h3,"h3shape_to_cells_experimental"); print("Dependencies ready",h3.__version__)'
umask 077
deploy_dir="$HOME/alivemap-playground/{digest[:16]}-utf8"
mkdir -p "$deploy_dir"
if test -f "$deploy_dir/playground_api.py"; then
    test "$(sha256sum "$deploy_dir/playground_api.py" | cut -d ' ' -f 1)" = '{digest}' || {{ echo 'STOP: existing extension differs'; exit 1; }}
else
    cat > "$deploy_dir/playground_api.py" <<'{delimiter}'
{source}{delimiter}
fi
test "$(sha256sum "$deploy_dir/playground_api.py" | cut -d ' ' -f 1)" = '{digest}' || {{ echo 'STOP: uploaded source checksum mismatch; check UTF-8 transport'; exit 1; }}
echo 'Starting additive playground API on 127.0.0.1:8767. Original API is unchanged.'
echo 'Keep this window open. Tower coverage is simulated; this process performs MEC H3 and delivery decisions.'
exec env ALIVEMAP_LEGACY_URL=http://127.0.0.1:8765 "$legacy_dir/.venv/bin/python" -m uvicorn playground_api:app --app-dir "$deploy_dir" --host 127.0.0.1 --port 8767
'''
    target = ROOT/'.local/deploy-playground.sh'
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(script.encode())
    print('Prepared guarded playground deployment; source SHA256='+digest)
    return target


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recover-baseline', action='store_true', help='Start the reviewed baseline only if absent; never stop/replace a process')
    package(parser.parse_args().recover_baseline)
