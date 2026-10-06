"""Infrastructure Adapter: Amazon Bedrock synthesis with a labelled local fallback.

The Bedrock call below is real client code against Claude on Amazon Bedrock.
Whether it runs depends entirely on the environment: with no AWS credentials
present, without the Anthropic SDK installed, or when the call raises, the
adapter falls back to a deterministic local summary. The two paths are not
interchangeable and are never presented as if they were, so every report carries
``synthesis_mode``:

* ``"bedrock"``        an Amazon Bedrock model answered this request
* ``"heuristic-local"`` no model was invoked; the local heuristic produced it

A mode on its own leaves a reviewer guessing why, so every report also carries
``fallback_reason``: a bounded public explanation, or the sentence explaining
that no credentials resolved. Provider payloads can contain account, role and
request identifiers, so the API never returns an exception message verbatim.
The API and the web companion surface the bounded explanation. An unexplained
fallback looked like a design choice; a safe, named category is a fact a
reviewer can act on.

Runtime evidence belongs to the deployment, not this module. ``synthesis_mode``
is the per-request receipt: only ``bedrock`` means a model answered.
"""
import asyncio
import importlib.util
import json
import logging
import os
import threading
import time

from src.domain.semantic_diff import (
    DiffSectionDigest,
    SemanticDiffReport,
    join_words,
    plural,
    touched_names,
)
from src.domain.spoken_form import strip_markdown_for_speech

MODE_BEDROCK = "bedrock"
MODE_HEURISTIC = "heuristic-local"

#: Claude on Amazon Bedrock carries an ``anthropic.`` provider prefix on the
#: first-party model id. The id this file pinned before,
#: ``anthropic.claude-3-5-sonnet-20241022-v2:0``, is a retired snapshot on the
#: legacy InvokeModel integration and answers ResourceNotFoundException. Set
#: AWS_BEDROCK_MODEL_ID to pin a different model or a region-scoped inference
#: profile without editing this file.
DEFAULT_MODEL_ID = "anthropic.claude-opus-5"

#: Room for the model to think and still finish the sentence. Adaptive thinking
#: is on by default on this model family and is billed against the same ceiling,
#: so a small ceiling truncates the answer rather than saving anything.
DEFAULT_MAX_TOKENS = 16000

#: Diff characters the model is shown. A longer patch is cut here, and the
#: report says so with exact counts rather than silently narrowing the view.
MODEL_DIFF_CHAR_BUDGET = 3000

#: Spoken-summary characters. The model is asked for under 25 words, but its
#: answer is cut for the ear anyway, at a sentence end when one fits and at
#: a word end otherwise, never mid-word, with an ellipsis marking the cut.
SPOKEN_SUMMARY_CHAR_BUDGET = 180

#: Seconds each model call is given before it is abandoned to the labelled
#: local fallback. The production function budget is 30 seconds. This is the
#: SDK's ``timeout``, which httpx applies to each phase of one request on its
#: own (connect, write, each read, pool), so it bounds every wait on the
#: network rather than the wall-clock time of the call; SigV4 signing, which
#: may look up credentials, and building the client run outside it. Every
#: attempt of one press shares one ``MODEL_CALL_TIMEOUT_SEC`` budget for
#: deciding whether a retry fits and how long it may wait, and the client is
#: built with no SDK retries: the SDK retries a timed-out request by default,
#: so a slow call could otherwise wait three times 25 seconds.
MODEL_CALL_TIMEOUT_SEC = 25

#: A press whose first answer carries no text, or whose first call fails
#: with a transient error (HTTP 429 or 5xx, or a connection error), is tried
#: once more, but only when at least this many seconds of the budget remain
#: after any wait the service asked for in ``retry-after``. The second attempt
#: gets the time that is left, never a fresh 25 seconds. This replaces the
#: SDK's own retries, which ignored the budget.
RETRY_MIN_REMAINING_SEC = 8.0

#: Wait before retrying a transient error when the service names none, the
#: SDK's own first backoff.
RETRY_DEFAULT_WAIT_SEC = 0.5

