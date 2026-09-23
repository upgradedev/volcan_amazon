# Volcan: Infrastructure as Code & Cost Profile

---

## 1. Cloud Architecture

Volcan runs on AWS Lambda behind an API Gateway HTTP API. The Terraform in this directory
declares the same Lambda plus a Function URL as a reproducible alternate ingress. The active
API Gateway endpoint was updated and probed on 2026-09-23; its health response carries the
deployed Git revision.

- **Compute:** AWS Lambda (`python3.11`, 256MB) executing the FastMCP ASGI application.
- **Networking:** Active ingress is API Gateway HTTP API. Terraform declares an HTTPS Lambda Function URL without an always-on load balancer.
- **Intelligence:** Amazon Bedrock is attempted when the configured model is available; each response reports `bedrock` or a labelled local fallback reason.
- **Audit Logging:** Amazon CloudWatch Log Group with 14-day retention.

---

## 2. Monthly Idle Cost Profile

| Resource | AWS Service | Monthly Idle Cost | Measured Date |
|---|---|---|---|
| FastMCP Serverless Compute | AWS Lambda (0 invocations = $0.00) | **$0.00** | 2026-09-02 |
| Public HTTPS Ingress | AWS Lambda Function URL (Included Free) | **$0.00** | 2026-09-02 |
| AST Semantic Synthesis | Amazon Bedrock (Pay-per-token, $0.00 idle) | **$0.00** | 2026-09-02 |
| Audit Trail Logs | Amazon CloudWatch (<5GB Free Tier) | **$0.00** | 2026-09-02 |
| Identity & Access | AWS IAM | **$0.00** | 2026-09-02 |
| **TOTAL MONTHLY IDLE COST** | | **$0.00 ESTIMATE** | **2026-09-02** |

---

## 3. Deploy & Teardown Instructions

```bash
# Initialize Terraform
cd infra
terraform init

# Validate configuration
terraform validate

# Plan and Apply
terraform plan -var="source_revision=$(git rev-parse HEAD)" -out=tfplan
terraform apply tfplan

# Teardown / Destroy all resources
terraform destroy -auto-approve
```
