"""Strict configuration for the Architecture Assistant runtime.

Every value is server-side. The OpenCode password is a :class:`SecretStr` so it
can never be rendered by accident, and nothing in this module logs or returns a
secret value. The assistant is disabled by default: when ``enabled`` is false no
OpenCode endpoint is ever contacted.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_OPENCODE_VERSION = "2.0.30"
DEFAULT_OPENCODE_BASE_URL = "http://opencode:4096"
DEFAULT_AUTH_USERNAME = "opencode"
DEFAULT_PROFILE_PATH = "assistant-runtime/opencode.json"
DEFAULT_TOOLS_PATH = "assistant-runtime/assistant-tools.json"
DEFAULT_OPENAPI_SNAPSHOT_PATH = "assistant-runtime/openapi/opencode-2.0.30.json"

# An explicit, bounded agent step budget. Kept in step with the tool-call budget
# in later slices; the runtime disables tools once the step limit is reached.
MAX_AGENT_STEPS = 12

# Response/stream ceilings enforced by the adapter before anything is retained
# or forwarded. The runtime's own `tool_output` limit spills to disk instead of
# truncating, so the adapter must bound results itself.
DEFAULT_MAX_RESPONSE_BYTES = 262_144
DEFAULT_MAX_STREAM_EVENT_BYTES = 65_536
DEFAULT_MAX_CONTRACT_BYTES = 1_048_576
#: A session transcript legitimately accumulates every step of a multi-step turn
#: (bounded tool inputs/outputs and assistant text), so it is read through its own
#: larger ceiling rather than the tight per-response cap. Still hard-bounded.
DEFAULT_MAX_TRANSCRIPT_BYTES = 2_097_152
HARD_MAX_RESPONSE_BYTES = 4_194_304


def repo_root() -> Path:
    """Repository root, derived from this file's location (``api/app/assistant``)."""
    return Path(__file__).resolve().parents[3]


class AssistantSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ASSISTANT_",
        env_file=".env",
        extra="ignore",
    )

    enabled: bool = False
    """Global kill switch. When false the assistant never contacts OpenCode."""

    opencode_base_url: str = DEFAULT_OPENCODE_BASE_URL
    opencode_version: str = DEFAULT_OPENCODE_VERSION
    opencode_auth_username: str = DEFAULT_AUTH_USERNAME
    opencode_password: SecretStr = SecretStr("")

    opencode_profile_path: str = DEFAULT_PROFILE_PATH
    opencode_tools_path: str = DEFAULT_TOOLS_PATH
    opencode_openapi_snapshot_path: str = DEFAULT_OPENAPI_SNAPSHOT_PATH

    tool_service_token: SecretStr = SecretStr("")
    """Static service token the OpenCode plugin presents to the internal tool
    dispatch endpoint. Empty means internal dispatch is refused (fail closed)."""

    tool_service_token_previous: SecretStr = SecretStr("")
    """Optional previous token accepted during rotation. Never logged."""

    connect_timeout_seconds: float = 2.0
    request_timeout_seconds: float = 10.0
    stream_timeout_seconds: float = 30.0
    probe_timeout_seconds: float = 5.0
    probe_cache_seconds: float = 15.0

    max_response_bytes: int = Field(default=DEFAULT_MAX_RESPONSE_BYTES, gt=0)
    max_stream_event_bytes: int = Field(default=DEFAULT_MAX_STREAM_EVENT_BYTES, gt=0)
    max_contract_bytes: int = Field(default=DEFAULT_MAX_CONTRACT_BYTES, gt=0)
    """Dedicated, larger cap for the OpenAPI contract document fetched by the
    startup probe. Lifecycle responses stay tightly bounded by
    ``max_response_bytes``; the pinned contract document is ~270 KiB."""

    max_transcript_bytes: int = Field(default=DEFAULT_MAX_TRANSCRIPT_BYTES, gt=0)
    """Dedicated, larger cap for the OpenCode session transcript
    (``GET /api/session/{id}/message``), which accumulates across a multi-step
    turn. Every other lifecycle response stays bounded by ``max_response_bytes``."""

    provider_fallback_enabled: bool = False
    """Automatic provider fallback is never permitted for the assistant."""

    correlation_header: str = "X-Assistant-Correlation-Id"

    @field_validator("opencode_base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("assistant opencode_base_url must be an absolute http(s) URL")
        if parsed.username or parsed.password:
            raise ValueError("assistant opencode_base_url must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("assistant opencode_base_url must not contain a query or fragment")
        return value.rstrip("/")

    @field_validator(
        "connect_timeout_seconds",
        "request_timeout_seconds",
        "stream_timeout_seconds",
        "probe_timeout_seconds",
    )
    @classmethod
    def _validate_timeouts(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("assistant timeouts must be positive")
        return value

    @field_validator("max_response_bytes", "max_contract_bytes", "max_transcript_bytes")
    @classmethod
    def _validate_max_response_bytes(cls, value: int) -> int:
        if value > HARD_MAX_RESPONSE_BYTES:
            raise ValueError("assistant response size limit exceeds the hard ceiling")
        return value

    # -- derived helpers -------------------------------------------------

    def password(self) -> str:
        return self.opencode_password.get_secret_value()

    def has_password(self) -> bool:
        return bool(self.password())

    def service_token(self) -> str:
        return self.tool_service_token.get_secret_value()

    def has_service_token(self) -> bool:
        return bool(self.service_token())

    def service_tokens(self) -> tuple[str, ...]:
        """Current token plus an optional previous token for rotation."""
        tokens = [self.service_token()]
        previous = self.tool_service_token_previous.get_secret_value()
        if previous:
            tokens.append(previous)
        return tuple(token for token in tokens if token)

    def resolve_path(self, configured: str) -> Path:
        path = Path(configured)
        return path if path.is_absolute() else repo_root() / path

    def profile_path(self) -> Path:
        return self.resolve_path(self.opencode_profile_path)

    def tools_path(self) -> Path:
        return self.resolve_path(self.opencode_tools_path)

    def openapi_snapshot_path(self) -> Path:
        return self.resolve_path(self.opencode_openapi_snapshot_path)


@lru_cache(maxsize=1)
def get_assistant_settings() -> AssistantSettings:
    return AssistantSettings()


# Convenience singleton mirroring the existing ``app.config.settings`` pattern.
settings = get_assistant_settings()
