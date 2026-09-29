# Pure Serverless Terraform Infrastructure for Volcan on AWS Lambda (eu-west-1)
# Architecture: AWS Lambda + Function URL + Amazon Bedrock + CloudWatch

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type        = string
  default     = "eu-west-1"
  description = "Primary AWS region for deployment"
}

variable "environment" {
  type        = string
  default     = "prod"
  description = "Environment tier"
}

variable "lambda_package_path" {
  type        = string
  default     = "../dist/volcan_lambda.zip"
  description = "Path to the built Lambda deployment package"
}

variable "source_revision" {
  type        = string
  description = "Immutable Git commit deployed in the Lambda package"
}

variable "volcan_approval_secret_arn" {
  type        = string
  description = "ARN of an existing Secrets Manager SecretString (32+ bytes); the value is never managed by Terraform"

  validation {
    condition     = can(regex("^arn:[^:]+:secretsmanager:[^:]+:[0-9]{12}:secret:.+$", var.volcan_approval_secret_arn))
    error_message = "volcan_approval_secret_arn must be a Secrets Manager secret ARN."
  }
}

variable "enable_bedrock_mantle" {
  type        = bool
  default     = false
  description = "Separate owner gate for bedrock-mantle:CreateInference; durable-state deploys exclude it by default"
}

resource "aws_dynamodb_table" "volcan_state" {
  name         = "volcan-state-euw1-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Project     = "volcan"
    Environment = var.environment
    Region      = var.aws_region
    ManagedBy   = "terraform"
    Hackathon   = "amazon-developer-2026"
  }
}

# 1. IAM Execution Role for AWS Lambda (Least Privilege)
resource "aws_iam_role" "volcan_lambda_role" {
  name = "volcan-lambda-role-euw1-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# 2. Least-Privilege Policy for durable state, secret read and logging
resource "aws_iam_policy" "volcan_serverless_policy" {
  name        = "volcan-serverless-policy-euw1-${var.environment}"
  description = "Least privilege access to Volcan state, approval secret and CloudWatch logs"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:*:log-group:/aws/lambda/volcan-mcp-euw1-${var.environment}:*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:Query",
          "dynamodb:TransactWriteItems"
        ]
        Resource = aws_dynamodb_table.volcan_state.arn
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = var.volcan_approval_secret_arn
      }
    ]
  })
}

# Bedrock permission remains a separate, explicit owner decision. The default
# durable-state plan neither adds nor changes the live role's model authority.
resource "aws_iam_policy" "volcan_bedrock_mantle" {
  count       = var.enable_bedrock_mantle ? 1 : 0
  name        = "volcan-bedrock-mantle-euw1-${var.environment}"
  description = "Optional permission to invoke the account default Bedrock Mantle project"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["bedrock-mantle:CreateInference"]
        Resource = "arn:aws:bedrock-mantle:${var.aws_region}:${data.aws_caller_identity.current.account_id}:project/default"
      }
    ]
  })
}

data "aws_caller_identity" "current" {}

resource "aws_iam_role_policy_attachment" "volcan_attach" {
  role       = aws_iam_role.volcan_lambda_role.name
  policy_arn = aws_iam_policy.volcan_serverless_policy.arn
}

resource "aws_iam_role_policy_attachment" "volcan_bedrock_mantle_attach" {
  count      = var.enable_bedrock_mantle ? 1 : 0
  role       = aws_iam_role.volcan_lambda_role.name
  policy_arn = aws_iam_policy.volcan_bedrock_mantle[0].arn
}

# 3. AWS Lambda Function for Streamable HTTP FastMCP Server ($0.00 Idle Cost)
resource "aws_lambda_function" "volcan_mcp_function" {
  function_name    = "volcan-mcp-euw1-${var.environment}"
  role             = aws_iam_role.volcan_lambda_role.arn
  runtime          = "python3.11"
  handler          = "src.interfaces.lambda_handler.handler"
  filename         = var.lambda_package_path
  source_code_hash = filebase64sha256(var.lambda_package_path)
  memory_size      = 256
  timeout          = 30

  environment {
    variables = {
      ENVIRONMENT            = var.environment
      VOLCAN_ENVIRONMENT     = "production-eu-west-1"
      SOURCE_REVISION        = var.source_revision
      VOLCAN_GITHUB_WRITE    = "0"
      VOLCAN_ALLOWED_ORIGINS = "https://qylv1gxor9.execute-api.eu-west-1.amazonaws.com"
      VOLCAN_STATE_TABLE     = aws_dynamodb_table.volcan_state.name
      VOLCAN_APPROVAL_SECRET_ARN = var.volcan_approval_secret_arn
      # API Gateway may route consecutive requests to different Lambda
      # environments. MCP 2025-11-25 makes transport sessions optional, while
      # dialogue, actions, nonce consumption and audit state are shared through
      # the conditional DynamoDB table above.
      VOLCAN_MCP_SESSION_MODE = "stateless"
      AWS_LWA_INVOKE_MODE     = "response_stream"
    }
  }

  tags = {
    Project     = "volcan"
    Environment = var.environment
    Region      = var.aws_region
    ManagedBy   = "terraform"
    Hackathon   = "amazon-developer-2026"
  }
}

# 4. HTTPS Lambda Function URL (Replaces costly Application Load Balancers)
resource "aws_lambda_function_url" "volcan_mcp_url" {
  function_name      = aws_lambda_function.volcan_mcp_function.function_name
  authorization_type = "NONE"

  cors {
    allow_credentials = false
    allow_origins     = ["*"]
    # Lambda Function URL validates method tokens at six characters maximum;
    # the service handles browser preflight without an explicit OPTIONS token.
    allow_methods     = ["GET", "POST"]
    allow_headers     = ["content-type", "x-mcp-version", "authorization"]
    max_age           = 86400
  }
}

# 5. CloudWatch Log Group with 14-day retention
resource "aws_cloudwatch_log_group" "volcan_lambda_logs" {
  name              = "/aws/lambda/volcan-mcp-euw1-${var.environment}"
  retention_in_days = 14
}

# Outputs
output "volcan_function_url" {
  value       = aws_lambda_function_url.volcan_mcp_url.function_url
  description = "Public HTTPS Streamable HTTP FastMCP endpoint on AWS Lambda"
}

output "lambda_function_arn" {
  value       = aws_lambda_function.volcan_mcp_function.arn
  description = "ARN of the Volcan Serverless Lambda function"
}

output "state_table_name" {
  value       = aws_dynamodb_table.volcan_state.name
  description = "DynamoDB table holding conditional multi-turn state and audit records"
}
