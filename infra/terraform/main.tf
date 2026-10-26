terraform {
  required_version = ">= 1.8, < 2.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}
provider "aws" { region = var.region }
variable "region" { type = string }
variable "workload_principal_arn" {
  type        = string
  description = "Existing workload IAM role allowed to assume the read-only discovery role"
}
resource "aws_iam_role" "discovery" {
  name_prefix = "atlasops-discovery-"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { AWS = var.workload_principal_arn }, Action = "sts:AssumeRole" }]
  })
}
resource "aws_iam_role_policy" "discovery" {
  role = aws_iam_role.discovery.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = ["ec2:DescribeInstances", "cloudwatch:GetMetricStatistics", "cloudwatch:DescribeAlarms"]
      Resource  = "*"
      Condition = { StringEquals = { "aws:RequestedRegion" = var.region } }
    }]
  })
}
output "discovery_role_arn" { value = aws_iam_role.discovery.arn }
