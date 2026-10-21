"""Authenticated integration settings API for Nexus Requests WebGUI.

Mount with app.include_router(integration_router) after existing auth middleware.
Never return saved credential values to clients.
"""
import hashlib
import hmac
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from itsdangerous import BadSignature, SignatureExpired

from auth import get_serializer
from auth_routes import current_admin
from config_store import ConfigStore, SERVICES
from scheduler_validation import validate_scheduler
from global_save_validation import validate_global_save

router = APIRouter(prefix='/api/integrations')
TOKEN_AGE = 3600


def _session_fingerprint(request):
    session = request.cookies.get('nexus_session', '')
    if not session or not current_admin(request):
        raise HTTPException(status_code=401, detail='Authentication required')
    return hashlib.sha256(session.encode('utf-8')).hexdigest()


def _require_same_origin(request):
    origin = request.headers.get('origin')
    if not origin:
        raise HTTPException(status_code=403, detail='Origin header required')
    target = urlsplit(str(request.base_url))
    source = urlsplit(origin)
    if (source.scheme, source.netloc) != (target.scheme, target.netloc):
        raise HTTPException(status_code=403, detail='Origin mismatch')


def _check_csrf(request):
    _require_same_origin(request)
    token = request.headers.get('x-csrf-token', '')
    try:
        payload = get_serializer().loads(token, salt='integration-csrf', max_age=TOKEN_AGE)
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        raise HTTPException(status_code=403, detail='Invalid CSRF token')
    expected = _session_fingerprint(request)
    if not isinstance(payload, dict) or not isinstance(payload.get('session'), str) or not hmac.compare_digest(payload['session'], expected):
        raise HTTPException(status_code=403, detail='Invalid CSRF token')


@router.get('/csrf')
async def integration_csrf(request: Request):
    session = _session_fingerprint(request)
    token = get_serializer().dumps({'session': session}, salt='integration-csrf')
    return JSONResponse({'csrf_token': token}, headers={'Cache-Control': 'no-store'})


@router.get('/{service}')
async def integration_status(service: str, request: Request):
    _session_fingerprint(request)
    if service not in SERVICES:
        raise HTTPException(status_code=404, detail='Unknown integration')
    store = ConfigStore()
    status = store.public_status(service)
    saved = store.load_internal(service)
    status['display_values'] = {
        key: value for key, value in saved.items()
        if key in ('url', 'username')
    }
    return JSONResponse(status, headers={'Cache-Control': 'no-store'})





@router.post('/discord/connect-and-test')
async def integration_discord_connect_and_test(request: Request):
    """Verify Discord, prepare channel, and send test notification."""
    _session_fingerprint(request)
    _check_csrf(request)

    content_type = request.headers.get('content-type', '')
    if content_type.split(';', 1)[0].strip().lower() != 'application/json':
        raise HTTPException(status_code=415, detail='JSON required')

    raw = await request.body()
    if len(raw) > 8192:
        raise HTTPException(status_code=413, detail='Payload too large')

    try:
        import json
        import asyncio

        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError('Invalid request')

        token = payload.get('bot_token', '')
        guild_id = payload.get('guild_id', '')

        if not isinstance(token, str) or not isinstance(guild_id, str):
            raise ValueError('Invalid Discord credentials')

        from discord_setup import connect_discord_and_send_test

        result = await asyncio.to_thread(
            connect_discord_and_send_test, token, guild_id
        )

        return JSONResponse(
            result,
            headers={'Cache-Control': 'no-store'}
        )

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=502,
            detail='Discord setup failed'
        )


@router.post('/discord/create-channel')
async def integration_discord_create_channel(request: Request):
    """Find or create the Nexus Requests Discord notification channel."""
    _session_fingerprint(request)
    _check_csrf(request)

    content_type = request.headers.get('content-type', '')
    if content_type.split(';', 1)[0].strip().lower() != 'application/json':
        raise HTTPException(status_code=415, detail='JSON required')

    raw = await request.body()
    if len(raw) > 8192:
        raise HTTPException(status_code=413, detail='Payload too large')

    try:
        import json
        import asyncio

        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError('Invalid request')

        token = payload.get('bot_token', '')
        guild_id = payload.get('guild_id', '')

        if not isinstance(token, str) or not isinstance(guild_id, str):
            raise ValueError('Invalid Discord credentials')

        from discord_setup import ensure_notification_channel

        result = await asyncio.to_thread(
            ensure_notification_channel, token, guild_id
        )

        return JSONResponse(result, headers={'Cache-Control': 'no-store'})

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=502,
            detail='Discord channel setup failed'
        )


