"""Reuse valid packages; build missing real geography without deleting user data."""
import argparse
import json

from geospatial.build import ROOT, build
from routing_core.maps import validate_package


def prepare(region, terrain=False, refresh=False):
    folder = ROOT / 'map_packages' / region
    active = folder / 'active.json'
    if active.exists() and not refresh:
        selected = json.loads(active.read_text(encoding='utf-8'))['revision']
        path = (folder / selected).resolve()
        if not path.is_relative_to(folder.resolve()):
            raise ValueError('Invalid active map path')
        try:
            validate_package(path)
            manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
            if not terrain or manifest.get('elevation_raster'):
                print(f'[{region}] Reusing validated package {selected}', flush=True)
                return path
        except (ValueError, OSError, KeyError) as exc:
            print(f'[{region}] Existing package needs building: {type(exc).__name__}', flush=True)
    snapshot = ROOT / 'assets/maps' / (region + '.json')
    return build(region, skip_rasters=not terrain,
                 roads_snapshot=snapshot if snapshot.exists() and not refresh else None)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('region', choices=json.loads((ROOT/'geospatial/definitions.json').read_text()))
    parser.add_argument('--terrain', action='store_true')
    parser.add_argument('--refresh', action='store_true')
    options = parser.parse_args()
    prepare(options.region, options.terrain, options.refresh)
