"""Application settings.

All fields are optional so the app boots with ZERO environment configured: every
provider defaults to ``"mock"`` and every key is ``None``. Real providers are
opt-in via env vars; if a provider is selected but its key is missing, the
adapter factories log a warning and fall back to the deterministic mock.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- provider selection (mock by default = fully offline) ----------------
    llm_provider: str = "mock"
    stt_provider: str = "mock"
    tts_provider: str = "mock"
    search_provider: str = "mock"
    embeddings_provider: str = "mock"

    # --- live voice mode -----------------------------------------------------
    # "cascaded"        = separate STT -> LLM -> TTS providers (the original path;
    #                     needs Deepgram/Soniox + Cartesia/ElevenLabs + an LLM).
    # "gemini_realtime" = Gemini Live speech-to-speech: a single GEMINI_API_KEY
    #                     does listen + think + speak, no STT/TTS providers. The
    #                     leanest voice setup (only Gemini + LiveKit). Override via
    #                     LIVE_MODE. Prep/scoring still use LLM_PROVIDER separately.
    #   "openai_realtime"  = OpenAI Realtime speech-to-speech (gpt-realtime): one
    #                     OpenAI key does listen + think + speak. Uses the REAL
    #                     api.openai.com (NOT the OPENAI_BASE_URL proxy, which
    #                     can't relay the realtime WebSocket).
    live_mode: str = "cascaded"
    # Gemini Live model + voice for gemini_realtime mode. Valid model ids come
    # from livekit-plugins-google's LiveAPIModels; voice from its Voice list.
    # The native-audio model is the one compatible with the agent's proactive
    # speaking (session.generate_reply — how the interviewer asks each question);
    # the faster flash-live model raises "generate_reply is not compatible", so
    # it can't drive this interview flow. Override via GEMINI_REALTIME_MODEL.
    gemini_realtime_model: str = "gemini-2.5-flash-native-audio-preview-12-2025"
    gemini_realtime_voice: str = "Puck"
    # How long a silence (ms) before the model decides the candidate finished
    # their turn. The Live API default is short (~800ms), which cuts people off
    # mid-thought; this raises it so natural pauses don't end the turn. Pair with
    # LOW end-of-speech sensitivity (set in build_realtime_llm). Tune via
    # GEMINI_REALTIME_SILENCE_MS — lower = snappier, higher = more patient.
    gemini_realtime_silence_ms: int = 1500
    # OpenAI Realtime (openai_realtime mode). Its own key + endpoint, kept
    # SEPARATE from the text-path OPENAI_API_KEY/OPENAI_BASE_URL (which point at
    # the cliproxy). Realtime must hit api.openai.com directly.
    openai_realtime_api_key: str | None = None
    openai_realtime_base_url: str = "https://api.openai.com/v1"
    openai_realtime_model: str = "gpt-realtime"
    openai_realtime_voice: str = "marin"
    # Push-to-talk: disable automatic turn detection in the realtime session and
    # let the CANDIDATE control turns from the browser (unmute → talk → mute
    # commits the turn and the interviewer replies). Avoids flaky/laggy auto
    # end-of-turn detection. Override via PUSH_TO_TALK. One-flip revert to the
    # auto path if the manual signalling misbehaves.
    push_to_talk: bool = False

    # --- model overrides (swap models without code changes via env) ----------
    # Two tiers, per the prep/live/post split:
    #   gemini_model      = analytic/background (prep, scoring) — newest Gemini 3
    #                       Flash (has "thinking"); verified for structured output.
    #   gemini_model_live = the real-time interviewer — lowest-latency flash-lite.
    # Ids verified against the models API 2026-07-25 (project golden rule #6).
    gemini_model: str = "gemini-3.6-flash"
    # Newest flash-lite. Gemini 3.x on the live path needs livekit-plugins-google
    # >=1.6, which threads the "thought_signature" through function-call turns
    # (1.5.x dropped it -> 400 INVALID_ARGUMENT after the first save_answer).
    # Pin an exact id here, never a "-latest" alias: the live loop's function
    # calling must not change models under us. Override: GEMINI_MODEL_LIVE.
    gemini_model_live: str = "gemini-3.5-flash-lite"
    # Gemini native TTS — the fallback voice for languages Cartesia doesn't cover
    # (e.g. Vietnamese). gemini-2.5-flash-preview-tts speaks 24 languages incl.
    # vi-VN. Override via GEMINI_TTS_MODEL when a newer TTS model ships.
    gemini_tts_model: str = "gemini-2.5-flash-preview-tts"
    # 2026-current OpenAI default. UNVERIFIED — no OpenAI key in this env; re-verify
    # the exact id + structured-output support before wiring billing (project
    # golden rule #6). Env-overridable via OPENAI_MODEL.
    openai_model: str = "gpt-5.1-mini"
    # ElevenLabs TTS model — the low-latency multilingual voice for languages
    # Cartesia can't speak (e.g. Vietnamese). eleven_flash_v2_5 is ~75ms-latency
    # and covers 32 languages incl. vi. Override via ELEVENLABS_MODEL.
    elevenlabs_model: str = "eleven_flash_v2_5"

    # --- provider credentials (all optional) ---------------------------------
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    # OpenAI-compatible base URL. Set for a proxy / gateway / self-hosted or
    # third-party OpenAI-compatible endpoint (e.g. an LLM router that fronts
    # Claude/Gemini/Grok behind the OpenAI chat-completions API). Leave unset to
    # hit api.openai.com. Env-overridable via OPENAI_BASE_URL.
    openai_base_url: str | None = None
    soniox_api_key: str | None = None
    deepgram_api_key: str | None = None
    cartesia_api_key: str | None = None
    elevenlabs_api_key: str | None = None
    tavily_api_key: str | None = None
    exa_api_key: str | None = None

    # --- supabase ------------------------------------------------------------
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None

    # --- livekit -------------------------------------------------------------
    livekit_url: str | None = None
    livekit_api_key: str | None = None
    livekit_api_secret: str | None = None

    # --- knowledge (LightRAG sidecar) ----------------------------------------
    # When set, the knowledge adapter + /api/kb/ingest forward to this base URL;
    # unset (the default) keeps everything fully offline. Env-overridable via
    # LIGHTRAG_URL (pydantic-settings reads it by field name).
    lightrag_url: str | None = None
    # Optional shared secret sent as ``X-Internal-Secret`` when calling the
    # sidecar. When the sidecar has LIGHTRAG_API_SECRET set it rejects mismatches;
    # unset here (and there) keeps the offline/local path open. Set both to the
    # same value in a hosted deployment.
    lightrag_api_secret: str | None = None

    # --- internal API auth (opt-in) ------------------------------------------
    # The agent API is trust-the-network by design (reads are capability-guarded
    # by unguessable session ids). When INTERNAL_API_SECRET is set, the *write*
    # endpoints (prep/score/coach/kb-ingest and the worker's live-result
    # write-back) require it in the ``X-Internal-Secret`` header; unset (the
    # default) leaves them open so zero-config local runs and tests are
    # unaffected. The web app and the voice worker send it when configured.
    internal_api_secret: str | None = None

    # --- service -------------------------------------------------------------
    agent_api_port: int = 8000
    # Base URL the WORKER uses to reach the prep/score API. Defaults to
    # localhost:{agent_api_port} (same-host dev); docker compose overrides it to
    # the service DNS name (AGENT_API_URL=http://agent-api:8000) because the
    # worker runs in a separate container where localhost is itself.
    agent_api_url: str | None = None
    default_language: str = "en"

    # --- LLM call resilience --------------------------------------------------
    # Per-call ceiling on prep/post LLM requests. Without it a stalled provider
    # call hangs the prep graph forever and the session sticks in "prep" (the
    # node-level try/except only fires once the call RETURNS). The post pipeline
    # additionally has per-stage timeouts.
    llm_call_timeout_sec: float = 90.0

    # --- live: adaptive interview (off the turn-critical path) ----------------
    # When on, the background Director caches an advisory difficulty
    # recommendation and the interviewer exposes a get_difficulty_hint tool. The
    # turn path never blocks on it. Default OFF so the lean live loop and the
    # offline suite are unchanged. Override via ENABLE_ADAPTIVE_DIFFICULTY.
    enable_adaptive_difficulty: bool = False

    # --- post: adversarial score verifier (off the turn-critical path) --------
    # When on, the post scoring pipeline runs a second, adversarial LLM pass over
    # low/borderline competency scores to catch over- or under-scoring; any
    # failure leaves the original scores untouched. Default OFF so the offline
    # suite and existing scorecards are unchanged. Override via
    # ENABLE_SCORE_VERIFIER / SCORE_VERIFIER_TIMEOUT_SEC.
    enable_score_verifier: bool = False
    score_verifier_timeout_sec: float = 60.0

    # --- live: BVC noise cancellation (opt-in) --------------------------------
    # OFF by default: the BVC native filter failed to initialize inside the
    # slim arm64 container ("failed to initialize the audio filter") and took
    # the whole input audio stream down with it — the agent heard nothing.
    # Enable with ENABLE_BVC=true only on hosts where it's verified to load.
    # Noise robustness without it: semantic turn detector + min_words gate.
    enable_bvc: bool = False

    # --- live cost / duration guard (Golden Rule #5: cap voice in code) -------
    # Hard ceilings enforced by the worker's SessionGuard so a live room can
    # never run unbounded (a stalled/looping LLM would otherwise burn voice
    # minutes forever). These are the in-code per-tier caps; a per-session
    # override can later be threaded in via RoomMetadata.
    max_interview_duration_sec: int = 1200  # 20 min wall-clock hard stop
    max_interview_turns: int = 80  # transcript turns hard stop

    # --- live: durability -----------------------------------------------------
    # All persistence normally happens in the worker's shutdown callback. Two
    # settings harden that against a hard crash (OOM/SIGKILL) that skips it:
    #   shutdown_process_timeout_sec — how long the SDK lets the shutdown
    #     callback run before killing the job process. The SDK default (10s) can
    #     kill it mid-write (the live-result POST alone allows 20s); give it real
    #     headroom.
    #   transcript_flush_interval_sec — off-turn-path checkpoint cadence. Every
    #     interval, if the transcript grew, the worker POSTs a partial result to
    #     the live-result endpoint, so a crash loses at most one interval of
    #     conversation instead of the whole interview. 0 disables it.
    shutdown_process_timeout_sec: float = 60.0
    transcript_flush_interval_sec: float = 20.0

    # --- post / scoring resilience -------------------------------------------
    # Per-stage timeout for the (latency-tolerant) scoring pipeline; on timeout
    # or error the stage degrades to a valid fallback instead of failing the
    # whole scorecard. See post/__init__.py.
    score_stage_timeout_sec: float = 60.0
    # Closed-loop skill distiller (WP-10): when enabled, a scored interview
    # proposes a playbook delta into the review queue. OFF by default so tests
    # and local runs don't write drafts; enable in production via env.
    enable_skill_distiller: bool = False


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance loaded from env / ``.env``."""
    return Settings()
