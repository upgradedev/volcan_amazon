"""Infrastructure Adapter: Amazon Bedrock Multimodal Synthesis."""
import json
import os

from src.domain.semantic_diff import DiffSectionDigest, SemanticDiffReport


class BedrockSynthesisAdapter:
    def __init__(
        self,
        region_name: str = "us-east-1",
        model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0",
    ):
        self.region_name = os.getenv("AWS_REGION", region_name)
        self.model_id = os.getenv("AWS_BEDROCK_MODEL_ID", model_id)

    async def summarize_diff(self, raw_diff: str, sections: list[DiffSectionDigest]) -> SemanticDiffReport:
        # Check for AWS credentials in environment
        if not os.getenv("AWS_ACCESS_KEY_ID") and not os.getenv("AWS_SESSION_TOKEN"):
            return self._heuristic_fallback(raw_diff, sections)

        try:
            import boto3

            client = boto3.client("bedrock-runtime", region_name=self.region_name)
            prompt = (
                f"You are Volcan, an accessibility agent assisting a visually impaired engineer. "
                f"Summarize the following code changes into a clear, concise (under 25 words) executive spoken summary. "
                f"Identify any high-risk changes.\n\nDiff:\n{raw_diff[:3000]}"
            )
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 512,
                "messages": [{"role": "user", "content": prompt}],
            })
            response = client.invoke_model(modelId=self.model_id, body=body)
            response_body = json.loads(response.get("body").read())
            content_text = response_body["content"][0]["text"].strip()

            return SemanticDiffReport(
                total_files_changed=len(sections),
                total_insertions=sum(s.added_count for s in sections),
                total_deletions=sum(s.removed_count for s in sections),
                executive_spoken_summary=content_text[:180],
                category_breakdown={},
                critical_findings=[],
                sections=sections,
            )
        except Exception:
            return self._heuristic_fallback(raw_diff, sections)

    def _heuristic_fallback(self, raw_diff: str, sections: list[DiffSectionDigest]) -> SemanticDiffReport:
        files_count = len(sections)
        total_add = sum(s.added_count for s in sections)
        total_del = sum(s.removed_count for s in sections)
        summary = f"Refactored code across {files_count} modules with {total_add} insertions and {total_del} deletions."
        
        return SemanticDiffReport(
            total_files_changed=files_count,
            total_insertions=total_add,
            total_deletions=total_del,
            executive_spoken_summary=summary,
            category_breakdown={},
            critical_findings=[],
            sections=sections,
        )
