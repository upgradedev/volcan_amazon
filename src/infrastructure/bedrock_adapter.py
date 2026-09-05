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

from src.domain.semantic_diff import DiffSectionDigest, SemanticDiffReport

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
        return bool(os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("AWS_SESSION_TOKEN"))

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
        summary = (
            f"Refactored code across {files_count} modules with "
            f"{total_add} insertions and {total_del} deletions."
        )

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
