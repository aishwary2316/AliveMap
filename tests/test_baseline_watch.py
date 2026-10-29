from pathlib import Path
from unittest.mock import Mock

import pytest

from mec import baseline_watch

ROOT=Path(__file__).resolve().parents[1]


def test_healthy_existing_baseline_is_not_restarted(tmp_path,monkeypatch):
    (tmp_path/'main.py').write_bytes((ROOT/'mec/baseline/main.py').read_bytes())
    monkeypatch.setattr(baseline_watch,'healthy',lambda:True)
    start=Mock();monkeypatch.setattr(baseline_watch.subprocess,'Popen',start)
    assert baseline_watch.start_if_absent(tmp_path) is None
    start.assert_not_called()


def test_changed_baseline_is_not_started(tmp_path,monkeypatch):
    (tmp_path/'main.py').write_text('different source')
    start=Mock();monkeypatch.setattr(baseline_watch.subprocess,'Popen',start)
    with pytest.raises(RuntimeError,match='source changed'):baseline_watch.start_if_absent(tmp_path)
    start.assert_not_called()


def test_owned_child_gets_startup_time_before_health_is_required(monkeypatch):
    checks=iter([False,False,True])
    monkeypatch.setattr(baseline_watch,'healthy',lambda:next(checks))
    pause=Mock();monkeypatch.setattr(baseline_watch.time,'sleep',pause)
    child=Mock();child.poll.return_value=None
    baseline_watch.wait_ready(child)
    assert pause.call_count==2
    child.terminate.assert_not_called()
