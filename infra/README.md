# Volcan: Infrastructure as Code & Cost Profile

---

## 1. Cloud Architecture

Volcan deploys on AWS using serverless containers (Amazon ECS Fargate / AWS Lambda) with least-privilege IAM policies granting access strictly to Amazon Bedrock models (`anthropic.claude-3-5-sonnet-20241022-v2:0` and `amazon.nova-micro-v1:0`).

---

## 2. Monthly Idle Cost Profile

| Resource | Service | Monthly Cost Idle | Measured Date |
|---|---|---|---|
| MCP Streamable HTTP Container | Amazon ECS Fargate (0 tasks when idle) | **$0.00** | 2026-09-01 |
| LLM AST Synthesis | Amazon Bedrock (Pay-per-token, 0 idle) | **$0.00** | 2026-09-01 |
| Audit Trail Logs | Amazon CloudWatch (Free Tier <5GB) | **$0.00** | 2026-09-01 |
| IAM Roles & Policies | AWS IAM | **$0.00** | 2026-09-01 |
| **TOTAL MONTHLY IDLE COST** | | **$0.00** | **2026-09-01** |

---

## 3. Deploy & Teardown Instructions

```bash
# Initialize Terraform
cd infra
terraform init

# Validate configuration
terraform validate

# Plan and Apply
terraform plan -out=tfplan
terraform apply tfplan

# Teardown / Destroy all resources
terraform destroy -auto-approve
```
