from urllib.request import Request as UrlRequest
"""Read-only integration connectivity checks for Nexus Requests.

No torrent, library, tagging, or scheduling mutations. qBittorrent login
creates an authentication session only.
"""
import asyncio
import ipaddress
import json
import socket
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import (
    HTTPCookieProcessor, HTTPRedirectHandler, ProxyHandler, Request,
    build_opener,
)

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from config_store import ConfigStore, SERVICES
from integration_api import _check_csrf, _session_fingerprint

router = APIRouter(prefix='/api/integrations')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _base_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError('Invalid server URL')
    parsed = urlsplit(value.strip())
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment):
        raise ValueError('Use an HTTP(S) server URL without credentials or query')
    try:
        port = parsed.port
    except ValueError:
        raise ValueError('Invalid server port') from None
    if port is not None and not 1 <= port <= 65535:
        raise ValueError('Invalid server port')
    # Reject metadata/link-local/multicast destinations; LAN hosts are supported.
    try:
        addresses = socket.getaddrinfo(parsed.hostname, port or (443 if parsed.scheme == 'https' else 80))
    except socket.gaierror:
        raise ValueError('Server hostname could not be resolved') from None
    for entry in addresses:
        ip = ipaddress.ip_address(entry[4][0].split('%')[0])
        if ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
            raise ValueError('Server address is not allowed')
    return value.strip().rstrip('/')


def _get(opener, url, headers=None):
    with opener.open(UrlRequest(url, headers=headers or {}, method='GET'), timeout=6) as response:
        if response.status != 200:
            raise ValueError(f'HTTP {response.status}')
        return response.read(32768)


def _run_test(service, config):
    base = _base_url(config.get('url'))
    opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPCookieProcessor(CookieJar()))
    if service == 'qbittorrent':
        username, password = config.get('username'), config.get('password')
        if not username or not password:
            raise ValueError('Username and password required')
        data = urlencode({'username': username, 'password': password}).encode()
        req = UrlRequest(base + '/api/v2/auth/login', data=data,
                      headers={'Content-Type': 'application/x-www-form-urlencoded',
                               'Referer': base + '/'}, method='POST')
        with opener.open(req, timeout=6) as response:
            if response.status != 200 or response.read(100).strip() != b'Ok.':
                raise ValueError('Authentication failed')
        version = _get(opener, base + '/api/v2/app/version', {'Referer': base + '/'})
        if not version.strip():
            raise ValueError('Empty qBittorrent version response')
    else:
        key = config.get('api_key')
        if not key:
            raise ValueError('API key required')
        endpoint = '/api/v1/status' if service == 'seerr' else '/api/v3/system/status'
        payload = _get(opener, base + endpoint, {'X-Api-Key': key})
        try:
            response = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            raise ValueError('Invalid service response') from None
        if not isinstance(response, dict):
            raise ValueError('Unexpected service response')
    return {'service': service, 'ok': True, 'message': 'Connection successful'}


@router.post('/{service}/test')
async def test_connection(service: str, request: Request):
    _session_fingerprint(request)
    _check_csrf(request)
    if service not in ('seerr', 'qbittorrent', 'radarr', 'sonarr'):
        raise HTTPException(status_code=404, detail='Connection test unavailable')
    try:
        config = ConfigStore().load_internal(service)
        result = await asyncio.to_thread(_run_test, service, config)
    except HTTPError as exc:
        result = {'service': service, 'ok': False, 'message': f'HTTP {exc.code} from service'}
    except (URLError, TimeoutError, OSError):
        result = {'service': service, 'ok': False, 'message': 'Connection failed or timed out'}
    except ValueError as exc:
        result = {'service': service, 'ok': False, 'message': str(exc)}
    return JSONResponse(result, headers={'Cache-Control': 'no-store'})