@router.post('/discord/test')
async def integration_discord_test(request: Request):
    """Verify Discord credentials and permissions without saving them."""
    _session_fingerprint(request)
    _check_csrf(request)

    content_type = request.headers.get('content-type', '')
    if content_type.split(';', 1)[0].strip().lower() != 'application/json':
        raise HTTPException(status_code=415, detail='JSON required')

    raw = await request.body()
    if len(raw) > 8192:
        raise HTTPException(status_code=413, detail='Payload too large')

    try:
        import json
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError('Invalid request')

        token = payload.get('bot_token', '')
        guild_id = payload.get('guild_id', '')

        if not isinstance(token, str) or not isinstance(guild_id, str):
            raise ValueError('Invalid Discord credentials')

        from discord_setup import test_discord_connection
        import asyncio

        result = await asyncio.to_thread(
            test_discord_connection, token, guild_id
        )
        return JSONResponse(result, headers={'Cache-Control': 'no-store'})

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=502,
            detail='Discord connection test failed'
        )


@router.post('/save-all')
async def integration_save_all(request: Request):
    _session_fingerprint(request)
    _check_csrf(request)

    content_type = request.headers.get('content-type', '')
    if content_type.split(';', 1)[0].strip().lower() != 'application/json':
        raise HTTPException(status_code=415, detail='JSON required')

    raw = await request.body()
    if len(raw) > 32768:
        raise HTTPException(status_code=413, detail='Payload too large')

    try:
        import json
        configurations = json.loads(raw)
        if not isinstance(configurations, dict):
            raise ValueError()
        for service, settings in configurations.items():
            if not isinstance(settings, dict):
                raise ValueError()
            if any(len(v) > 4096 for v in settings.values()
                   if isinstance(v, str)):
                raise ValueError()
        if 'scheduler' in configurations:
            validate_scheduler(configurations['scheduler'])
        store = ConfigStore()
        validate_global_save(configurations, store)
        store.save_all(configurations)
    except (ValueError, UnicodeDecodeError, TypeError):
        raise HTTPException(status_code=422, detail='Invalid configuration')

    return JSONResponse(
        {'ok': True},
        headers={'Cache-Control': 'no-store'}
    )

@router.post('/{service}')
async def integration_save(service: str, request: Request):
    _session_fingerprint(request)
    if service not in SERVICES:
        raise HTTPException(status_code=404, detail='Unknown integration')
    _check_csrf(request)
    if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
        raise HTTPException(status_code=415, detail='JSON required')
    if request.headers.get('content-length', '').isdigit() and int(request.headers['content-length']) > 8192:
        raise HTTPException(status_code=413, detail='Payload too large')
    raw = await request.body()
    if len(raw) > 8192:
        raise HTTPException(status_code=413, detail='Payload too large')
    try:
        import json
        settings = json.loads(raw)
        if not isinstance(settings, dict):
            raise ValueError()
        if any(len(v) > 4096 for v in settings.values() if isinstance(v, str)):
            raise ValueError()
        if service == 'scheduler':
            validate_scheduler(settings)
        ConfigStore().save(service, settings)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail='Invalid configuration')
    return JSONResponse(ConfigStore().public_status(service), headers={'Cache-Control': 'no-store'})


@router.get('/scheduler/settings')
async def scheduler_settings(request: Request):
    _session_fingerprint(request)
    defaults = {
        'enabled': 'false',
        'start_time': '02:00',
        'end_time': '06:00',
        'timezone': 'America/New_York',
    }
    saved = ConfigStore().load_internal('scheduler')
    return JSONResponse(
        {**defaults, **saved},
        headers={'Cache-Control': 'no-store'}
    )

@router.post('/discord/activate')
async def integration_discord_activate(request: Request):
    """Verify Discord access and securely save its configuration."""
    _session_fingerprint(request)
    _check_csrf(request)

    if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
        raise HTTPException(status_code=415, detail='JSON required')

    raw = await request.body()
    if len(raw) > 8192:
        raise HTTPException(status_code=413, detail='Payload too large')

    import asyncio
    import json

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError('Invalid request')

        token = payload.get('bot_token')
        guild_id = payload.get('guild_id')

        if not isinstance(token, str) or not token.strip():
            raise ValueError('Bot token required')
        if not isinstance(guild_id, str) or not (
            17 <= len(guild_id) <= 20 and guild_id.isascii() and guild_id.isdecimal()
        ):
            raise ValueError('Valid Discord Server ID required')

        from discord_setup import ensure_notification_channel

        result = await asyncio.to_thread(
            ensure_notification_channel, token, guild_id
        )

        channel_id = str(result['channel_id'])

        ConfigStore().save('discord', {
            'bot_token': token,
            'guild_id': guild_id,
            'channel_id': channel_id,
        })

        from bot_service import restart_bot, BotServiceError

        try:
            await asyncio.to_thread(restart_bot)
        except BotServiceError:
            raise HTTPException(
                status_code=503,
                detail='Discord settings saved, but the bot could not be restarted'
            )

        return JSONResponse({
            'success': True,
            'configured': True,
            'channel_name': 'nexus-requests',
        }, headers={'Cache-Control': 'no-store'})

    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail='Invalid Discord activation configuration')
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail='Discord activation failed')
