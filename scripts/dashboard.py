#!/usr/bin/env python3
"""Create or verify the demo dashboard through Kibana's Dashboards API."""

import json
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ID = 'santa-esql-past-and-plan'
PATH = '/api/dashboards/' + ID
MARKER = 'Managed by santa-esql-advent: past-and-plan-v1.'
DEFINITION = ROOT / 'dashboards/santa-archives.json'
PREVIOUS_DEFINITION = ROOT / 'dashboards/previous/santa-archives-v1.json'
# Only these exact observed API defaults may be added to the requested payload.
API_DEFAULTS = json.loads((ROOT / 'dashboards/api-defaults.json').read_text())


def _matches(desired, actual, path=()):
    """Allow recorded API defaults and generated panel IDs; reject all other drift."""
    if isinstance(desired, dict):
        if not isinstance(actual, dict):
            return False
        for key in actual.keys() - desired.keys():
            if path == ('panels', '*') and key == 'id' and isinstance(actual[key], str):
                continue
            default_path = '/'.join((*path, key))
            if default_path not in API_DEFAULTS or actual[key] != API_DEFAULTS[default_path]:
                return False
        return all(key in actual and _matches(value, actual[key], (*path, key))
                   for key, value in desired.items())
    if isinstance(desired, list):
        return isinstance(actual, list) and len(desired) == len(actual) and all(
            _matches(wanted, received, (*path, '*'))
            for wanted, received in zip(desired, actual)
        )
    return desired == actual


def _with_image_id(definition, file_id):
    """Resolve the portable image placeholder without rewriting the repository."""
    result = deepcopy(definition)
    result['panels'][0]['config']['image_config']['src']['file_id'] = file_id
    return result


def _previous_definition(definition):
    """Reconstruct only the exact pre-banner layout for a guarded one-step upgrade."""
    previous = deepcopy(definition)
    image = previous['panels'].pop(0)
    for panel in previous['panels']:
        panel['grid']['y'] -= image['grid']['h']
    return previous


def ensure(cfg, request, create=False):
    """Verify the dashboard, uploading its image and upgrading a known layout if allowed."""
    import dashboard_image
    template = json.loads(DEFINITION.read_text())
    existing = request(cfg, 'GET', PATH, missing_ok=True, kibana=True)
    preferred_id = None
    previous_layout = False
    if existing is None:
        if not create:
            raise RuntimeError('Required dashboard missing. Run ./demo.sh setup without --skip-dashboard.')
    else:
        actual = existing.get('data', {})
        if not actual.get('description', '').startswith(MARKER):
            raise RuntimeError('Existing dashboard has no demo ownership marker; refusing to modify it.')
        panels = actual.get('panels', [])
        if panels and panels[0].get('type') == 'image':
            source = panels[0].get('config', {}).get('image_config', {}).get('src', {})
            if source.get('type') == 'file':
                preferred_id = source.get('file_id')
        current_matches = preferred_id and _matches(_with_image_id(template, preferred_id), actual)
        previous = json.loads(PREVIOUS_DEFINITION.read_text())
        previous_layout = (_matches(_with_image_id(previous, preferred_id), actual) if preferred_id
                           else _matches(_previous_definition(previous), actual))
        if not current_matches and not previous_layout:
            raise RuntimeError(
                'Existing demo dashboard is incompatible; refusing to overwrite it. '
                'Restore the managed definition or explicitly remove the demo-owned dashboard in Kibana.'
            )
        if previous_layout and not create:
            raise RuntimeError('Dashboard needs the dataset and color upgrade. Run ./demo.sh setup without --skip-dashboard.')
    file_id = dashboard_image.ensure(cfg, request, create=create, preferred_id=preferred_id)
    desired = _with_image_id(template, file_id)
    if existing is None or not _matches(desired, existing.get('data', {})):
        if not create:
            raise RuntimeError('Dashboard image needs preparation. Run ./demo.sh setup without --skip-dashboard.')
        request(cfg, 'PUT', PATH, desired, kibana=True)
        existing = request(cfg, 'GET', PATH, kibana=True)
    if not _matches(desired, existing.get('data', {})):
        raise RuntimeError('Kibana returned an incompatible dashboard after image preparation.')
    return cfg['KIBANA_URL'].rstrip('/') + '/app/dashboards#/view/' + ID
