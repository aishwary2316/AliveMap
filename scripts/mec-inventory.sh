#!/usr/bin/env bash
# Read-only discovery. Keep raw output in ignored .local/, not Git.
set -u

printf '\n== Host and OS ==\n'
hostname
id
cat /etc/os-release
printf '\n== Python ==\n'
python3 --version
command -v python3
printf '\n== Home entries (names only) ==\n'
pwd
find "$HOME" -maxdepth 1 -mindepth 1 -printf '%f\n' | sort
printf '\n== Existing API listener ==\n'
ss -ltnp 'sport = :8765'
printf '\n== API health ==\n'
curl --noproxy '*' --fail --silent --show-error --max-time 5 http://127.0.0.1:8765/health
printf '\n== Candidate app entrypoints (paths only) ==\n'
find "$HOME" -maxdepth 4 -type d \( -name .venv -o -name venv -o -name .cache -o -name .git -o -name node_modules \) -prune -o -type f \( -name main.py -o -name app.py -o -name pyproject.toml -o -name requirements.txt -o -name AGENTS.md \) -print 2>/dev/null
printf '\n== End of read-only discovery ==\n'