"""
API-key authentication for Iron-Thread. Secure by default, zero-config on your own machine.

  * IRONTHREAD_API_KEYS set     -> every endpoint except the public ones needs a valid key.
  * no keys configured          -> only requests from this machine (and addressed to localhost) are
                                   accepted; anything else gets a 403 explaining how to set a key.
  * IRONTHREAD_AUTH=off         -> explicitly open (for a network you trust). Never the default.

Public endpoints: status, health, docs, the public signing keys and the stateless verify endpoint.
That is what lets a stranger check a proof without an account.
"""
import hmac
import ipaddress
import os
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

PUBLIC_PATHS = {
    "/", "/health", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect",
    "/attestations/keys", "/attestations/verify",
}
MIN_KEY_CHARS = 16
LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}
LOCAL_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$"

_bearer = HTTPBearer(auto_error=False)
_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def new_key():
    """A fresh random API key. Run `python auth.py` to print one."""
    return "it_" + secrets.token_urlsafe(32)


def configured_keys():
    raw = os.getenv("IRONTHREAD_API_KEYS", "")
    return [k.strip() for k in raw.split(",") if k.strip()]


def _hostname(request):
    host = request.headers.get("host", "").strip()
    if host.startswith("["):                      # [::1]:8000
        return host[1:host.find("]")] if "]" in host else host
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def is_local(request):
    """
    True only for a request that came from this machine AND was addressed to localhost.
      - the Host check stops DNS-rebinding (a web page in your browser reaching your local server)
      - proxy headers mean a reverse proxy is in front, so the loopback address proves nothing
    """
    if any(h in request.headers for h in ("x-forwarded-for", "forwarded", "x-real-ip")):
        return False
    if _hostname(request).lower() not in LOCAL_HOSTNAMES:
        return False
    host = request.client.host if request.client else None
    if host is None:                              # unix domain socket
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback


def require_auth(
    request: Request,
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    header_key: Optional[str] = Depends(_header),
):
    if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
        return

    keys = configured_keys()
    if keys:
        if any(len(k) < MIN_KEY_CHARS for k in keys):
            raise HTTPException(status_code=500, detail=(
                f"IRONTHREAD_API_KEYS contains a key shorter than {MIN_KEY_CHARS} characters. "
                "Generate one with: python auth.py"))
        presented = bearer.credentials if bearer else header_key
        if presented and any(hmac.compare_digest(presented.encode(), k.encode()) for k in keys):
            return
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid API key. Send 'Authorization: Bearer <key>' or 'X-API-Key: <key>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if os.getenv("IRONTHREAD_AUTH", "").strip().lower() == "off":
        return
    if is_local(request):
        return
    raise HTTPException(status_code=403, detail=(
        "No API key is configured, so this server only accepts requests from the machine it runs on. "
        "To expose it, set IRONTHREAD_API_KEYS=<secret> (generate one with: python auth.py). "
        "To run it open on a network you trust, set IRONTHREAD_AUTH=off."))


def cors_settings():
    """
    Browsers may only talk to this server from localhost pages unless you say otherwise:
    IRONTHREAD_CORS_ORIGINS="https://app.example.com,https://other.example.com"  (or "*" to open it up).
    Credentials are off: we authenticate with headers, never cookies.
    """
    raw = os.getenv("IRONTHREAD_CORS_ORIGINS", "").strip()
    base = {"allow_methods": ["*"], "allow_headers": ["*"], "allow_credentials": False}
    if raw == "*":
        return {**base, "allow_origins": ["*"]}
    if raw:
        return {**base, "allow_origins": [o.strip() for o in raw.split(",") if o.strip()]}
    return {**base, "allow_origin_regex": LOCAL_ORIGIN_REGEX}


if __name__ == "__main__":
    print(new_key())
