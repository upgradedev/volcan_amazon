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

# 2. Least-Privilege Policy for Amazon Bedrock & CloudWatch Logging
resource "aws_iam_policy" "volcan_serverless_policy" {
  name        = "volcan-serverless-policy-euw1-${var.environment}"
  description = "Least privilege access to Amazon Bedrock models and CloudWatch logs for Volcan"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        # Kept narrow on purpose: one model, named. A region-scoped inference
        # profile is a different ARN and would have to be added here as well.
        Resource = [
          "arn:aws:bedrock:${var.aws_region}::foundation-model/anthropic.claude-opus-5",
          "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.nova-micro-v1:0"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:*:log-group:/aws/lambda/volcan-mcp-euw1-${var.environment}:*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "volcan_attach" {
  role       = aws_iam_role.volcan_lambda_role.name
  policy_arn = aws_iam_policy.volcan_serverless_policy.arn
}

# 3. AWS Lambda Function for Streamable HTTP FastMCP Server ($0.00 Idle Cost)
resource "aws_lambda_function" "volcan_mcp_function" {
  function_name = "volcan-mcp-euw1-${var.environment}"
  role          = aws_iam_role.volcan_lambda_role.arn
  runtime       = "python3.11"
  handler       = "src.interfaces.mcp_server.handler"
  memory_size   = 256
  timeout       = 30

  environment {
    variables = {
      ENVIRONMENT         = var.environment
      AWS_LWA_INVOKE_MODE = "response_stream"
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
    allow_methods     = ["GET", "POST", "OPTIONS"]
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