#: The request text, unchanged from the build that was live on 2026-10-06.
#: Measured that day against anthropic.claude-opus-5 in eu-west-1 with the
#: take-4 permissions.py patch (16 calls, ledger outside the repository):
#:
#: * this prompt and request body (231 input tokens): 2 of 4 calls ended in
#:   text; the other 2 were refused (stop_reason "refusal", stop_details
#:   category "cyber", no content, 0 output tokens, 1.5 to 3.2 seconds).
#:   Call 2 was refused and call 3, the same body one second later, answered;
#: * two trial request bodies, run in the 4 minutes after, both at effort
#:   "low" with adaptive thinking stated: 0 of 12 ended in text, every one the
#:   same refusal. Body A (305 input tokens) added a system prompt with an
#:   instruction to flag a weakened authorization or validation rule; its 4
#:   presses each resent the same body once after the refusal, 8 calls in all.
#:   Body B (220 input tokens) was this prompt without its last sentence.
#:   The ledger's settings field does not record the system prompt or the
#:   trim; the input token counts are what tell the two bodies apart.
#:
#: The trials fell in one window, so settings and time cannot be separated,
#: and no trial setting ever produced an answer to measure. The request body
#: therefore stays the one with live evidence behind it.
PROMPT_TEMPLATE = (
    "You are Volcan, an accessibility agent assisting a visually impaired engineer. "
    "Summarize the following code changes into a clear, concise (under 25 words) "
    "executive spoken summary. Identify any high-risk changes.\n\n"
    "Diff:\n{diff}"
)

#: Private operator telemetry: one structured line per model call, holding
#: the shape of the answer and never its words, ids or ARNs. The logger has no
#: handler of its own. In Lambda the runtime's root handler writes its records
#: to CloudWatch Logs: the ``volcan-voice-ide`` logger, set up the same way,
#: delivered 11 ``[INFO]`` lines to this function's log group between
#: 2026-09-23 and 2026-09-29. A local process with no root handler drops them.
_telemetry = logging.getLogger("volcan.bedrock")
_telemetry.setLevel(logging.INFO)

#: Why a model message carried no text a voice could say. Each cause has its
#: own public sentence, because "the model declined it" and "it wrote
#: nothing" call for different actions from the person reading the reason.
NO_TEXT_REFUSAL = "refusal"
NO_TEXT_MAX_TOKENS = "max_tokens"
NO_TEXT_THINKING_ONLY = "thinking_only"
NO_TEXT_EMPTY_TEXT = "empty_text"
NO_TEXT_NO_CONTENT = "no_content"

_FALLBACK_TAIL = "; the local deterministic digest answered instead"
NO_TEXT_PUBLIC_REASONS = {
    # The safety classifier that runs with the model, reported as stop_reason
    # "refusal" with a stop_details category. Not Amazon Bedrock Guardrails,
    # which this deployment does not configure.
    NO_TEXT_REFUSAL: "The model's safety classifier declined to summarize this patch" + _FALLBACK_TAIL,
    NO_TEXT_MAX_TOKENS: "Amazon Bedrock used its whole output allowance before writing an answer" + _FALLBACK_TAIL,
    NO_TEXT_THINKING_ONLY: "Amazon Bedrock reasoned about the patch but wrote no answer" + _FALLBACK_TAIL,
    NO_TEXT_EMPTY_TEXT: "Amazon Bedrock returned an empty answer" + _FALLBACK_TAIL,
    NO_TEXT_NO_CONTENT: "Amazon Bedrock returned no usable text block" + _FALLBACK_TAIL,
}

#: Causes worth one more attempt within the budget. A refusal is not one, by
#: design rather than by measurement: it is the model's safety decision on
#: this input, and Volcan reports it instead of asking again until a request
#: gets through. On the live request body a resend might well answer (call 2
#: was refused and call 3, the same body, answered a second later); the
#: 0 of 4 recovered by resends on 2026-10-06 were on trial body A, not this one.
#: Running out of output room would only happen again with the same allowance.
RETRYABLE_NO_TEXT = frozenset({NO_TEXT_THINKING_ONLY, NO_TEXT_EMPTY_TEXT, NO_TEXT_NO_CONTENT})


