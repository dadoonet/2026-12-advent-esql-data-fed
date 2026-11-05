#!/usr/bin/env python3
"""Upload and verify the dashboard header through Kibana's Files API."""

import hashlib
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / 'assets/santa-elky-christmas-past.png'
NAME = 'santa-elky-christmas-past'
KIND = 'defaultImage'
BASE = '/api/files/files/' + KIND
ALT = 'Elky dressed as Santa meeting the Ghost of Christmas Past with a toy train.'


def ensure(cfg, request, create=False, preferred_id=None):
    """Return a verified image file ID, optionally creating or completing its upload."""
    content = ASSET.read_bytes()
    if not content.startswith(b'\x89PNG\r\n\x1a\n') or len(content) > 10 * 1024 * 1024:
        raise RuntimeError('The dashboard header must be an unchanged PNG no larger than 10 MiB.')
    digest = hashlib.sha256(content).hexdigest()
    metadata = {'santa_demo': 'christmas-header-v1', 'sha256': digest}
    missing_message = 'Required dashboard header image missing. Run ./demo.sh setup without --skip-dashboard.'

    def files_request(method, path, payload=None, **kwargs):
        return request(cfg, method, path, payload, kibana=True,
                       internal_origin='santa-esql-advent-demo', **kwargs)

    def compatible(file):
        return (file.get('name') == NAME and file.get('mimeType') == 'image/png'
                and file.get('meta') == metadata)

    def verify(file):
        if not compatible(file):
            raise RuntimeError('Existing dashboard header image has incompatible metadata or ownership; refusing to overwrite it.')
        identifier = file.get('id')
        if not isinstance(identifier, str) or not identifier:
            raise RuntimeError('Kibana returned an invalid dashboard header file ID.')
        path = BASE + '/' + quote(identifier, safe='')
        if file.get('status') == 'AWAITING_UPLOAD':
            if not create:
                raise RuntimeError(missing_message)
            result = files_request('PUT', path + '/blob',
                             raw_body=content, content_type='image/png')
            if result.get('ok') is not True or result.get('size') != len(content):
                raise RuntimeError('Kibana did not confirm the complete dashboard header image upload.')
            response = files_request('GET', path)
            file = response['file']
            if not compatible(file) or file.get('id') != identifier:
                raise RuntimeError('Dashboard header metadata changed during upload verification.')
        if file.get('status') != 'READY':
            raise RuntimeError('Dashboard header image is not ready. Check the owned file in Kibana Files before retrying setup.')
        stored = files_request('GET', path + '/blob', raw_response=True)
        if hashlib.sha256(stored).hexdigest() != digest:
            raise RuntimeError('Existing dashboard header image content differs from the committed PNG; refusing to overwrite it.')
        print('[image] Verified dashboard header image: ' + ASSET.name, flush=True)
        return identifier

    if preferred_id is not None:
        if not isinstance(preferred_id, str) or not preferred_id:
            raise RuntimeError('The dashboard references an invalid header image file ID.')
        response = files_request('GET', BASE + '/' + quote(preferred_id, safe=''),
                                 missing_ok=True)
        if response is not None:
            return verify(response['file'])
        if not create:
            raise RuntimeError(missing_message)

    response = files_request('POST', BASE + '/list?page=1&perPage=100',
                             {'name': NAME, 'meta': metadata})
    if response.get('total', 0) > 100:
        raise RuntimeError('Too many matching dashboard image files to verify safely; inspect Kibana Files before retrying setup.')
    candidates = [file for file in response['files'] if compatible(file)]
    ready = sorted((file for file in candidates if file.get('status') == 'READY'),
                   key=lambda file: file['id'])
    if ready:
        return verify(ready[0])
    awaiting = sorted((file for file in candidates if file.get('status') == 'AWAITING_UPLOAD'),
                      key=lambda file: file['id'])
    if awaiting:
        return verify(awaiting[0])
    if candidates:
        raise RuntimeError('Matching dashboard header files are not ready; inspect their status in Kibana Files before retrying setup.')
    if not create:
        raise RuntimeError(missing_message)
    response = files_request('POST', BASE, {
        'name': NAME, 'mimeType': 'image/png', 'alt': ALT, 'meta': metadata,
    })
    return verify(response['file'])
