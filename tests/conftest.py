"""Explicit test tiers; collection never opts into archived prototypes."""
import pytest

GUI_MODULES = {
    'test_dark_chrome', 'test_desktop_workspace', 'test_map_responsiveness',
    'test_playground_editor', 'test_responsive_workspace', 'test_workspace_workflows',
}
MAP_MODULES = {
    'test_geo_maps', 'test_incident_comparison',
    'test_playground_editor', 'test_story_workflows', 'test_workspace_workflows',
    'test_map_responsiveness',
}


def pytest_collection_modifyitems(items):
    for item in items:
        module = item.path.stem
        if module in GUI_MODULES:
            item.add_marker(pytest.mark.gui)
        if (module in MAP_MODULES or 'provider' in item.fixturenames
                or item.name.startswith('test_other_real_maps_')
                or item.name.startswith('test_guided_worker_runs_every_map_')):
            item.add_marker(pytest.mark.maps)
