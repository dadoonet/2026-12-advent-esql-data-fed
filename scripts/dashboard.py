#!/usr/bin/env python3
"""Create or verify the demo dashboard through Kibana's Dashboards API."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ID = 'santa-esql-past-and-plan'
PATH = '/api/dashboards/' + ID
MARKER = 'Managed by santa-esql-advent: past-and-plan-v1.'
DEFINITION = ROOT / 'dashboards/santa-archives.json'
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


def ensure(cfg, request, create=False):
    """Create a missing dashboard, verify compatible content, and return its URL."""
    desired = json.loads(DEFINITION.read_text())
    existing = request(cfg, 'GET', PATH, missing_ok=True, kibana=True)
    if existing is None:
        if not create:
            raise RuntimeError(
                'Required dashboard missing. Run ./demo.sh setup without --skip-dashboard.'
            )
        request(cfg, 'PUT', PATH, desired, kibana=True)
        existing = request(cfg, 'GET', PATH, kibana=True)
    actual = existing.get('data', {})
    if not actual.get('description', '').startswith(MARKER):
        raise RuntimeError(
            'Existing dashboard has no demo ownership marker; refusing to modify it.'
        )
    if not _matches(desired, actual):
        raise RuntimeError(
            'Existing demo dashboard is incompatible; refusing to overwrite it. '
            'Restore dashboards/santa-archives.json to match, or explicitly remove '
            'the demo-owned dashboard in Kibana before running ./demo.sh setup again.'
        )
    return cfg['KIBANA_URL'].rstrip('/') + '/app/dashboards#/view/' + ID