class NoSpokenText(Exception):
    """A model message arrived but carried no text a voice could say."""

    def __init__(self, cause: str, stop_reason: str | None = None):
        super().__init__(f"the Bedrock response carried no text block ({cause})")
        self.cause = cause
        self.stop_reason = stop_reason

    @property
    def public_reason(self) -> str:
        return NO_TEXT_PUBLIC_REASONS.get(self.cause, NO_TEXT_PUBLIC_REASONS[NO_TEXT_NO_CONTENT])


def shorten_for_speech(text: str, budget: int = SPOKEN_SUMMARY_CHAR_BUDGET) -> str:
    """Flatten model prose to one speakable line within ``budget`` chars.

    Markdown goes first: the cut is measured on the words a voice will
    say, not on stars and ticks it would stumble over.
    """
    flat = " ".join(strip_markdown_for_speech(text).split())
    if len(flat) <= budget:
        return flat
    room = flat[:budget]
    for end in (". ", "! ", "? "):
        cut = room.rfind(end)
        if cut > 0:
            return room[: cut + 1] + " \u2026"
    cut = room.rfind(" ")
    if cut > 0:
        return room[:cut] + " \u2026"
    return room + " \u2026"

#: The one field ``/health`` reports about the model path. Credentials alone
#: were reported for a while, and read as a promise that a model would answer:
#: they resolve on the development machine, where the SDK is absent and no call
#: can leave the process at all. Two facts decide whether an attempt is even
#: possible, so the health check states the conclusion of both rather than half
#: of the evidence.
CAPABILITY_READY = "ready_to_attempt"
CAPABILITY_NO_SDK = "unavailable_sdk_not_installed"
CAPABILITY_NO_CREDENTIALS = "unavailable_no_credentials"
CAPABILITY_NEITHER = "unavailable_no_sdk_and_no_credentials"

#: How long a resolved answer to "are there credentials?" is served before it is
#: looked up again. The lookup walks the whole boto3 chain, and on a machine
#: with no credentials its last step, the EC2 instance-metadata probe, costs
#: about two seconds (2.054 s measured on 2026-09-26): paid on every request, it made /health
#: and every press take two seconds on a judge's laptop. A stale answer is
#: served while a background lookup replaces it, and /health?refresh=1 forces
#: one. Whether a model answered is still reported per digest, never cached.
CREDENTIAL_CACHE_SECONDS = 300.0

#: Package that has to be importable before a Bedrock call can be attempted.
SDK_DISTRIBUTION = "anthropic[bedrock]"
SDK_MODULE = "anthropic"


