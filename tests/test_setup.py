"""Setup must preserve user files and reject map paths outside their region."""
import json

import pytest

from scripts import setup_local, setup_maps
from geospatial.build import publish_stage


def test_partial_environment_is_not_deleted_when_python_is_missing(tmp_path, monkeypatch):
    environment = tmp_path / '.venv'
    environment.mkdir()
    sentinel = environment / 'keep-user-file.txt'
    sentinel.write_text('preserve')
    monkeypatch.setattr(setup_local, 'ROOT', tmp_path)
    monkeypatch.setattr(setup_local.sys, 'argv', ['setup_local.py'])
    with pytest.raises(SystemExit) as error:
        setup_local.main()
    assert error.value.code == 2
    assert sentinel.read_text() == 'preserve'


def test_active_revision_cannot_escape_its_region(tmp_path, monkeypatch):
    folder = tmp_path / 'map_packages' / 'delhi_urban'
    folder.mkdir(parents=True)
    (folder / 'active.json').write_text(json.dumps({'revision': '../../outside'}))
    monkeypatch.setattr(setup_maps, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='Invalid active map path'):
        setup_maps.prepare('delhi_urban')


def test_repair_preserves_old_revision_and_restores_it_if_publication_fails(tmp_path, monkeypatch):
    from pathlib import Path
    packages = tmp_path / 'packages'
    destination = packages / 'region' / 'revision'
    stage = packages / '.staging' / 'new'
    destination.mkdir(parents=True)
    stage.mkdir(parents=True)
    (destination / 'old.txt').write_text('keep')
    (stage / 'new.txt').write_text('replacement')
    original = Path.rename
    def fail_stage(self, target):
        if self == stage:
            raise OSError('Simulated publication failure')
        return original(self, target)
    with monkeypatch.context() as context:
        context.setattr(Path, 'rename', fail_stage)
        with pytest.raises(OSError, match='Simulated'):
            publish_stage(stage, destination, packages)
    assert (destination / 'old.txt').read_text() == 'keep'
    retained = publish_stage(stage, destination, packages)
    assert (retained / 'old.txt').read_text() == 'keep'
    assert (destination / 'new.txt').read_text() == 'replacement'


def test_publication_rejects_destination_outside_packages(tmp_path):
    packages = tmp_path / 'packages'
    stage = packages / 'stage'
    stage.mkdir(parents=True)
    with pytest.raises(ValueError, match='Unsafe'):
        publish_stage(stage, tmp_path / 'outside', packages)
    assert stage.exists()
