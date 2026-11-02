"""Loopback-only setup; no token is accepted or returned by these endpoints."""
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import telegram_bot

router = APIRouter(prefix='/api/telegram')
LOCAL_HOSTS = {'127.0.0.1', 'localhost', '::1'}
LOCAL_PORTS = {5173, 5174, 8000, 8765}


def local_request(request):
    if not request.client or request.client.host not in LOCAL_HOSTS:
        raise HTTPException(403, 'Use Telegram settings from the local app.')
    try:
        host = urlsplit('http://' + request.headers.get('host', ''))
        if host.hostname not in LOCAL_HOSTS or (host.port or 80) not in LOCAL_PORTS:
            raise ValueError()
        origin = request.headers.get('origin')
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme != 'http' or parsed.hostname not in LOCAL_HOSTS or (parsed.port or 80) not in LOCAL_PORTS:
                raise ValueError()
        if request.headers.get('sec-fetch-site') == 'cross-site':
            raise ValueError()
        if request.method != 'GET' and request.headers.get('x-garmin-local-action') != 'telegram-setup':
            raise ValueError()
    except ValueError:
        raise HTTPException(403, 'Use Telegram settings from the local app.') from None


class PairingRequest(BaseModel):
    timezone: str = Field(max_length=100)
    model_config = {'extra': 'forbid'}


@router.get('/status')
def status(request: Request):
    local_request(request)
    return telegram_bot.status()


@router.post('/pairing')
def pairing(request: Request, body: PairingRequest):
    local_request(request)
    try:
        return telegram_bot.configure(body.timezone)
    except (telegram_bot.TelegramError, ValueError) as error:
        raise HTTPException(400, str(error)) from None


@router.post('/disable')
def disable(request: Request):
    local_request(request)
    return telegram_bot.disable()


@router.post('/retry-credentials')
def retry_credentials(request: Request):
    local_request(request)
    try:
        return telegram_bot.retry_credentials()
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
