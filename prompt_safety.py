"""Defence-in-depth minimization for optional approved-model egress.

This is not a complete DLP engine: it strips recognizable secrets/PII and
credential-bearing URLs while keeping technical field names and evidence text.
All calls still require explicit approved-model company consent.
"""
import re
from urllib.parse import urlsplit, urlunsplit

# Normalize snake_case / camelCase / HTTP header punctuation consistently.
_SENSITIVE_KEYS = frozenset({
    "password", "passphrase", "token", "accesstoken", "refreshtoken",
    "apikey", "xapikey", "clientsecret", "secret", "authorization",
    "authorizationheader", "cookie", "setcookie", "sessioncookie",
    "sessiontoken", "sessionid", "totp", "otpauth", "privatekey",
    "bearertoken", "emailaddress",
})
_SENSITIVE_SUFFIXES = ("password", "apikey", "clientsecret", "privatekey", "authtoken")


def sensitive_key(key):
    normalized = re.sub(r"[^a-z0-9]", "", str(key).casefold())
    return normalized in _SENSITIVE_KEYS or normalized.endswith(_SENSITIVE_SUFFIXES)


_URL = re.compile(r"(?i)https?://[^\s<>\"']+")
_EMAIL = re.compile(r"(?i)(?<![\w.+-])[A-Z0-9_.+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])")
_PHONE = re.compile(r"(?<!\w)\+[1-9]\d{8,14}\b")
_LABELED_PHONE = re.compile(
    r"(?i)\b(?:phone|telephone|mobile|tel|contact[_ ]?number)"
    r"\s*[:=]\s*\+?[\d() .-]{8,}\d")
_ACCESS_KEYS = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9_]{15,}|github_pat_[A-Za-z0-9_]{15,}|"
    r"AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{15,})\b")
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")


def _safe_url(match):
    raw = match.group(0)
    url = raw.rstrip(".,;)]}")
    punctuation = raw[len(url):]
    try:
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in ("https", "http") or not parsed.hostname:
            return "[REDACTED_URL]" + punctuation
        if parsed.username is not None or parsed.password is not None:
            return "[REDACTED_URL]" + punctuation
        if any(char in parsed.netloc for char in ("@", "\\", "\n", "\r")):
            return "[REDACTED_URL]" + punctuation
        # Query and fragments can contain auth codes, customer IDs and session tokens.
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", "")) + punctuation
    except ValueError:
        return "[REDACTED_URL]" + punctuation


def strip_sensitive_text(value):
    if not isinstance(value, str):
        raise TypeError("Sensitive text sanitizer requires a string.")
    value = _PRIVATE_KEY.sub("[REDACTED_PRIVATE_KEY]", value)
    value = _URL.sub(_safe_url, value)
    value = _ACCESS_KEYS.sub("[REDACTED_CREDENTIAL]", value)
    value = _EMAIL.sub("[REDACTED_EMAIL]", value)
    value = _LABELED_PHONE.sub("[REDACTED_PHONE]", value)
    value = _PHONE.sub("[REDACTED_PHONE]", value)
    return value
