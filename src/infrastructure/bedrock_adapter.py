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
``fallback_reason``: the exception class, the model id and the message, or the
sentence explaining that no credentials resolved. The API and the web companion
surface both fields. An unexplained fallback looked like a design choice; a
named one is a fact a reviewer can act on.

**This path has never answered in this repository.** There are no AWS
credentials here, so the model id and the client below are unexercised code. See
the Known limitations section of the README.
"""
import asyncio
import os
from collections import Counter

from src.domain.semantic_diff import DiffSectionDigest, SemanticDiffReport, plural

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

    def credentials_present(self) -> bool:
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

    def _build_client(self):
        if self._client_factory is not None:
            return self._client_factory(self.region_name)
        from anthropic import AnthropicBedrockMantle

        return AnthropicBedrockMantle(aws_region=self.region_name)

    @staticmethod
    def _first_text_block(message) -> str:
        """The first text block of a Bedrock response.

        Indexing ``content[0]`` is wrong on a model that thinks: the first block
        is then a thinking block and the digest raises instead of speaking. The
        blocks arrive as SDK objects, and as plain dictionaries from a stub, so
        both shapes are read the same way.
        """
        blocks = getattr(message, "content", None)
        if blocks is None and isinstance(message, dict):
            blocks = message.get("content")

        for block in blocks or []:
            if isinstance(block, dict):
                block_type, text = block.get("type"), block.get("text")
            else:
                block_type, text = getattr(block, "type", None), getattr(block, "text", None)
            if block_type == "text" and text and text.strip():
                return text.strip()

        raise ValueError("the Bedrock response carried no text block")

    def _invoke(self, raw_diff: str) -> str:
        """The blocking client call, run off the event loop by the caller."""
        client = self._build_client()
        prompt = (
            "You are Volcan, an accessibility agent assisting a visually impaired engineer. "
            "Summarize the following code changes into a clear, concise (under 25 words) "
            "executive spoken summary. Identify any high-risk changes.\n\n"
            f"Diff:\n{raw_diff[:3000]}"
        )
        message = client.messages.create(
            model=self.model_id,
            max_tokens=DEFAULT_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return self._first_text_block(message)

    async def summarize_diff(self, raw_diff: str, sections: list[DiffSectionDigest]) -> SemanticDiffReport:
        if not self.credentials_present():
            return self._heuristic_fallback(
                raw_diff, sections,
                "no AWS credentials were resolved by the boto3 credential chain",
            )

        try:
            # The client is synchronous. Calling it directly would block the
            # event loop for the whole round trip, stalling every other request.
            content_text = await asyncio.to_thread(self._invoke, raw_diff)
        except ImportError as exc:
            return self._heuristic_fallback(
                raw_diff, sections,
                f"the Anthropic SDK is not installed ({exc}); "
                "pip install 'anthropic[bedrock]' to reach Amazon Bedrock",
            )
        except Exception as exc:  # noqa: BLE001 - any failure degrades to the labelled fallback
            return self._heuristic_fallback(
                raw_diff, sections,
                f"{type(exc).__name__} calling Amazon Bedrock with model "
                f"{self.model_id}: {exc}",
            )

        self.last_fallback_reason = None
        return SemanticDiffReport(
            total_files_changed=len(sections),
            total_insertions=sum(s.added_count for s in sections),
            total_deletions=sum(s.removed_count for s in sections),
            executive_spoken_summary=content_text[:180],
            category_breakdown={},
            critical_findings=[],
            sections=sections,
            synthesis_mode=MODE_BEDROCK,
            fallback_reason=None,
        )

    def _heuristic_fallback(
        self, raw_diff: str, sections: list[DiffSectionDigest], reason: str,
    ) -> SemanticDiffReport:
        self.last_fallback_reason = reason
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

        top_category = Counter(section.category.value for section in sections).most_common(1)[0][0]
        return f"Changes are mostly {top_category.replace('_', ' ').lower()}"
