# InnovateUS AWS Deployment Guide

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Step 1: AWS Account Setup](#step-1-aws-account-setup)
3. [Step 2: Create DynamoDB Tables](#step-2-create-dynamodb-tables)
4. [Step 3: Create IAM Roles & Policies](#step-3-create-iam-roles--policies)
5. [Step 4: Prepare Environment Variables](#step-4-prepare-environment-variables)
6. [Step 5: Deploy Backend to Lambda](#step-5-deploy-backend-to-lambda)
7. [Step 6: Deploy Frontend to S3 + CloudFront](#step-6-deploy-frontend-to-s3--cloudfront)
8. [Step 7: API Gateway Configuration](#step-7-api-gateway-configuration)
9. [Step 8: Testing & Verification](#step-8-testing--verification)
10. [Step 9: Monitoring & Logs](#step-9-monitoring--logs)
11. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before starting, you'll need:

- **AWS Account** with appropriate permissions (Admin role initially)
- **AWS CLI** installed and configured: `aws --version`
- **Python 3.9+** for building Lambda package
- **Node.js 18+** for building Next.js frontend
- **Git** with access to your repository
- **API Keys:**
  - OpenAI API key (for GPT-4o, Whisper)
  - Qualtrics API token + data center URL (optional, for Qualtrics sync)
  - JotForm API key (optional, for JotForm sync)

### Quick AWS CLI Setup

```bash
# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-windows-x86_64.exe" -o "AWSCLIV2.exe"
.\AWSCLIV2.exe

# Configure credentials
aws configure
# Enter: AWS Access Key ID, Secret Access Key, Region (us-east-1), Output format (json)

# Verify
aws sts get-caller-identity
```

---

## Step 1: AWS Account Setup

### 1.1 Choose a Region

We recommend **us-east-1** (N. Virginia) for lowest latency to OpenAI APIs. All commands below assume `us-east-1`.

```bash
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "Account ID: $AWS_ACCOUNT_ID"
```

### 1.2 Create an S3 Bucket for Lambda Packages

```bash
aws s3 mb s3://innovateus-lambda-builds-${AWS_ACCOUNT_ID} --region us-east-1
```

---

## Step 2: Create DynamoDB Tables

### 2.1 Create surveys Table

```bash
aws dynamodb create-table \
  --table-name innovateus-surveys \
  --attribute-definitions AttributeName=pk,AttributeType=S AttributeName=sk,AttributeType=S \
  --key-schema AttributeName=pk,KeyType=HASH AttributeName=sk,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1

# Wait for table to be ACTIVE
aws dynamodb wait table-exists --table-name innovateus-surveys --region us-east-1
```

### 2.2 Create submissions Table with GSI

```bash
aws dynamodb create-table \
  --table-name innovateus-submissions \
  --attribute-definitions \
    AttributeName=pk,AttributeType=S \
    AttributeName=sk,AttributeType=S \
    AttributeName=ip_hash,AttributeType=S \
    AttributeName=created_at,AttributeType=S \
  --key-schema AttributeName=pk,KeyType=HASH AttributeName=sk,KeyType=RANGE \
  --global-secondary-indexes \
    "IndexName=IpHashIndex,Keys=[{AttributeName=ip_hash,KeyType=HASH},{AttributeName=created_at,KeyType=RANGE}],Projection={ProjectionType=ALL},ProvisionedThroughput={ReadCapacityUnits=1,WriteCapacityUnits=1}" \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1

# Wait for table to be ACTIVE
aws dynamodb wait table-exists --table-name innovateus-submissions --region us-east-1
```

### 2.3 Enable Backup & Point-in-Time Recovery

```bash
# Enable point-in-time recovery
aws dynamodb update-continuous-backups \
  --table-name innovateus-surveys \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true \
  --region us-east-1

aws dynamodb update-continuous-backups \
  --table-name innovateus-submissions \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true \
  --region us-east-1

# Verify
aws dynamodb describe-continuous-backups --table-name innovateus-surveys --region us-east-1
```

### 2.4 Seed Initial Data (Optional)

```bash
cd apps/api
python seed.py  # This creates a sample cohort
```

---

## Step 3: Create IAM Roles & Policies

### 3.1 Create Lambda Execution Role (Trust Policy)

```bash
cat > trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

aws iam create-role \
  --role-name innovateus-lambda-role \
  --assume-role-policy-document file://trust-policy.json
```

### 3.2 Attach Basic Lambda Execution Policy

```bash
# Allows CloudWatch Logs
aws iam attach-role-policy \
  --role-name innovateus-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
```

### 3.3 Create DynamoDB Access Policy

```bash
cat > dynamodb-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:BatchWriteItem"
      ],
      "Resource": [
        "arn:aws:dynamodb:*:*:table/innovateus-surveys",
        "arn:aws:dynamodb:*:*:table/innovateus-submissions",
        "arn:aws:dynamodb:*:*:table/innovateus-submissions/index/IpHashIndex"
      ]
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name innovateus-lambda-role \
  --policy-name dynamodb-access \
  --policy-document file://dynamodb-policy.json
```

### 3.4 Create Secrets Manager Policy (Optional, for API keys)

```bash
cat > secrets-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:*:*:secret:innovateus/*"
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name innovateus-lambda-role \
  --policy-name secrets-access \
  --policy-document file://secrets-policy.json
```

---

## Step 4: Prepare Environment Variables

### 4.1 Store Secrets in Secrets Manager

```bash
# Store OpenAI API key
aws secretsmanager create-secret \
  --name innovateus/openai-api-key \
  --secret-string "sk-..." \  # Replace with your actual key
  --region us-east-1

# Store admin password (hashed)
# First, generate hash locally:
python3 << 'EOF'
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
admin_pwd = "change-me-to-strong-password"
hash = pwd_context.hash(admin_pwd)
print(hash)
EOF

# Then store it:
aws secretsmanager create-secret \
  --name innovateus/admin-password-hash \
  --secret-string "<hash-from-above>" \
  --region us-east-1

# Store editor password hash
aws secretsmanager create-secret \
  --name innovateus/editor-password-hash \
  --secret-string "<editor-hash>" \
  --region us-east-1

# (Optional) Store Qualtrics credentials
aws secretsmanager create-secret \
  --name innovateus/qualtrics-api-token \
  --secret-string "your-token" \
  --region us-east-1
```

### 4.2 Create .env.production for Lambda

Create `apps/api/.env.production`:

```bash
# Database
AWS_REGION=us-east-1
SURVEYS_TABLE=innovateus-surveys
SUBMISSIONS_TABLE=innovateus-submissions

# JWT
JWT_SECRET=your-super-secret-jwt-key-here  # Use a strong random string
JWT_ALGORITHM=HS256
TOKEN_EXPIRATION_MINUTES=1440

# CORS
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# OpenAI
OPENAI_API_KEY=$secret:innovateus/openai-api-key

# Hashes (from secretsmanager)
ADMIN_PASSWORD_HASH=$secret:innovateus/admin-password-hash
EDITOR_PASSWORD_HASH=$secret:innovateus/editor-password-hash

# Qualtrics (optional)
QUALTRICS_API_TOKEN=$secret:innovateus/qualtrics-api-token
QUALTRICS_DATA_CENTER=ca1
QUALTRICS_SURVEY_ID=your-survey-id

# JotForm (optional)
JOTFORM_API_KEY=$secret:innovateus/jotform-api-key
```

---

## Step 5: Deploy Backend to Lambda

### 5.1 Package Backend (Single Lambda Option - Recommended Start)

```bash
cd apps/api

# Install dependencies
pip install -r requirements.txt -t package/

# Copy source code
cp -r app/ package/
cp -r services/ package/
cp -r routers/ package/  
cp main.py package/

# Create deployment package
cd package
zip -r ../lambda-package.zip .
cd ..
```

### 5.2 Create Lambda Function

```bash
LAMBDA_ROLE_ARN=$(aws iam get-role --role-name innovateus-lambda-role --query Role.Arn --output text)

aws lambda create-function \
  --function-name innovateus-backend \
  --runtime python3.9 \
  --handler main.handler \
  --role $LAMBDA_ROLE_ARN \
  --timeout 120 \
  --memory-size 1024 \
  --zip-file fileb://lambda-package.zip \
  --environment Variables='{ \
    AWS_REGION=us-east-1, \
    SURVEYS_TABLE=innovateus-surveys, \
    SUBMISSIONS_TABLE=innovateus-submissions, \
    JWT_SECRET=your-secret, \
    OPENAI_API_KEY=sk-..., \
    CORS_ORIGINS=https://yourdomain.com \
  }' \
  --region us-east-1
```

### 5.3 Configure Lambda for Mangum

Update `apps/api/main.py` to export the Mangum handler:

```python
from fastapi import FastAPI
from mangum import Mangum
from app.routers import survey, submissions, admin, editor, ai, transcribe, export

app = FastAPI(title="InnovateUS Feedback API")

# Register routers
app.include_router(survey.router, prefix="/v1/survey", tags=["survey"])
app.include_router(submissions.router, prefix="/v1/submissions", tags=["submissions"])
app.include_router(admin.router, prefix="/v1/admin", tags=["admin"])
app.include_router(editor.router, prefix="/v1/admin", tags=["editor"])
app.include_router(ai.router, prefix="/v1/ai", tags=["ai"])
app.include_router(transcribe.router, prefix="/v1/transcribe", tags=["transcribe"])
app.include_router(export.router, prefix="/v1/admin/export", tags=["export"])

# Health check
@app.get("/health")
def health():
    return {"status": "ok"}

# Mangum handler for Lambda
handler = Mangum(app)
```

---

## Step 6: Deploy Frontend to S3 + CloudFront

### 6.1 Build Next.js

```bash
cd apps/web

# Set environment variables for build
export NEXT_PUBLIC_API_URL=https://your-api-gateway-url.execute-api.us-east-1.amazonaws.com/

npm run build
```

### 6.2 Create S3 Bucket

```bash
aws s3 mb s3://innovateus-frontend-${AWS_ACCOUNT_ID} --region us-east-1

# Enable static website hosting
aws s3 website s3://innovateus-frontend-${AWS_ACCOUNT_ID}/ \
  --index-document index.html \
  --error-document 404.html
```

### 6.3 Upload Built Files

```bash
aws s3 sync out/ s3://innovateus-frontend-${AWS_ACCOUNT_ID}/ \
  --delete \
  --cache-control "public, max-age=31536000, immutable"
```

### 6.4 Create CloudFront Distribution

```bash
cat > cloudfront-config.json << 'EOF'
{
  "CallerReference": "innovateus-$(date +%s)",
  "Comment": "InnovateUS Frontend",
  "DefaultRootObject": "index.html",
  "Origins": {
    "Items": [
      {
        "Id": "S3Origin",
        "DomainName": "innovateus-frontend-ACCOUNT_ID.s3.us-east-1.amazonaws.com",
        "S3OriginConfig": {
          "OriginAccessIdentity": ""
        }
      }
    ],
    "Quantity": 1
  },
  "DefaultCacheBehavior": {
    "ViewerProtocolPolicy": "redirect-to-https",
    "AllowedMethods": {
      "Items": ["GET", "HEAD"],
      "Quantity": 2
    },
    "TargetOriginId": "S3Origin",
    "ForwardedValues": {
      "QueryString": false,
      "Cookies": {"Forward": "none"}
    },
    "TrustedSigners": {
      "Enabled": false,
      "Quantity": 0
    },
    "MinTTL": 0
  },
  "Enabled": true
}
EOF

# Create distribution
aws cloudfront create-distribution --distribution-config file://cloudfront-config.json
```

---

## Step 7: API Gateway Configuration

### 7.1 Create HTTP API

```bash
LAMBDA_ARN=$(aws lambda get-function --function-name innovateus-backend --query Configuration.FunctionArn --output text)

aws apigatewayv2 create-api \
  --name innovateus-api \
  --protocol-type HTTP \
  --target $LAMBDA_ARN \
  --region us-east-1
```

### 7.2 Configure CORS

```bash
API_ID=$(aws apigatewayv2 get-apis --region us-east-1 --query "Items[?Name=='innovateus-api'].ApiId" --output text)

aws apigatewayv2 update-api \
  --api-id $API_ID \
  --cors-configuration \
    AllowCredentials=true, \
    AllowHeaders="Content-Type,X-Amz-Date,Authorization,X-Api-Key", \
    AllowMethods="GET,POST,PUT,DELETE,OPTIONS", \
    AllowOrigins="https://yourdomain.com", \
    MaxAge=3600 \
  --region us-east-1
```

### 7.3 Deploy API Stage

```bash
aws apigatewayv2 create-stage \
  --api-id $API_ID \
  --stage-name prod \
  --auto-deploy \
  --region us-east-1
```

### 7.4 Grant API Gateway Lambda Permission

```bash
aws lambda add-permission \
  --function-name innovateus-backend \
  --statement-id AllowAPIGateway \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --region us-east-1
```

---

## Step 8: Testing & Verification

### 8.1 Test API Gateway

```bash
# Get API endpoint
API_ENDPOINT=$(aws apigatewayv2 get-apis --region us-east-1 --query "Items[?Name=='innovateus-api'].ApiEndpoint" --output text)

# Test health check
curl -X GET "${API_ENDPOINT}/health"

# Expected: {"status":"ok"}
```

### 8.2 Test Survey Endpoint

```bash
# Get a cohort_id (if you seeded data)
COHORT_ID="your-cohort-id-here"

curl -X GET "${API_ENDPOINT}/v1/survey/${COHORT_ID}"

# Should return survey config JSON
```

### 8.3 Test Admin Login

```bash
curl -X POST "${API_ENDPOINT}/v1/admin/login" \
  -H "Content-Type: application/json" \
  -d '{"password":"your-admin-password"}'

# Should return JWT token
```

---

## Step 9: Monitoring & Logs

### 9.1 View Lambda Logs

```bash
# View recent logs
aws logs tail /aws/lambda/innovateus-backend --follow --region us-east-1

# Search for errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/innovateus-backend \
  --filter-pattern "ERROR" \
  --region us-east-1
```

### 9.2 CloudWatch Metrics

```bash
# View Lambda invocations
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=innovateus-backend \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-02T00:00:00Z \
  --period 3600 \
  --statistics Sum \
  --region us-east-1

# View Lambda errors
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=innovateus-backend \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-02T00:00:00Z \
  --period 3600 \
  --statistics Sum \
  --region us-east-1
```

### 9.3 Set Up Alarms

```bash
# Alert on Lambda errors
aws cloudwatch put-metric-alarm \
  --alarm-name innovateus-lambda-errors \
  --alarm-description "Alert when Lambda errors > 5" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=FunctionName,Value=innovateus-backend \
  --evaluation-periods 1 \
  --alarm-actions "arn:aws:sns:us-east-1:${AWS_ACCOUNT_ID}:innovateus-alerts" \
  --region us-east-1
```

---

## Troubleshooting

### Issue: Lambda Timeout

**Symptom:** "Task timed out after X seconds"

**Solution:**
1. Increase Lambda timeout: `aws lambda update-function-configuration --function-name innovateus-backend --timeout 180`
2. Check for slow DB queries with CloudWatch logs
3. Monitor OpenAI API latency (add timing logs)

### Issue: DynamoDB Throttling

**Symptom:** "ProvisionedThroughputExceededException"

**Solution:**
- We use PAY_PER_REQUEST, so this shouldn't happen unless there's a bug
- Check for scan operations without limit in logs
- Enable auto-scaling for the GSI if using PROVISIONED mode

### Issue: CORS Errors

**Symptom:** "No 'Access-Control-Allow-Origin' header"

**Solution:**
1. Verify CloudFront domain is in API Gateway CORS origins
2. Check that CORS_ORIGINS env var includes your frontend domain
3. Verify CloudFront is not caching the error response

### Issue: API Gateway 404

**Symptom:** "Not Found" on all API calls

**Solution:**
1. Verify Lambda is linked to API Gateway: `aws apigatewayv2 get-integrations --api-id <API_ID>`
2. Check Lambda execution role has no permission issues
3. Redeploy Lambda function: `aws lambda update-function-code --function-name innovateus-backend --zip-file fileb://lambda-package.zip`

### Issue: Cold Starts Too Slow

**Symptom:** First request takes 10+ seconds

**Solution:**
1. Increase Lambda memory to 1024 MB (faster CPU)
2. Use Lambda Provisioned Concurrency for production (higher cost)
3. Split into multiple Lambdas by function (see architecture doc)

---

## Next Steps

1. **Set up a custom domain** with Route53 + ACM certificate
2. **Enable WAF** on CloudFront for DDoS protection
3. **Set up CI/CD pipeline** with GitHub Actions to auto-deploy on push
4. **Configure monitoring alerts** for production
5. **Run load tests** to validate scaling behavior
6. **Set up database backups** (enable DynamoDB point-in-time recovery)

---

## Quick Reference Commands

```bash
# View all Lambda functions
aws lambda list-functions --region us-east-1

# View API Gateway endpoints
aws apigatewayv2 get-apis --region us-east-1

# View DynamoDB table size
aws dynamodb describe-table --table-name innovateus-surveys --region us-east-1 --query Table.TableSizeBytes

# Update Lambda environment variables
aws lambda update-function-configuration \
  --function-name innovateus-backend \
  --environment Variables={KEY=value} \
  --region us-east-1

# Download latest Lambda logs
aws logs get-log-events \
  --log-group-name /aws/lambda/innovateus-backend \
  --log-stream-name $(aws logs describe-log-streams --log-group-name /aws/lambda/innovateus-backend --order-by LastEventTime --descending --max-items 1 --query logStreams[0].logStreamName --output text) \
  --region us-east-1
```
