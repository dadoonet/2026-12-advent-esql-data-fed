#!/usr/bin/env python3
"""Orchestrate ES|QL federation and a dashboard without indexing the historical archive."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.local'
PROJECT = 'santa-esql-advent-2026'
OWNER = hashlib.sha256(str(ROOT).encode()).hexdigest()[:16]
SOURCE = 'santa_minio'
DATASET = 'santa_deliveries_2025'
BUCKET = 'santa-archives'
OBJECT = 'christmas-2025-v2.parquet'
LEGACY_OBJECT = 'christmas-2025.parquet'
LEGACY_ARCHIVE_SHA256 = 'de6f9458d9149d68d997cd3c096682b06953c71685e93768df8b4a2d9e322cbc'
DEFAULTS = {
    'ES_VERSION': '9.6.0-SNAPSHOT', 'KIBANA_VERSION': '9.6.0-SNAPSHOT',
    'ES_PORT': '9200', 'KIBANA_PORT': '5601', 'S3_PORT': '9000',
    'S3_CONSOLE_PORT': '9001', 'S3_REGION': 'us-east-1',
    'S3_ES_ENDPOINT': 'http://minio:9000', 'ES_USERNAME': 'elastic',
    'READY_TIMEOUT': '240',
}
SECRETS = ('ES_PASSWORD', 'KIBANA_PASSWORD', 'KIBANA_ENCRYPTION_KEY',
           'S3_ACCESS_KEY', 'S3_SECRET_KEY', 'CLUSTER_ENCRYPTION_PASSWORD')


def log(stage, message):
    print(f'[{stage}] {message}', flush=True)


def fail(message):
    raise RuntimeError(message)


def load_config(create=False):
    values = dict(DEFAULTS)
    envfile = ROOT / '.env'
    if not envfile.exists() and create:
        generated = {key: secrets.token_hex(24) for key in SECRETS}
        # Exclusive creation prevents concurrent runs from replacing credentials.
        fd = os.open(envfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write('# Local development credentials. Never commit this file.\n')
            stream.writelines(f'{key}={value}\n' for key, value in generated.items())
        log('prepare', 'Generated private .env')
    if envfile.exists():
        for line in envfile.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            key, sep, value = line.partition('=')
            if not sep or not key.strip().replace('_', '').isalnum():
                fail('Invalid .env line; use unquoted KEY=value entries, without shell expressions.')
            values[key.strip()] = value.strip()
    for key in set(values) | set(SECRETS) | {'ES_URL', 'KIBANA_URL', 'S3_URL', 'MINIO_IMAGE', 'ES_JAVA_OPTS'}:
        if key in os.environ:
            values[key] = os.environ[key]
    for key, port in [('ES_URL', 'ES_PORT'), ('KIBANA_URL', 'KIBANA_PORT'), ('S3_URL', 'S3_PORT')]:
        values.setdefault(key, f'http://localhost:{values[port]}')
    values['DEMO_OWNER'] = OWNER
    for key in ('ES_URL', 'KIBANA_URL', 'S3_URL', 'S3_ES_ENDPOINT'):
        url = urlsplit(values[key])
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query:
            fail(f'{key} must be an HTTP(S) URL without embedded credentials or a query.')
    return values


def need_credentials(cfg):
    for key in SECRETS:
        if not cfg.get(key) or 'CHANGE_ME' in cfg[key]:
            fail(f'Set {key} in private .env or environment; ./demo.sh setup generates credentials when .env is absent.')


def scrub(cfg, message):
    for key in SECRETS:
        value = cfg.get(key)
        if value:
            message = message.replace(value, '<redacted>')
    return message


def command(cfg, args, capture=False, input_text=None):
    result = subprocess.run(args, cwd=ROOT, env={**os.environ, **cfg},
                            text=True, input=input_text, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        fail(scrub(cfg, f'Command failed: {args[0]} {args[1]}\n{result.stderr.strip()}'))
    if not capture and result.stdout.strip():
        print(scrub(cfg, result.stdout.strip()), flush=True)
    return result.stdout


def docker_ready(cfg):
    try:
        command(cfg, ['docker', 'info', '--format', '{{.ServerVersion}}'], capture=True)
        command(cfg, ['docker', 'compose', 'version'], capture=True)
    except (OSError, RuntimeError):
        fail('Docker and Docker Compose must be installed and the Docker daemon accessible. Start Docker yourself, then retry.')


def compose(cfg, *args, input_text=None):
    return command(cfg, ['docker', 'compose', '--project-name', PROJECT,
                         '--file', str(ROOT / 'compose.yaml'), *args], capture=True, input_text=input_text)


def owned_resources(cfg):
    """Refuse name collisions before any Compose mutation, including cleanup."""
    # Check exact reserved names too: Compose may otherwise adopt an unlabelled volume.
    specifications = [
        ('container', ['ps', '-aq'], ['inspect'],
         [f'{PROJECT}-{service}-1' for service in ('elasticsearch', 'kibana', 'minio')]),
        ('volume', ['volume', 'ls', '-q'], ['volume', 'inspect'],
         [f'{PROJECT}_{volume}' for volume in ('es-data', 'es-config', 'kibana-data', 'minio-data')]),
        ('network', ['network', 'ls', '-q'], ['network', 'inspect'], [f'{PROJECT}_default']),
    ]
    for kind, listing, inspecting, reserved in specifications:
        ids = command(cfg, ['docker', *listing, '--filter', f'label=com.docker.compose.project={PROJECT}'], True).split()
        if kind == 'container':
            all_names = command(cfg, ['docker', 'ps', '-a', '--format', '{{.Names}}'], True).split()
        elif kind == 'network':
            all_names = command(cfg, ['docker', 'network', 'ls', '--format', '{{.Name}}'], True).split()
        else:
            all_names = command(cfg, ['docker', *listing], True).split()
        ids = sorted(set(ids) | (set(reserved) & set(all_names)))
        if ids:
            entries = json.loads(command(cfg, ['docker', *inspecting, *ids], True))
            for entry in entries:
                labels = (entry.get('Config', {}).get('Labels') if kind == 'container' else entry.get('Labels')) or {}
                if labels.get('io.santa.advent.owner') != OWNER:
                    fail(f'Refusing to modify {kind}: reserved Compose resources belong to another directory or owner.')


def request(cfg, method, path, payload=None, missing_ok=False, kibana=False,
            raw_body=None, content_type="application/json", raw_response=False, internal_origin=None):
    base = cfg['KIBANA_URL'] if kibana else cfg['ES_URL']
    token = base64.b64encode(f"{cfg['ES_USERNAME']}:{cfg['ES_PASSWORD']}".encode()).decode()
    if payload is not None and raw_body is not None:
        fail("A request cannot contain both JSON and raw bytes.")
    data = raw_body if raw_body is not None else (None if payload is None else json.dumps(payload).encode())
    headers = {"Authorization": f"Basic {token}", "Content-Type": content_type, "kbn-xsrf": "santa-demo"}
    if internal_origin:
        headers["x-elastic-internal-origin"] = internal_origin
    req = urllib.request.Request(base.rstrip('/') + path, data=data, method=method,
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.headers.get('Warning'):
                fail(scrub(cfg, 'Elasticsearch Warning: ' + response.headers.get('Warning')))
            return response.read() if raw_response else json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and missing_ok:
            return None
        detail = exc.read().decode(errors='replace')
        fail(scrub(cfg, f'{method} {path}: HTTP {exc.code}: {detail}'))
    except (urllib.error.URLError, TimeoutError) as exc:
        fail(f'{method} {path}: service unavailable ({type(exc).__name__}). Run ./demo.sh setup and check configured endpoints.')


def wait(cfg, name, check):
    deadline = time.monotonic() + float(cfg['READY_TIMEOUT'])
    last_error = 'service reported not ready'
    while True:
        try:
            result = check()
            if result:
                log('ready', name)
                return result
        except (RuntimeError, OSError) as exc:
            last_error = scrub(cfg, str(exc))
        if time.monotonic() >= deadline:
            fail(f'{name} not ready after {cfg["READY_TIMEOUT"]}s. Check ./demo.sh status and project container logs; verify endpoint and credentials. Last error: {last_error}')
        time.sleep(2)


def es_ready(cfg):
    info = request(cfg, 'GET', '/')
    if info['version']['number'] not in (cfg['ES_VERSION'], cfg['ES_VERSION'].removesuffix('-SNAPSHOT')):
        fail(f'Elasticsearch version mismatch: expected {cfg["ES_VERSION"]}, observed {info["version"]["number"]}. Set ES_VERSION explicitly.')
    health = request(cfg, 'GET', '/_cluster/health?wait_for_status=yellow&timeout=2s')
    return info if health['status'] in ('yellow', 'green') and not health.get('timed_out') else None


def kibana_ready(cfg):
    result = request(cfg, 'GET', '/api/status', kibana=True)
    expected = cfg['KIBANA_VERSION']
    if result.get('version', {}).get('number') not in (expected, expected.removesuffix('-SNAPSHOT')):
        fail('Kibana version mismatch. Set KIBANA_VERSION explicitly.')
    return result.get('status', {}).get('overall', {}).get('level') == 'available'


def s3_client(cfg):
    import boto3
    from botocore.config import Config
    return boto3.client('s3', endpoint_url=cfg['S3_URL'], region_name=cfg['S3_REGION'],
                        aws_access_key_id=cfg['S3_ACCESS_KEY'], aws_secret_access_key=cfg['S3_SECRET_KEY'],
                        config=Config(signature_version='s3v4', s3={'addressing_style': 'path'},
                                      connect_timeout=3, read_timeout=10, retries={'max_attempts': 0},
                                      request_checksum_calculation='when_required', response_checksum_validation='when_required'))


def s3_ready(cfg):
    try:
        s3_client(cfg).list_buckets()
        return True
    except Exception:
        return False


def data_object(cfg, upload=False):
    from botocore.exceptions import ClientError
    client = s3_client(cfg)
    if upload:
        command(cfg, [sys.executable, 'data/generate.py'])
    local = (ROOT / 'data/deliveries.parquet').read_bytes()
    digest = hashlib.sha256(local).hexdigest()
    try:
        remote = client.get_object(Bucket=BUCKET, Key=OBJECT)['Body'].read()
    except ClientError as exc:
        if exc.response['Error']['Code'] not in ('NoSuchBucket', 'NoSuchKey', '404'):
            fail(f'S3 object access failed ({exc.response["Error"]["Code"]}); verify credentials and read permissions.')
        if not upload:
            fail('Required Parquet object missing. Run ./demo.sh setup without --skip-data-upload.')
        try:
            client.head_bucket(Bucket=BUCKET)
        except ClientError as head:
            if head.response['Error']['Code'] not in ('404', 'NoSuchBucket'):
                fail('Cannot access S3 bucket; check configured credentials and permissions.')
            kwargs = {} if cfg['S3_REGION'] == 'us-east-1' else {'CreateBucketConfiguration': {'LocationConstraint': cfg['S3_REGION']}}
            client.create_bucket(Bucket=BUCKET, **kwargs)
        client.put_object(Bucket=BUCKET, Key=OBJECT, Body=local, ContentType='application/vnd.apache.parquet')
        remote = client.get_object(Bucket=BUCKET, Key=OBJECT)['Body'].read()
        log('upload', 'Uploaded the Parquet object; no Elasticsearch index is created')
    if hashlib.sha256(remote).hexdigest() != digest:
        fail('Existing S3 object differs from the committed dataset. Refusing to overwrite it. Restore the expected object or use ./demo.sh reset for owned MinIO data.')
    log('data', f'Parquet object verified ({len(remote)} bytes, SHA256 {digest[:12]})')


def definitions(cfg, create=False):
    source = {'type': 's3', 'settings': {'auth': 'static_credentials',
              'access_key': cfg['S3_ACCESS_KEY'], 'secret_key': cfg['S3_SECRET_KEY'],
              'endpoint': cfg['S3_ES_ENDPOINT'], 'addressing_style': 'path'}}
    dataset = {'data_source': SOURCE, 'resource': f's3://{BUCKET}/{OBJECT}', 'settings': {'region': cfg['S3_REGION']}}
    for resource, name, plural, desired in [('data_source', SOURCE, 'data_sources', source), ('dataset', DATASET, 'datasets', dataset)]:
        path = f'/_query/{resource}/{name}'
        existing = request(cfg, 'GET', path, missing_ok=True)
        if existing is None:
            if not create:
                fail(f'Required {resource} {name} missing. Run ./demo.sh setup without --skip-registration.')
            request(cfg, 'PUT', path, desired)
            log('register', f'Created {resource} {name}')
        else:
            current = existing[plural][0]
            if resource == 'dataset' and current.get('resource') == f's3://{BUCKET}/{LEGACY_OBJECT}':
                if not create:
                    fail('Dataset uses the previous archive. Run ./demo.sh setup without --skip-registration to upgrade it.')
                previous_settings = current.get('settings', {})
                if (set(current) - {'name', 'data_source', 'resource', 'settings', 'description'}
                        or current.get('data_source') != SOURCE or previous_settings.get('region') != cfg['S3_REGION']
                        or set(previous_settings) - {'region', 'schema_resolution'}
                        or previous_settings.get('schema_resolution', 'first_file_wins') != 'first_file_wins'):
                    fail('Previous dataset definition was changed; refusing to overwrite it.')
                # Keep the compatible existing schema-resolution choice when repointing the archive.
                desired['settings'] = dict(previous_settings)
                if 'description' in current:
                    desired['description'] = current['description']
                previous_bytes = s3_client(cfg).get_object(Bucket=BUCKET, Key=LEGACY_OBJECT)['Body'].read()
                if hashlib.sha256(previous_bytes).hexdigest() != LEGACY_ARCHIVE_SHA256:
                    fail('Previous archive was changed; refusing to repoint its dataset. Restore it or explicitly remove the demo-owned dataset before setup.')
                log('register', 'Upgrading the verified dataset to the varied archive; the previous S3 object is preserved')
                request(cfg, 'PUT', path, desired)
                current = request(cfg, 'GET', path)[plural][0]
            for key, value in desired.items():
                if key == 'settings':
                    for setting, wanted in value.items():
                        if setting not in ('access_key', 'secret_key') and current.get('settings', {}).get(setting) != wanted:
                            fail(f'Existing {resource} has incompatible {setting}; refusing to overwrite it.')
                elif current.get(key) != value:
                    fail(f'Existing {resource} has incompatible {key}; refusing to overwrite it.')
            log('register', f'Reusing compatible {resource} {name}')


def ensure_license(cfg):
    license = request(cfg, 'GET', '/_license')['license']
    if license['type'] not in ('trial', 'enterprise') or license['status'] != 'active':
        log('license', 'Activating the trial required for Data Federation')
        request(cfg, 'POST', '/_license/start_trial?acknowledge=true')
        license = request(cfg, 'GET', '/_license')['license']
    if license['type'] not in ('trial', 'enterprise') or license['status'] != 'active':
        fail('Data Federation requires an active Enterprise or Trial license. This cluster may have exhausted its trial.')
    log('license', f'Active {license["type"]} license')


def record_config(cfg):
    STATE.mkdir(exist_ok=True, mode=0o700)
    keys = sorted((set(DEFAULTS) | set(SECRETS) | {'ES_JAVA_OPTS'}) - {'READY_TIMEOUT'})
    # Compare fingerprints, never store a second copy of credentials.
    settings = {k: cfg.get(k) for k in keys}
    settings['files'] = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in ('compose.yaml', 'config/elasticsearch.yml', 'config/kibana.yml', 'config/Dockerfile.minio')}
    fingerprint = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()
    path = STATE / 'stack.sha256'
    if path.exists() and path.read_text() != fingerprint:
        fail('Local stack configuration changed. Restore .env or explicitly reset owned persistent data before changing versions, ports, or credentials.')
    path.write_text(fingerprint)


def setup(cfg, args):
    need_credentials(cfg)
    if not args.skip_stack_start or not args.skip_s3_start:
        docker_ready(cfg)
        owned_resources(cfg)
        record_config(cfg)
    if not args.skip_s3_start:
        log('start', 'Starting owned MinIO')
        compose(cfg, 'up', '-d', 'minio')
    else:
        log('skip', 'Checking existing S3 service')
    wait(cfg, 'S3 authentication', lambda: s3_ready(cfg))
    if not args.skip_stack_start:
        log('keystore', 'Preparing persistent cluster-state encryption keys')
        script = ('if [ ! -f config/elasticsearch.keystore ]; then bin/elasticsearch-keystore create; fi; '
                  'bin/elasticsearch-keystore add --stdin --force cluster.state.encryption.active_password_id')
        compose(cfg, 'run', '--rm', '--no-deps', '-T', '--entrypoint', 'bash', 'elasticsearch',
                '-c', script, input_text='santa-demo\n')
        compose(cfg, 'run', '--rm', '--no-deps', '-T', '--entrypoint',
                '/usr/share/elasticsearch/bin/elasticsearch-keystore', 'elasticsearch',
                'add', '--stdin', '--force', 'cluster.state.encryption.password.santa-demo',
                input_text=cfg['CLUSTER_ENCRYPTION_PASSWORD'] + '\n')
        log('start', 'Starting owned Elasticsearch')
        compose(cfg, 'up', '-d', 'elasticsearch')
    else:
        log('skip', 'Checking existing Elasticsearch and Kibana')
    info = wait(cfg, 'Elasticsearch', lambda: es_ready(cfg))
    log('build', f"Elasticsearch {info['version']['number']} build {info['version']['build_hash']}")
    if not args.skip_stack_start:
        request(cfg, 'POST', '/_nodes/reload_secure_settings', {})
    ensure_license(cfg)
    if not args.skip_stack_start:
        request(cfg, 'POST', '/_security/user/kibana_system/_password', {'password': cfg['KIBANA_PASSWORD']})
        log('start', 'Starting owned Kibana')
        compose(cfg, 'up', '-d', 'kibana')
    wait(cfg, 'Kibana', lambda: kibana_ready(cfg))
    data_object(cfg, upload=not args.skip_data_upload)
    definitions(cfg, create=not args.skip_registration)
    import indexed_data
    import dashboard
    if not args.skip_indexed_data:
        command(cfg, [sys.executable, 'data/plan.py'])
    indexed_data.ensure(cfg, request, create=not args.skip_indexed_data)
    url = dashboard.ensure(cfg, request, create=not args.skip_dashboard)
    log('dashboard', url)
    log('setup', 'Ready. Replay with ./demo.sh run; credentials remain in private .env')


def run(cfg):
    from validate import validate
    need_credentials(cfg)
    if not es_ready(cfg):
        fail('Elasticsearch is not ready. Run ./demo.sh setup.')
    if not s3_ready(cfg):
        fail('S3 is not ready or authentication failed. Run ./demo.sh setup.')
    data_object(cfg)
    definitions(cfg)
    import indexed_data
    indexed_data.ensure(cfg, request)
    expected = json.loads((ROOT / 'data/expected.json').read_text())
    expected.update(json.loads((ROOT / 'data/plan-expected.json').read_text()))
    STATE.mkdir(exist_ok=True, mode=0o700)
    # An index with this name would invalidate the external-data demonstration.
    resolved = request(cfg, 'GET', f'/_resolve/index/{DATASET}', missing_ok=True) or {}
    if any(resolved.get(kind) for kind in ('indices', 'aliases', 'data_streams')):
        fail('An index shadows the dataset name. Remove the naming conflict before this external-data experiment.')
    for query in sorted((ROOT / 'queries').glob('*.esql')):
        response = request(cfg, 'POST', '/_query', {'query': query.read_text(), 'locale': 'en-US'})
        validate(response, expected[query.stem])
        (STATE / f'{query.stem}.json').write_text(json.dumps(response, indent=2) + '\n')
        log('PASS', f'{query.stem}: {len(response["values"])} rows match independent expectations')
        print(json.dumps([dict(zip([col['name'] for col in response['columns']], row)) for row in response['values']], indent=2))
    log('done', 'All five queries matched expectations: external archive, indexed plans, and their lookup join')


def status(cfg):
    import indexed_data
    import dashboard
    need_credentials(cfg)
    checks = [('Elasticsearch', lambda: es_ready(cfg)), ('Kibana', lambda: kibana_ready(cfg)),
              ('S3', lambda: s3_ready(cfg)), ('Parquet object', lambda: data_object(cfg) or True),
              ('Federation definitions', lambda: definitions(cfg) or True),
              ('Indexed 2026 plans', lambda: indexed_data.ensure(cfg, request) or True),
              ('Kibana dashboard', lambda: dashboard.ensure(cfg, request) or True)]
    ok = True
    for name, check in checks:
        try:
            if not check():
                fail('not ready')
            log('OK', name)
        except Exception as exc:
            ok = False
            log('MISSING', f'{name}: {scrub(cfg, str(exc))}')
    if not ok:
        fail('Setup is incomplete. Run ./demo.sh setup or correct the configured endpoints.')


def cleanup(cfg, reset=False, yes=False):
    if reset and not yes:
        if not sys.stdin.isatty() or input('Delete this demo’s owned Elasticsearch, Kibana and MinIO volumes? Type reset: ') != 'reset':
            fail('Reset cancelled. Use ./demo.sh reset --yes for unattended cleanup.')
    docker_ready(cfg)
    owned_resources(cfg)
    # Compose requires interpolation even for down; use harmless values if .env was removed.
    for key in SECRETS:
        cfg.setdefault(key, 'unused-cleanup-placeholder-000000000000')
    compose(cfg, 'down', *(['--volumes'] if reset else []))
    if reset and STATE.exists():
        import shutil
        shutil.rmtree(STATE)
    log('reset' if reset else 'down', 'Owned containers removed' + (' and owned persistent volumes deleted' if reset else '; persistent data preserved'))


def present_kibana_access(cfg, open_browser=True):
    """Show local login details and open the dashboard only in an interactive terminal."""
    import dashboard
    url = cfg['KIBANA_URL'].rstrip('/') + '/app/dashboards#/view/' + dashboard.ID
    print(f'[access] Dashboard: {url}', flush=True)
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print('[access] Credentials remain in private .env; browser opening is skipped outside an interactive terminal.', flush=True)
        return
    print(f"[access] Username: {cfg['ES_USERNAME']}")
    print(f"[access] Password: {cfg['ES_PASSWORD']}", flush=True)
    if not open_browser:
        return
    try:
        import webbrowser
        opened = webbrowser.open(url, new=2)
    except Exception:
        opened = False
    if not opened:
        print('[access] Open the dashboard URL manually.', flush=True)


def main():
    parser = argparse.ArgumentParser(prog='./demo.sh', description=__doc__, epilog='Examples: ./demo.sh; ./demo.sh setup; ./demo.sh run; ./demo.sh setup --skip-stack-start --skip-s3-start --skip-data-upload --skip-registration; ./demo.sh reset --yes')
    parser.add_argument('command', nargs='?', default='all', choices=['all', 'setup', 'run', 'status', 'down', 'reset', 'help'], help='default/all: setup then run; setup: prepare and start; run: query and validate; status: check readiness and data; down: stop, preserving volumes; reset: delete owned volumes; help: show usage')
    for flag, description in [
        ('stack-start', 'Reuse configured Elasticsearch and Kibana; check readiness'),
        ('s3-start', 'Reuse configured S3 endpoint; check authentication'),
        ('data-upload', 'Reuse the existing Parquet object; check its contents'),
        ('registration', 'Reuse compatible data source and dataset definitions'),
        ('indexed-data', 'Reuse the indexed 2026 plans; check mapping and contents'),
        ('dashboard', 'Reuse the compatible dashboard; check its definition'),
    ]:
        parser.add_argument('--skip-' + flag, action='store_true', help=description + ' (default/setup only)')
    parser.add_argument('--no-open', action='store_true', help='Disable automatic browser opening (default/setup only)')
    parser.add_argument('--yes', action='store_true', help='Confirm deletion of owned persistent data (reset only)')
    args = parser.parse_args()
    if args.command == 'help':
        parser.print_help()
        return
    if args.command not in ('all', 'setup') and any(getattr(args, 'skip_' + flag) for flag in ('stack_start', 's3_start', 'data_upload', 'registration', 'indexed_data', 'dashboard')):
        parser.error('Skip options apply only to the default command and setup.')
    if args.no_open and args.command not in ('all', 'setup'):
        parser.error('--no-open applies only to the default command and setup.')
    if args.yes and args.command != 'reset':
        parser.error('--yes applies only to reset.')
    cfg = load_config(create=args.command in ('all', 'setup'))
    try:
        if args.command in ('all', 'setup'):
            setup(cfg, args)
        if args.command in ('all', 'run'):
            run(cfg)
        elif args.command == 'status':
            status(cfg)
        elif args.command in ('down', 'reset'):
            cleanup(cfg, reset=args.command == 'reset', yes=args.yes)
        if args.command in ('all', 'setup'):
            present_kibana_access(cfg, open_browser=not args.no_open)
    except Exception as exc:
        fail(scrub(cfg, str(exc)))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('Interrupted. Services and data are preserved; use ./demo.sh down to stop them.', file=sys.stderr)
        sys.exit(130)
