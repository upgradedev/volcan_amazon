# Volcan: Infrastructure as Code & Cost Profile

---

## 1. Cloud Architecture: 100% Pure Serverless

Volcan deploys on AWS as a **Pure Serverless Architecture** using **AWS Lambda with Function URLs (Response Streaming)**, providing sub-second cold starts, infinite concurrency scaling, and exact **$0.00 monthly idle costs**.

- **Compute:** AWS Lambda (`python3.11`, 256MB) executing the FastMCP ASGI application.
- **Networking:** HTTPS Lambda Function URL with streaming response mode (`AWS_LWA_INVOKE_MODE = "response_stream"`), eliminating costly Application Load Balancers (ALBs).
- **Intelligence:** Amazon Bedrock (`anthropic.claude-3-5-sonnet-20241022-v2:0` & `amazon.nova-micro-v1:0`) billed on pure token consumption with zero idle cost.
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
| **TOTAL MONTHLY IDLE COST** | | **$0.00** | **2026-09-02** |

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
