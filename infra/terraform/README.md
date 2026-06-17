# Terraform

AWS infrastructure for Phase 1 Sentellent deployment.

## Resources

- ECS Fargate cluster and backend service
- API Gateway HTTP API proxy to backend
- RDS PostgreSQL
- ElastiCache Redis
- S3 + CloudFront for frontend static hosting
- CloudWatch log group and IAM execution role

## Usage

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars with VPC, subnet, secret ARNs, and credentials
terraform init
terraform plan
terraform apply
```

## Notes

- Configure the remote S3 backend bucket before first apply.
- Store secrets in AWS Secrets Manager and reference ARNs in task definitions.
- Run Alembic migrations through the GitHub Actions deploy workflow before ECS rollout.
