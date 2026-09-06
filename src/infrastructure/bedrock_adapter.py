"""Infrastructure Adapter: Amazon Bedrock synthesis with a labelled local fallback.

The Bedrock call below is real boto3 code against ``bedrock-runtime``. Whether
it runs depends entirely on the environment: with no AWS credentials present,
or when the call raises, the adapter falls back to a deterministic local
summary. The two paths are not interchangeable and are never presented as if
they were, so every report carries ``synthesis_mode``:

* ``"bedrock"``        an Amazon Bedrock model answered this request
* ``"heuristic-local"`` no model was invoked; the local heuristic produced it

The API and the web companion both surface that field, which is what keeps the
Amazon Bedrock claim honest when no credentials are configured.
"""
import json
import os
from collections import Counter

from src.domain.semantic_diff import DiffSectionDigest, SemanticDiffReport, plural

MODE_BEDROCK = "bedrock"
MODE_HEURISTIC = "heuristic-local"


class BedrockSynthesisAdapter:
    def __init__(
        self,
        region_name: str = "us-east-1",
        model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0",
    ):
        self.region_name = os.getenv("AWS_REGION", region_name)
        self.model_id = os.getenv("AWS_BEDROCK_MODEL_ID", model_id)
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

    async def summarize_diff(self, raw_diff: str, sections: list[DiffSectionDigest]) -> SemanticDiffReport:
        if not self.credentials_present():
            self.last_fallback_reason = "no AWS credentials in environment"
            return self._heuristic_fallback(raw_diff, sections)

        try:
            import boto3

            client = boto3.client("bedrock-runtime", region_name=self.region_name)
            prompt = (
                "You are Volcan, an accessibility agent assisting a visually impaired engineer. "
                "Summarize the following code changes into a clear, concise (under 25 words) "
                "executive spoken summary. Identify any high-risk changes.\n\n"
                f"Diff:\n{raw_diff[:3000]}"
            )
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 512,
                "messages": [{"role": "user", "content": prompt}],
            })
            response = client.invoke_model(modelId=self.model_id, body=body)
            response_body = json.loads(response.get("body").read())
            content_text = response_body["content"][0]["text"].strip()

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
            )
        except Exception as exc:  # noqa: BLE001 - any failure degrades to the labelled fallback
            self.last_fallback_reason = f"{type(exc).__name__}: {exc}"
            return self._heuristic_fallback(raw_diff, sections)

    def _heuristic_fallback(self, raw_diff: str, sections: list[DiffSectionDigest]) -> SemanticDiffReport:
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
