"""Build a guarded additive deployment; SSH connection remains interactive."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def package():
    source = (ROOT/'mec/playground_api.py').read_text(encoding='utf-8').replace('\r\n', '\n')
    digest = hashlib.sha256(source.encode()).hexdigest()
    baseline = hashlib.sha256((ROOT/'mec/baseline/main.py').read_bytes()).hexdigest()
    delimiter = 'ALIVEMAP_SOURCE_'+digest[:16]
    script = f'''set -eu
legacy_dir="$HOME/mec-av-poc"
test "$(sha256sum "$legacy_dir/main.py" | cut -d ' ' -f 1)" = '{baseline}' || {{ echo 'STOP: original source changed'; exit 1; }}
test -x "$legacy_dir/.venv/bin/python"
test -z "$(ss -H -ltn 'sport = :8767')" || {{ echo 'STOP: port 8767 occupied; nothing stopped'; exit 1; }}
curl --noproxy '*' --fail --silent --show-error --max-time 5 http://127.0.0.1:8765/health
"$legacy_dir/.venv/bin/python" -c 'import h3,fastapi,pydantic; assert hasattr(h3,"h3shape_to_cells_experimental"); print("Dependencies ready",h3.__version__)'
umask 077
deploy_dir="$HOME/alivemap-playground/{digest[:16]}"
mkdir -p "$deploy_dir"
if test -f "$deploy_dir/playground_api.py"; then
    test "$(sha256sum "$deploy_dir/playground_api.py" | cut -d ' ' -f 1)" = '{digest}' || {{ echo 'STOP: existing extension differs'; exit 1; }}
else
    cat > "$deploy_dir/playground_api.py" <<'{delimiter}'
{source}{delimiter}
fi
test "$(sha256sum "$deploy_dir/playground_api.py" | cut -d ' ' -f 1)" = '{digest}'
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
    package()
