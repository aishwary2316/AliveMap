"""Create an isolated laptop environment, build real maps and verify a local story."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]
REGIONS = tuple(json.loads((ROOT / 'geospatial/definitions.json').read_text(encoding='utf-8')))


def run(arguments):
    temporary = ROOT / '.local/setup-temp'
    temporary.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update(TEMP=str(temporary), TMP=str(temporary), TMPDIR=str(temporary))
    subprocess.run([str(arg) for arg in arguments], cwd=ROOT, env=environment, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--maps', nargs='+', choices=(*REGIONS, 'all'), default=['delhi_urban'])
    parser.add_argument('--terrain', action='store_true', help='Attempt DEM and historical imagery acquisition')
    parser.add_argument('--dev', action='store_true', help='Also install pytest for development')
    parser.add_argument('--skip-check', action='store_true', help='Skip the actual SUMO/local API smoke test')
    parser.add_argument('--launch', action='store_true', help='Open the desktop after successful setup')
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        parser.exit(2, 'Use Python 3.12: py -3.12 scripts/setup_local.py (Windows), or python3.12 scripts/setup_local.py.\n')
    environment = ROOT / '.venv'
    python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if environment.exists():
        if not python.is_file():
            parser.exit(2, '.venv exists but has no Python executable. Move it aside yourself before retrying; setup will not delete it.\n')
        run([python, '-c', 'import sys; sys.exit(0 if sys.version_info[:2] == (3,12) else "Existing .venv must use Python 3.12")'])
    else:
        print('[1/4] Creating .venv with Python 3.12', flush=True)
        venv.EnvBuilder(with_pip=False).create(environment)
    run([python, '-m', 'ensurepip', '--upgrade'])
    print('[2/4] Installing pinned dependencies (existing packages are reused)', flush=True)
    requirements = 'requirements-dev.txt' if args.dev else 'requirements-laptop.txt'
    run([python, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', requirements])
    run([python, '-m', 'pip', 'check'])
    run([python, '-c', 'import tkinter; from laptop.network import binary; import subprocess; subprocess.run([binary("sumo"),"--version"],check=True)'])
    regions = REGIONS if 'all' in args.maps else tuple(dict.fromkeys(args.maps))
    print('[3/4] Preparing real geographic packages', flush=True)
    for region in regions:
        run([python, '-m', 'scripts.setup_maps', region, *(['--terrain'] if args.terrain else [])])
    print('[4/4] Checking independent reports, routing and the incident-free baseline', flush=True)
    if not args.skip_check:
        run([python, '-m', 'scripts.verify_local', '--maps', *regions])
    print('AliveMap setup complete. Local mode needs no server credentials.', flush=True)
    if args.launch:
        run([python, '-m', 'laptop.map_launcher', '--playground'])
    else:
        print('Open AliveMap Playground.cmd, or run .venv Python with -m laptop.map_launcher --playground.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f'Setup stopped because a step failed (exit {exc.returncode}). Fix the error above and rerun the same command.', file=sys.stderr)
        sys.exit(exc.returncode or 1)
