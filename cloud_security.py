"""Single-user trusted-proxy boundary for a private cloud *pilot*.

The app is NEVER directly published. Nginx validates oauth2-proxy OIDC auth,
injects an independent long shared secret and verified email, and only then
forwards to this internal-only app container.
"""
import hmac
import os
from urllib.parse import urlparse


def cloud_configuration(env=None):
    env = env if env is not None else os.environ
    if env.get("CCON_CLOUD_MODE") != "1":
        raise ValueError("Cloud HTTP requires CCON_CLOUD_MODE=1.")
    origin = env.get("CCON_PUBLIC_ORIGIN", "")
    url = urlparse(origin)
    if (url.scheme != "https" or not url.hostname or url.username or url.password or
            url.params or url.query or url.fragment or url.path not in ("", "/")):
        raise ValueError("Cloud origin must be a single HTTPS hostname.")
    email = env.get("CCON_AUTHORIZED_EMAIL", "").strip().lower()
    secret = env.get("CCON_PROXY_SHARED_SECRET", "")
    if "@" not in email or any(c in email for c in "\r\n") or len(email) > 254:
        raise ValueError("A single authorized email is required.")
    if len(secret) < 32 or "\n" in secret or "\r" in secret:
        raise ValueError("Proxy shared secret must be at least 32 characters.")
    return {"origin": origin.rstrip("/"), "netloc": url.netloc,
            "email": email, "secret": secret}


def authorized(headers, config, method="GET"):
    """Authentication check must apply to *all* static and API endpoints."""
    if headers.get("Host") != config["netloc"]:
        return False
    token = headers.get("X-CCON-Proxy-Secret", "")
    if not hmac.compare_digest(token.encode(), config["secret"].encode()):
        return False
    email = headers.get("X-CCON-Verified-Email", "").lower()
    if not hmac.compare_digest(email.encode(), config["email"].encode()):
        return False
    if method not in ("GET", "HEAD") and headers.get("Origin") != config["origin"]:
        return False
    return True
