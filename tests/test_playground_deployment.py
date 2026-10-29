"""Regression for the Windows PowerShell Unicode upload failure."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import package_playground

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    (tmp_path/'mec/baseline').mkdir(parents=True)
    for relative in ('mec/playground_api.py', 'mec/baseline/main.py'):
        (tmp_path/relative).write_bytes((ROOT/relative).read_bytes())
    monkeypatch.setattr(package_playground, 'ROOT', tmp_path)
    return tmp_path


def test_recovery_is_explicit_and_generated_python_is_valid(deployment):
    script = package_playground.package().read_text(encoding='utf-8')
    assert 'ALIVEMAP_RECOVER_BASELINE' not in script
    script = package_playground.package(recover_baseline=True).read_text(encoding='utf-8')
    code = script.split("<<'ALIVEMAP_RECOVER_BASELINE'\n", 1)[1].split('\nALIVEMAP_RECOVER_BASELINE', 1)[0]
    compile(code, 'baseline-recovery', 'exec')
    assert script.index('sha256sum "$legacy_dir/main.py"') < script.index('subprocess.Popen')
    assert 'occupied but unhealthy; no process stopped' in code


@pytest.mark.skipif(os.name != 'nt', reason='Exercises Windows PowerShell 5 native pipe encoding')
def test_windows_powershell_transfers_exact_utf8_source_bytes(deployment):
    script = package_playground.package()
    checker = deployment/'check.py'
    checker.write_text('''import sys
from pathlib import Path
raw = sys.stdin.buffer.read()
source = raw.split(b"<<'ALIVEMAP_SOURCE_",1)[1].split(b"\\n",1)[1].split(b"ALIVEMAP_SOURCE_",1)[0]
expected = Path(sys.argv[1]).read_text(encoding="utf-8").encode("utf-8")
assert source == expected, "PowerShell changed uploaded source bytes"
print("UTF8_TRANSPORT_VERIFIED")
''', encoding='utf-8')
    def quote(value):
        return "'"+str(value).replace("'", "''")+"'"
    test_script = deployment/'check.ps1'
    test_script.write_text('$OutputEncoding = [System.Text.UTF8Encoding]::new($false)\n'
                           f'Get-Content -LiteralPath {quote(script)} -Raw -Encoding UTF8 | & {quote(sys.executable)} {quote(checker)} {quote(deployment/"mec/playground_api.py")}\n'
                           'exit $LASTEXITCODE\n', encoding='utf-8')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(test_script)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout+result.stderr
    assert 'UTF8_TRANSPORT_VERIFIED' in result.stdout