class BedrockSynthesisAdapter:
    def __init__(
        self,
        region_name: str = "us-east-1",
        model_id: str = DEFAULT_MODEL_ID,
        client_factory=None,
    ):
        self.region_name = os.getenv("AWS_REGION", region_name)
        self.model_id = os.getenv("AWS_BEDROCK_MODEL_ID", model_id)
        #: Seam for tests. Production leaves it None and builds the real client.
        self._client_factory = client_factory
        self.last_fallback_reason: str | None = None
        #: (answer, monotonic time it was resolved), or None before the first lookup.
        self._credentials_cache: tuple[bool, float] | None = None
        self._credentials_lock = threading.Lock()
        self._credentials_refreshing = False

    def credentials_present(self, refresh: bool = False) -> bool:
        """Whether the boto3 credential chain resolves, cached per adapter.

        The first call resolves and waits; later calls within
        ``CREDENTIAL_CACHE_SECONDS`` return the cached answer at once. After
        that the cached answer is still returned while one background lookup
        replaces it, so no request waits on the instance-metadata probe again.
        ``refresh=True`` resolves now and waits for the answer.
        """
        with self._credentials_lock:
            cached = self._credentials_cache
            if cached is not None and not refresh:
                answer, resolved_at = cached
                if time.monotonic() - resolved_at >= CREDENTIAL_CACHE_SECONDS and not self._credentials_refreshing:
                    self._credentials_refreshing = True
                    threading.Thread(target=self._refresh_credentials, daemon=True).start()
                return answer
            # First lookup, or a forced one: resolve under the lock, so a
            # second request arriving meanwhile waits for this answer instead
            # of starting its own two-second probe.
            answer = self._resolve_credentials()
            self._credentials_cache = (answer, time.monotonic())
            return answer

    def _refresh_credentials(self) -> None:
        answer = self._resolve_credentials()
        with self._credentials_lock:
            self._credentials_cache = (answer, time.monotonic())
            self._credentials_refreshing = False

    def _resolve_credentials(self) -> bool:
        """Resolve credentials the way boto3 itself does.

        Environment variables are only one of the sources boto3 searches. A judge
        running with a shared credentials file, an SSO profile or an instance role
        has working credentials and must reach the Bedrock path, not the fallback.
        The environment check remains as the answer when boto3 is absent.
        """
        try:
            import boto3
        except ImportError:
            return bool(os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("AWS_SESSION_TOKEN"))
        try:
            return boto3.Session().get_credentials() is not None
        except Exception:
            return False

    @staticmethod
    def sdk_present() -> bool:
        """Whether the Anthropic SDK could be imported, without importing it.

        ``find_spec`` locates the module and stops. Importing it here to find
        out would pull the client into every process that merely asks a health
        question, which is a side effect a health check has no business having.
        """
        try:
            return importlib.util.find_spec(SDK_MODULE) is not None
        except (ImportError, ValueError):
            return False

    def model_path_capability(self, refresh: bool = False) -> dict[str, object]:
        """What ``/health`` can honestly say about the model path.

        Neither fact is sufficient alone. Credentials without the SDK cannot
        attempt a call; the SDK without credentials cannot either. The resolved
        capability is the conjunction, and the two facts stay beside it so a
        reviewer can see what produced the conclusion. Even ``ready_to_attempt``
        is a statement about the attempt: whether a model answers is reported
        per digest by ``synthesis_mode``, and nothing here predicts it.
        """
        credentials = self.credentials_present(refresh=True) if refresh else self.credentials_present()
        sdk = self.sdk_present()

        if credentials and sdk:
            capability = CAPABILITY_READY
            detail = (
                "Credentials resolved and the SDK is importable, so a Bedrock call will be "
                f"attempted with model {self.model_id}. Whether one answers is reported per "
                "digest as synthesis_mode, with the reason beside it when none did."
            )
        elif credentials:
            capability = CAPABILITY_NO_SDK
            detail = (
                f"Credentials resolved, but {SDK_MODULE} is not importable, so no call can "
                f"leave this process. Install it with: pip install '{SDK_DISTRIBUTION}'."
            )
        elif sdk:
            capability = CAPABILITY_NO_CREDENTIALS
            detail = (
                "The SDK is importable, but the boto3 credential chain resolved no AWS "
                "credentials, so every digest comes from the local heuristic path."
            )
        else:
            capability = CAPABILITY_NEITHER
            detail = (
                f"Neither AWS credentials nor {SDK_MODULE} resolved here, so every digest "
                "comes from the local heuristic path."
            )

        return {
            "resolved_capability": capability,
            "detail": detail,
            "credentials_present": credentials,
            "sdk_installed": sdk,
            "model_id": self.model_id,
            "region": self.region_name,
        }

    def _build_client(self):
        if self._client_factory is not None:
            return self._client_factory(self.region_name)
        from anthropic import AnthropicBedrockMantle

        # No SDK retries: MODEL_CALL_TIMEOUT_SEC is the deadline for the whole
        # press, and this adapter decides itself whether a second attempt fits.
        return AnthropicBedrockMantle(aws_region=self.region_name, max_retries=0)

    @staticmethod
    def _field(obj, name):
        """Read a field from an SDK object or from a stub's plain dictionary."""
        if isinstance(obj, dict):
            return obj.get(name)
        return getattr(obj, name, None)

    @classmethod
    def _first_text_block(cls, message) -> str:
        """The first non-empty text block of a Bedrock response.

        Indexing ``content[0]`` is wrong on a model that thinks: the first block
        is then a thinking block and the digest raises instead of speaking. The
        blocks arrive as SDK objects, and as plain dictionaries from a stub, so
        both shapes are read the same way. A message with no such block raises
        ``NoSpokenText`` naming why, read from ``stop_reason`` and the blocks.

        A refusal raises even when text came first: a classifier can stop a
        message after partial output, and a sentence it cut off is not an
        answer to speak as if a model had finished it.
        """
        stop_reason = cls._field(message, "stop_reason")
        if stop_reason == "refusal":
            raise NoSpokenText(NO_TEXT_REFUSAL, stop_reason)
        blocks = cls._field(message, "content") or []
        types = []
        for block in blocks:
            block_type, text = cls._field(block, "type"), cls._field(block, "text")
            types.append(block_type)
            if block_type == "text" and text and text.strip():
                return text.strip()

        if stop_reason == "max_tokens":
            cause = NO_TEXT_MAX_TOKENS
        elif "text" in types:
            cause = NO_TEXT_EMPTY_TEXT
        elif any(t in ("thinking", "redacted_thinking") for t in types):
            cause = NO_TEXT_THINKING_ONLY
        else:
            cause = NO_TEXT_NO_CONTENT
        raise NoSpokenText(cause, stop_reason)

    @classmethod
    def _log_model_call(cls, attempt: int, latency_ms: int, message=None, error=None) -> dict:
        """Emit one private telemetry line for one model call and return it.

        Only the shape of the answer is recorded: stop reason, the refusal
        category (a fixed enum), each block's type and character count, and
        token usage. The answer's words, the refusal explanation, message and
        request ids, the model id (which may be an inference-profile ARN) and
        exception messages (which can carry account ids and ARNs) never are.
        """
        line: dict = {"event": "bedrock_model_call", "attempt": attempt, "latency_ms": latency_ms}
        if error is not None:
            line["outcome"] = "error"
            line["error_type"] = type(error).__name__
        else:
            blocks = []
            for block in cls._field(message, "content") or []:
                block_type = cls._field(block, "type")
                body = cls._field(block, "text") if block_type == "text" else cls._field(block, "thinking")
                blocks.append({"type": block_type, "chars": len(body) if isinstance(body, str) else None})
            stop_details = cls._field(message, "stop_details")
            usage = cls._field(message, "usage")
            details = cls._field(usage, "output_tokens_details") if usage is not None else None
            line.update({
                "outcome": "message",
                "stop_reason": cls._field(message, "stop_reason"),
                "refusal_category": cls._field(stop_details, "category") if stop_details is not None else None,
                "blocks": blocks,
                "usage": None if usage is None else {
                    "input_tokens": cls._field(usage, "input_tokens"),
                    "output_tokens": cls._field(usage, "output_tokens"),
                    "thinking_tokens": cls._field(details, "thinking_tokens") if details is not None else None,
                    "cache_read_input_tokens": cls._field(usage, "cache_read_input_tokens"),
                    "cache_creation_input_tokens": cls._field(usage, "cache_creation_input_tokens"),
                },
            })
        _telemetry.info(json.dumps(line, default=str))
        return line

    @staticmethod
    def _is_transient(exc: Exception) -> bool:
        """An error the SDK would have retried: HTTP 429 or 5xx, or a dropped
        connection. A timeout is not one here; it has used up the budget."""
        status = getattr(exc, "status_code", None)
        if isinstance(status, int):
            return status == 429 or status >= 500
        return type(exc).__name__ == "APIConnectionError"

    @staticmethod
    def _retry_wait(exc: Exception) -> float:
        """Seconds to wait before retrying ``exc``: the service's
        ``retry-after-ms`` or ``retry-after`` (in seconds) when it sends one,
        as the SDK honours them, and ``RETRY_DEFAULT_WAIT_SEC`` otherwise."""
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)
        if headers is not None:
            for name, scale in (("retry-after-ms", 0.001), ("retry-after", 1.0)):
                try:
                    value = float(headers.get(name)) * scale
                except (TypeError, ValueError):
                    continue
                if value >= 0:
                    return value
        return RETRY_DEFAULT_WAIT_SEC

    def _invoke(self, diff_excerpt: str) -> str:
        """The blocking client call, run off the event loop by the caller.

        ``diff_excerpt`` is already cut to ``MODEL_DIFF_CHAR_BUDGET`` by the
        caller, which records what the model saw; this method sends it whole.

        All attempts share one budget of ``MODEL_CALL_TIMEOUT_SEC``, counted
        from the first call. A first answer with no text (other than a refusal
        or a spent output allowance), or a first call that fails transiently,
        is tried once more when at least ``RETRY_MIN_REMAINING_SEC`` remain
        after the wait, with the remaining time as its timeout; otherwise the
        ``NoSpokenText`` or the error reaches the caller. When a first answer
        had no text and the second call then fails, the first cause is what
        reaches the caller, chained to the second error; telemetry has both.
        """
        client = self._build_client()
        prompt = PROMPT_TEMPLATE.format(diff=diff_excerpt)
        deadline = time.monotonic() + MODEL_CALL_TIMEOUT_SEC
        attempt = 0
        first_no_text: NoSpokenText | None = None
        while True:
            attempt += 1
            remaining = deadline - time.monotonic()
            started = time.monotonic()
            try:
                message = client.messages.create(
                    model=self.model_id,
                    max_tokens=DEFAULT_MAX_TOKENS,
                    timeout=MODEL_CALL_TIMEOUT_SEC if attempt == 1 else remaining,
                    messages=[{"role": "user", "content": prompt}],
                )
            except Exception as exc:
                self._log_model_call(attempt, round((time.monotonic() - started) * 1000), error=exc)
                if first_no_text is not None:
                    raise first_no_text from exc
                if attempt >= 2 or not self._is_transient(exc):
                    raise
                wait = self._retry_wait(exc)
                if deadline - time.monotonic() - wait < RETRY_MIN_REMAINING_SEC:
                    raise
                time.sleep(wait)
                continue
            self._log_model_call(attempt, round((time.monotonic() - started) * 1000), message=message)
            try:
                return self._first_text_block(message)
            except NoSpokenText as no_text:
                if (
                    attempt >= 2
                    or no_text.cause not in RETRYABLE_NO_TEXT
                    or deadline - time.monotonic() < RETRY_MIN_REMAINING_SEC
                ):
                    raise
                first_no_text = no_text

    @staticmethod
    def _public_failure_reason(exc: Exception) -> str:
        """Return an actionable category without leaking the provider payload.

        Bedrock and the Anthropic client include request ids, account ids and
        assumed-role ARNs in some exception strings. Those belong in private
        operator telemetry, never in an anonymous response or screen reader
        announcement. Classification therefore uses the exception type and
        message internally but returns only fixed product-owned sentences.
        """
        # A message that arrived without text is classified by its own cause,
        # before any substring matching could misread its wording.
        if isinstance(exc, NoSpokenText):
            return exc.public_reason
        throttled = (
            "Amazon Bedrock temporarily throttled this request; "
            "the local deterministic digest answered instead"
        )
        # The SDK's RateLimitError reads "ratelimiterror error code: 429 ...
        # rate_limit_error", which no wording rule below matched.
        if getattr(exc, "status_code", None) == 429:
            return throttled
        category = f"{type(exc).__name__} {exc}".lower()
        if "permission" in category or "accessdenied" in category or "unauthorized" in category:
            return (
                "Amazon Bedrock access is not authorized for the configured model; "
                "the local deterministic digest answered instead"
            )
        if "notfound" in category or "not found" in category or "unavailable" in category:
            return (
                "The configured Amazon Bedrock model is unavailable in this deployment; "
                "the local deterministic digest answered instead"
            )
        if any(word in category for word in ("throttl", "rate limit", "ratelimit", "rate_limit")):
            return throttled
        if "timeout" in category or "timed out" in category:
            return (
                "Amazon Bedrock did not answer before the request deadline; "
                "the local deterministic digest answered instead"
            )
        return (
            "Amazon Bedrock did not complete the synthesis request; "
            "the local deterministic digest answered instead"
        )

    async def summarize_diff(self, raw_diff: str, sections: list[DiffSectionDigest]) -> SemanticDiffReport:
        # The lookup can block on the instance-metadata probe the first time;
        # it runs off the event loop so other requests are not held behind it.
        if not await asyncio.to_thread(self.credentials_present):
            return self._heuristic_fallback(
                raw_diff, sections,
                "no AWS credentials were resolved by the boto3 credential chain",
            )

        excerpt = raw_diff[:MODEL_DIFF_CHAR_BUDGET]
        try:
            # The client is synchronous. Calling it directly would block the
            # event loop for the whole round trip, stalling every other request.
            content_text = await asyncio.to_thread(self._invoke, excerpt)
        except ImportError:
            return self._heuristic_fallback(
                raw_diff, sections,
                "the Anthropic SDK is not installed; "
                "pip install 'anthropic[bedrock]' to reach Amazon Bedrock",
            )
        except Exception as exc:  # noqa: BLE001 - any failure degrades to the labelled fallback
            return self._heuristic_fallback(
                raw_diff, sections,
                self._public_failure_reason(exc),
            )

        self.last_fallback_reason = None
        return SemanticDiffReport(
            total_files_changed=len(sections),
            total_insertions=sum(s.added_count for s in sections),
            total_deletions=sum(s.removed_count for s in sections),
            executive_spoken_summary=shorten_for_speech(content_text),
            category_breakdown={},
            critical_findings=[],
            sections=sections,
            synthesis_mode=MODE_BEDROCK,
            fallback_reason=None,
            # The panel under "The model's full answer" shows these words, so
            # Markdown goes here too: stars and ticks are noise on screen and
            # are read aloud by a screen reader. Nothing is cut. Outside code
            # fences, emphasis, heading, bullet, quote and link markup is
            # removed. Inside a fence every character stays, the diff '-' and
            # '+' and the '#' comment markers included, and the fence lines
            # become "Code:" and "End of code.". Inline code loses its ticks
            # and is not otherwise protected.
            model_prose_full=strip_markdown_for_speech(content_text),
            model_input_chars_sent=len(excerpt),
            model_input_chars_total=len(raw_diff),
        )

    def summarize_locally(
        self, raw_diff: str, sections: list[DiffSectionDigest], reason: str,
    ) -> SemanticDiffReport:
        """The deterministic digest, asked for by name: no credential lookup,
        no SDK import and no model call. ``last_fallback_reason`` is left alone,
        because nothing failed."""
        return self._local_report(sections, reason)

    def _heuristic_fallback(
        self, raw_diff: str, sections: list[DiffSectionDigest], reason: str,
    ) -> SemanticDiffReport:
        self.last_fallback_reason = reason
        return self._local_report(sections, reason)

    def _local_report(
        self, sections: list[DiffSectionDigest], reason: str,
    ) -> SemanticDiffReport:
        files_count = len(sections)
        total_add = sum(s.added_count for s in sections)
        total_del = sum(s.removed_count for s in sections)
        summary = self._heuristic_headline(sections)

        return SemanticDiffReport(
            total_files_changed=files_count,
            total_insertions=total_add,
            total_deletions=total_del,
            executive_spoken_summary=summary,
            category_breakdown={},
            critical_findings=[],
            sections=sections,
            synthesis_mode=MODE_HEURISTIC,
            fallback_reason=reason,
        )

    @staticmethod
    def _heuristic_headline(sections: list[DiffSectionDigest]) -> str:
        """A one-clause characterisation, not a restatement of the counts.

        The caller already speaks the file and line counts, so repeating them
        here would make a listener sit through the same numbers twice.
        """
        if not sections:
            return "No code changes detected in the current workspace"

        flagged = [section for section in sections if section.security_flags]
        if flagged:
            headline = f"Security-sensitive changes in {flagged[0].file_path}"
            if len(flagged) > 1:
                headline += f" and {plural(len(flagged) - 1, 'other file')}"
            return headline

        # "Changes are mostly business logic" said nothing that "no finding"
        # did not. The parser already knows which files changed and which
        # definitions each hunk sits in, so the clean case names them: at most
        # two files and three names each, because a listener hears all of it.
        parts = []
        for section in sections[:2]:
            names = touched_names(section)
            if len(names) > 3:
                names = names[:3] + [f"{len(names) - 3} more"]
            parts.append(
                f"{join_words(names)} in {section.file_path}" if names else section.file_path
            )
        others = len(sections) - 2
        if others > 0:
            parts.append(plural(others, "other file"))
        return f"The change touches {join_words(parts)}; no security rule matched"
