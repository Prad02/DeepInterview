"""LLM adapter factory + real adapters (lazy-imported SDKs).

``get_llm(settings)`` returns the deterministic :class:`MockLLM` unless an LLM
provider is selected *and* its API key is present; otherwise it logs a warning
and falls back to the mock. Real adapters import their SDK inside methods so the
module imports cleanly with no SDK installed.
"""

from __future__ import annotations

import asyncio
import json
import random
from typing import TYPE_CHECKING, Any

from ..logging import get_logger
from .base import LLMAdapter
from .mock import MockLLM

if TYPE_CHECKING:
    from ..config import Settings

log = get_logger(__name__)

# Per-call ceiling so a stalled provider call can never hang a pipeline forever
# (the prep graph's per-node try/except only fires once the call RETURNS).
_DEFAULT_TIMEOUT_SEC = 90.0

# Custom OpenAI-compatible proxies (often behind Cloudflare) can reject a
# fraction of *concurrent* requests with 421 Misdirected Request due to HTTP
# connection coalescing — the sequential prep calls succeed, but the parallel
# scoring/report fan-out trips it. For a custom base_url we therefore cap
# concurrency and retry these transient statuses so the fan-out completes.
_OPENAI_RETRY_STATUSES = frozenset({421, 429, 500, 502, 503, 504})
_OPENAI_MAX_RETRIES = 4
_OPENAI_MAX_CONCURRENCY = 3
_openai_semaphore: asyncio.Semaphore | None = None


def _get_openai_semaphore() -> asyncio.Semaphore:
    """Lazily create the shared concurrency gate (bound to the running loop)."""
    global _openai_semaphore
    if _openai_semaphore is None:
        _openai_semaphore = asyncio.Semaphore(_OPENAI_MAX_CONCURRENCY)
    return _openai_semaphore


def _schema_prompt(system: str, schema: type) -> str:
    """Append the JSON Schema to the system prompt (provider-agnostic).

    Both Gemini's ``response_schema`` and OpenAI's strict structured outputs
    reject free-form maps like our ``LocalizedText = dict[str, str]``
    (additionalProperties), so the reliable cross-provider pattern is JSON mode
    + the schema in the prompt + Pydantic validation of the result.
    """
    schema_json = json.dumps(schema.model_json_schema())
    return (
        f"{system}\n\nReturn ONLY a single JSON value that conforms to this "
        f"JSON Schema (no markdown, no commentary):\n{schema_json}"
    )


