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
- **Durable application state:** encrypted DynamoDB, pay per request, with conditional session/action/nonce writes, two-hour session TTL and point-in-time recovery.
- **Audit logging:** reviewer/repository-scoped transactional hash chains in DynamoDB plus a CloudWatch Log Group with 14-day retention.

---

## 2. Monthly Idle Cost Profile

| Resource | AWS Service | Monthly Idle Cost | Measured Date |
|---|---|---|---|
| FastMCP Serverless Compute | AWS Lambda (0 invocations = $0.00) | **$0.00** | 2026-09-02 |
| Public HTTPS Ingress | AWS Lambda Function URL (Included Free) | **$0.00** | 2026-09-02 |
| AST Semantic Synthesis | Amazon Bedrock (Pay-per-token, $0.00 idle) | **$0.00** | 2026-09-02 |
| Audit Trail Logs | Amazon CloudWatch (<5GB Free Tier) | **$0.00** | 2026-09-02 |
| Multi-turn state and audit chain | DynamoDB PAY_PER_REQUEST + storage + PITR | **Usage based; no bill measurement yet** | 2026-09-23 |
| Identity & Access | AWS IAM | **$0.00** | 2026-09-02 |
| **TOTAL MONTHLY IDLE COST** | | **Not measured after adding durable storage** | **2026-09-23** |

---

## 3. Deploy & Teardown Instructions

```bash
# Initialize Terraform
cd infra
terraform init

# Validate configuration
terraform validate

# Create a 32-byte-or-longer SecretString outside Terraform, then pass only its ARN.
# The secret value must never enter a tfvars file, plan or Terraform state.
export TF_VAR_volcan_approval_secret_arn='arn:aws:secretsmanager:eu-west-1:123456789012:secret:volcan-approval-...'

# Plan and Apply. The plan creates the table and changes Lambda/IAM, so review it.
terraform plan -var="source_revision=$(git rev-parse HEAD)" -out=tfplan
terraform apply tfplan

# Do not call this deployment durable merely because apply succeeded.
# The exact release must report backend=dynamodb and its own source revision.
curl -s "$(terraform output -raw volcan_function_url)/health" | python -m json.tool

# Teardown / Destroy all resources
terraform destroy -auto-approve
```

The default plan reads that exact ARN with `secretsmanager:GetSecretValue` and gives the
Lambda no Bedrock Mantle authority. `enable_bedrock_mantle=true` is a separate owner decision.
At cold start the runtime refuses a missing/unreachable SecretString, a value shorter than 32
bytes, or any direct `VOLCAN_APPROVAL_SECRET` value in durable mode. Local runs without
`VOLCAN_STATE_TABLE` still use process memory and say so in `/health`; they never pretend to be
a multi-worker durability test. Public health reports configured/reachable status without the
table name, secret ARN or account identifier.

The `VOLCAN_REVIEWERS` Bearer roster is optional in durable mode. Without it the anonymous
demo still answers: governed actions from the public surface land in one public demo chain that
`/api/audit_log` shows to anyone with caller-written text withheld, and voice turns run under
the fixed anonymous owner `public:anonymous`. With it, a credential binds a voice session to
that reviewer, and the audit read adds that reviewer's own review chains; the authenticated
identity and its repository allowlist select the session and action namespace, and JSON
`user_id` does not. Live GitHub writes always require it. Supplying that roster securely
remains an owner deployment responsibility and is not embedded in this Terraform state.
