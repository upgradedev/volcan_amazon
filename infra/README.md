# Volcan: Infrastructure as Code & Cost Profile

---

## 1. Cloud Architecture

Volcan runs on AWS Lambda behind an Amazon API Gateway HTTP API, which is the live ingress.
The Terraform in this directory does not declare that HTTP API (`grep -i apigateway
infra/main.tf` prints nothing): it was created outside Terraform, so a plan neither shows nor
manages it. The Terraform declares the same Lambda plus a Lambda Function URL as a
reproducible alternate ingress. The read-only probe in
[`deploy_teardown_receipt.json`](../deploy_teardown_receipt.json) reached the API Gateway
endpoint on 2026-10-19; its health response carries the deployed Git revision.

- **Compute:** AWS Lambda (`python3.11`, 1769 MB, raised from 256 MB on 2026-10-07) running the
  hand-written MCP server on FastAPI (`src/interfaces/mcp_server.py`), with no MCP SDK.
  One press of the same diff took 17562 ms of Lambda time at 256 MB and 3071 ms at 1769 MB
  (n=1 each, not a benchmark; see [docs/EVIDENCE.md](../docs/EVIDENCE.md#the-public-deployment)).
- **Networking:** Live ingress is the API Gateway HTTP API above. Terraform declares an HTTPS Lambda Function URL as the alternate, without an always-on load balancer.
- **Intelligence:** Amazon Bedrock is attempted when the configured model is available; each response reports `bedrock` or a labelled local fallback reason.
- **Durable application state:** encrypted DynamoDB, pay per request, with conditional session/action/nonce writes, two-hour session TTL and point-in-time recovery.
- **Audit logging:** reviewer/repository-scoped transactional hash chains in DynamoDB plus a CloudWatch Log Group with 14-day retention.

---

## 2. Monthly Idle Cost Profile

| Resource | AWS Service | Monthly Idle Cost | Basis |
|---|---|---|---|
| Hand-written MCP server on FastAPI | AWS Lambda (0 invocations = $0.00) | **$0.00** | AWS list price as of 2026-09-02, not a bill |
| Public HTTPS ingress (live) | Amazon API Gateway HTTP API, created outside Terraform | **$0.00** | AWS API Gateway pricing page, read 2026-10-20: billed per API call, "no minimum fees or upfront commitments". Not a bill |
| Alternate HTTPS ingress (declared in Terraform) | AWS Lambda Function URL (Included Free) | **$0.00** | AWS list price as of 2026-09-02, not a bill |
| AST Semantic Synthesis | Amazon Bedrock (Pay-per-token, $0.00 idle) | **$0.00** | AWS list price as of 2026-09-02, not a bill |
| Audit Trail Logs | Amazon CloudWatch (<5GB Free Tier) | **$0.00** | AWS list price as of 2026-09-02, not a bill |
| Multi-turn state and audit chain | DynamoDB PAY_PER_REQUEST + storage + PITR | **Usage based; no bill measurement yet** | Not measured; noted 2026-09-23 |
| Identity & Access | AWS IAM | **$0.00** | AWS list price as of 2026-09-02, not a bill |
| **TOTAL MONTHLY IDLE COST** | | **Not measured after adding durable storage** | **Not measured; noted 2026-09-23** |

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
Lambda no Bedrock Mantle authority. `enable_bedrock_mantle=true` is a separate deployment decision.
The live role already has a `volcan-bedrock-mantle-euw1-prod` policy attached (read 2026-10-06
with `aws iam list-attached-role-policies`). If that policy is in this Terraform state, a plan
with the default `enable_bedrock_mantle=false` destroys it and every press falls back with the
permission category, so plan with `-var enable_bedrock_mantle=true`, or first confirm with
`terraform state list` that it is not in state.
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
remains a deployment responsibility and is not embedded in this Terraform state.