def _loads_json(text: str) -> Any:
    """Parse JSON from an LLM response, tolerating ```json fences, stray prose, and
    *trailing* "Extra data".

    The keystone failure this fixes: the question planner has the largest schema,
    so its real Gemini response is the biggest — and a complete JSON object was
    sometimes FOLLOWED by extra content (a second object / trailing commentary).
    Plain ``json.loads`` raises ``Extra data`` on that, and the old greedy
    ``\\{.*\\}`` fallback spanned to the LAST brace (swallowing the trailing junk
    into invalid JSON), so every plan silently fell back to the generic mock —
    an interview that asks one question literally titled "mock". ``raw_decode``
    returns the FIRST complete JSON value and ignores anything after it.
    """
    import re

    t = (text or "").strip()
    # Strip a wrapping ```json ... ``` / ``` ... ``` markdown fence, if present.
    if t.startswith("```"):
        t = re.sub(r"^```[^\n]*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t).strip()
    # Fast path: a single clean JSON value.
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # Tolerant path: decode the first complete JSON value starting at the first
    # '{' or '[', ignoring any trailing data (raw_decode is "Extra data"-safe).
    decoder = json.JSONDecoder()
    for i, ch in enumerate(t):
        if ch in "{[":
            try:
                obj, _end = decoder.raw_decode(t, i)
                return obj
            except json.JSONDecodeError:
                continue
    raise json.JSONDecodeError("no JSON value found in LLM response", t, 0)


class GeminiLLM:
    """Google Gemini via ``google-genai`` (lazy import)."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_sec: float = _DEFAULT_TIMEOUT_SEC,
    ) -> None:
        # No default model: ids retire fast, so the current id lives in ONE
        # place (Settings.gemini_model) and must be passed in explicitly.
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_sec

    def _client(self) -> Any:
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - depends on optional SDK
            raise RuntimeError(
                "google-genai is not installed; install the 'gemini' extra."
            ) from exc
        return genai.Client(api_key=self._api_key)

    async def complete_text(self, *, system: str, user: str) -> str:
        client = self._client()
        resp = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=self._model,
                contents=user,
                config={"system_instruction": system},
            ),
            timeout=self._timeout,
        )
        return resp.text or ""

    async def complete_json(self, *, system: str, user: str, schema: type) -> Any:
        # JSON mode + schema-in-prompt (see _schema_prompt for why not
        # ``response_schema``).
        client = self._client()
        resp = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=self._model,
                contents=user,
                config={
                    "system_instruction": _schema_prompt(system, schema),
                    "response_mime_type": "application/json",
                },
            ),
            timeout=self._timeout,
        )
        return schema.model_validate(_loads_json(resp.text or "{}"))


class OpenAILLM:
    """OpenAI via the ``openai`` SDK (lazy import)."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_sec: float = _DEFAULT_TIMEOUT_SEC,
        base_url: str | None = None,
    ) -> None:
        # No default model — see GeminiLLM.__init__; Settings.openai_model is
        # the single source of truth.
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_sec
        # Optional OpenAI-compatible endpoint (proxy/gateway/self-host). None =>
        # the SDK default (api.openai.com).
        self._base_url = base_url
        self._client_obj: Any = None

    def _client(self) -> Any:
        if self._client_obj is not None:
            return self._client_obj
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - depends on optional SDK
            raise RuntimeError(
                "openai is not installed; install the 'openai' extra."
            ) from exc
        if self._base_url:
            import httpx

            # Two custom-endpoint accommodations:
            #  - Some gateways reject the SDK's default "OpenAI/Python ..."
            #    User-Agent (403 "Your request was blocked."), so send a neutral
            #    UA.
            #  - Disable HTTP keep-alive (fresh connection per request) to reduce
            #    the connection-coalescing 421s; the retry loop in `_create`
            #    mops up the rest. `max_retries=0` because we own the retry.
            self._client_obj = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                default_headers={"User-Agent": "deepinterview-agent/0.2"},
                max_retries=0,
                http_client=httpx.AsyncClient(
                    timeout=self._timeout,
                    limits=httpx.Limits(max_keepalive_connections=0, max_connections=6),
                ),
            )
        else:
            self._client_obj = AsyncOpenAI(api_key=self._api_key)
        return self._client_obj

    async def _create(self, **kwargs: Any) -> Any:
        """Chat-completion call with a timeout, plus (for custom endpoints) a
        concurrency cap and retry on transient proxy statuses (e.g. 421)."""
        client = self._client()
        if not self._base_url:
            return await asyncio.wait_for(
                client.chat.completions.create(**kwargs), timeout=self._timeout
            )
        from openai import APIConnectionError, APIStatusError

        sem = _get_openai_semaphore()
        async with sem:
            last_exc: Exception | None = None
            for attempt in range(_OPENAI_MAX_RETRIES + 1):
                try:
                    return await asyncio.wait_for(
                        client.chat.completions.create(**kwargs), timeout=self._timeout
                    )
                except (APIStatusError, APIConnectionError) as exc:
                    last_exc = exc
                    status = getattr(exc, "status_code", None)
                    retriable = isinstance(exc, APIConnectionError) or (
                        status in _OPENAI_RETRY_STATUSES
                    )
                    if attempt >= _OPENAI_MAX_RETRIES or not retriable:
                        raise
                    await asyncio.sleep(0.4 * (attempt + 1) + random.random() * 0.3)
            assert last_exc is not None  # pragma: no cover
            raise last_exc

    async def complete_text(self, *, system: str, user: str) -> str:
        resp = await self._create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""

    async def complete_json(self, *, system: str, user: str, schema: type) -> Any:
        # JSON mode + schema-in-prompt, NOT strict structured outputs: OpenAI's
        # strict mode rejects free-form maps (additionalProperties) like our
        # ``LocalizedText = dict[str, str]``, which would silently break the
        # question planner (every plan falling back to mock). Same pattern as
        # the Gemini adapter; Pydantic validates the result either way.
        resp = await self._create(
            model=self._model,
            messages=[
                {"role": "system", "content": _schema_prompt(system, schema)},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
        )
        return schema.model_validate(_loads_json(resp.choices[0].message.content or "{}"))


def get_llm(settings: Settings) -> LLMAdapter:
    """Choose an LLM adapter from settings, falling back to the mock."""
    provider = (settings.llm_provider or "mock").lower()
    if provider == "mock":
        return MockLLM()
    timeout = getattr(settings, "llm_call_timeout_sec", _DEFAULT_TIMEOUT_SEC)
    if provider == "gemini":
        if settings.gemini_api_key:
            return GeminiLLM(settings.gemini_api_key, settings.gemini_model, timeout)
        log.warning("llm_provider=gemini but gemini_api_key is missing; using MockLLM.")
        return MockLLM()
    if provider == "openai":
        if settings.openai_api_key:
            return OpenAILLM(
                settings.openai_api_key,
                settings.openai_model,
                timeout,
                base_url=getattr(settings, "openai_base_url", None),
            )
        log.warning("llm_provider=openai but openai_api_key is missing; using MockLLM.")
        return MockLLM()
    log.warning("Unknown llm_provider=%r; using MockLLM.", provider)
    return MockLLM()
