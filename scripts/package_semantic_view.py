"""Prepare a reviewable, guarded, additive deployment script; makes no connection."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def package():
    source = (ROOT / "mec/semantic_view.py").read_text(encoding="utf-8").replace("\r\n", "\n")
    digest = hashlib.sha256(source.encode()).hexdigest()
    baseline = hashlib.sha256((ROOT / "mec/baseline/main.py").read_bytes()).hexdigest()
    delimiter = "ALIVEMAP_SOURCE_" + digest[:16]
    script = f'''set -eu
legacy_dir="$HOME/mec-av-poc"
expected_baseline='{baseline}'
actual_baseline=$(sha256sum "$legacy_dir/main.py" | cut -d ' ' -f 1)
if test "$actual_baseline" != "$expected_baseline"; then
    echo 'STOP: existing API source differs from reviewed baseline' >&2
    exit 1
fi
test -x "$legacy_dir/.venv/bin/python"
if test -n "$(ss -H -ltn 'sport = :8766')"; then
    echo 'STOP: port 8766 already has a listener; no process will be stopped' >&2
    exit 1
fi
curl --noproxy '*' --fail --silent --show-error --max-time 5 http://127.0.0.1:8765/health
umask 077
deploy_dir="$HOME/alivemap-semantic-view/{digest[:16]}"
mkdir -p "$deploy_dir"
if test -f "$deploy_dir/semantic_view.py"; then
    existing=$(sha256sum "$deploy_dir/semantic_view.py" | cut -d ' ' -f 1)
    if test "$existing" != '{digest}'; then
        echo 'STOP: existing extension file differs; refusing to overwrite it' >&2
        exit 1
    fi
else
    cat > "$deploy_dir/semantic_view.py" <<'{delimiter}'
{source}{delimiter}
fi
installed=$(sha256sum "$deploy_dir/semantic_view.py" | cut -d ' ' -f 1)
test "$installed" = '{digest}'
echo 'Starting read-only view on loopback 8766. Existing API remains on 8765.'
echo 'Keep this SSH window open. Stop only the semantic-view Uvicorn process when finished.'
exec env ALIVEMAP_UPSTREAM=http://127.0.0.1:8765 "$legacy_dir/.venv/bin/python" -m uvicorn semantic_view:create_app --factory --app-dir "$deploy_dir" --host 127.0.0.1 --port 8766
'''
    destination = ROOT / ".local/deploy-semantic-view.sh"
    destination.parent.mkdir(exist_ok=True)
    destination.write_bytes(script.encode())
    print(f"Prepared {destination}; view SHA256={digest}; baseline SHA256={baseline}")
    return destination


if __name__ == "__main__":
    package()
