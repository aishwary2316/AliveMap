"""Unambiguous old-route rendering: only retired contiguous road runs are dashed."""
from collections import Counter


def retired_runs(old_route, current_route):
    remaining, runs, run = Counter(current_route), [], []
    for edge in old_route:
        if remaining[edge]:
            remaining[edge] -= 1
            if run:
                runs.append(run)
                run = []
        else:
            run.append(edge)
    if run:
        runs.append(run)
    return runs
