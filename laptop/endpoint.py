"""Endpoint and machine credentials; private configuration never enters run logs."""
import json
import os
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_URL = 'http://127.0.0.1:18767'
CONFIG = Path(__file__).resolve().parents[1]/'.local/mec-endpoint.json'


def endpoint(url=None, config_path=None):
    path = Path(config_path or CONFIG)
    config = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    selected = url or os.environ.get('ALIVEMAP_MEC_URL') or config.get('url') or DEFAULT_URL
    parsed = urlparse(selected)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise ValueError('MEC endpoint must be a base URL without credentials, paths or query strings')
    if not parsed.hostname or parsed.scheme not in ('http', 'https'):
        raise ValueError('MEC endpoint needs HTTPS, or HTTP on loopback for local/SSH operation')
    if parsed.scheme == 'http' and parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('Remote MEC endpoints require verified HTTPS')
    # File credentials belong to the configured host; a URL override must not
    # silently send them to another host. Explicit environment credentials apply
    # to the explicitly selected endpoint, useful for managed deployments.
    same_host = parsed.hostname == urlparse(config.get('url', '')).hostname
    client_id = os.environ.get('CF_ACCESS_CLIENT_ID') or (config.get('access_client_id') if same_host else None)
    secret = os.environ.get('CF_ACCESS_CLIENT_SECRET') or (config.get('access_client_secret') if same_host else None)
    if bool(client_id) != bool(secret):
        raise ValueError('Cloudflare Access credentials require both client ID and client secret')
    headers = {}
    if client_id and parsed.scheme == 'https':
        headers = {'CF-Access-Client-Id': client_id, 'CF-Access-Client-Secret': secret}
    api_key = os.environ.get('ALIVEMAP_API_KEY') or (config.get('api_key') if same_host else None)
    if api_key:
        headers['Authorization'] = 'Bearer '+api_key
    return selected.rstrip('/'), headers
