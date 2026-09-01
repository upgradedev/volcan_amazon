# Terraform Infrastructure for Volcan Accessible AI Agent Forge on AWS

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
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "prod"
}

# IAM Role for Volcan Execution with Least Privilege Bedrock Access
resource "aws_iam_role" "volcan_exec_role" {
  name = "volcan-execution-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "volcan_bedrock_least_privilege" {
  name        = "volcan-bedrock-policy-${var.environment}"
  description = "Least privilege access to Amazon Bedrock models for AST synthesis"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = [
          "arn:aws:bedrock:${var.aws_region}::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0",
          "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.nova-micro-v1:0"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "volcan_attach" {
  role       = aws_iam_role.volcan_exec_role.name
  policy_arn = aws_iam_policy.volcan_bedrock_least_privilege.arn
}

# ECS Cluster for Streamable HTTP FastMCP Container
resource "aws_ecs_cluster" "volcan_cluster" {
  name = "volcan-cluster-${var.environment}"
}

# CloudWatch Log Group for Immutable Governance Audit Trail
resource "aws_cloudwatch_log_group" "volcan_logs" {
  name              = "/ecs/volcan-mcp-${var.environment}"
  retention_in_days = 30
}

output "ecs_cluster_name" {
  value       = aws_ecs_cluster.volcan_cluster.name
  description = "Name of the Volcan ECS cluster"
}

output "iam_role_arn" {
  value       = aws_iam_role.volcan_exec_role.arn
  description = "ARN of the least-privilege IAM execution role"
}
