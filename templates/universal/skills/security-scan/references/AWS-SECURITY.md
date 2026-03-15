# AWS Security Best Practices

## Overview

This guide covers AWS security best practices for your cloud infrastructure, including Lambda functions, API Gateway, S3, RDS Aurora, and other AWS services used in the platform.

**Sources**:
- [AWS Well-Architected Framework - Security Pillar](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/)
- [AWS Security Best Practices](https://aws.amazon.com/architecture/security-identity-compliance/)

---

## AWS Lambda Security

### Function Configuration

```yaml
# serverless.yml - Secure Lambda configuration
provider:
  name: aws
  runtime: nodejs18.x
  memorySize: 256
  timeout: 30
  
  # IAM Role with least privilege
  iam:
    role:
      statements:
        - Effect: Allow
          Action:
            - dynamodb:GetItem
            - dynamodb:PutItem
            - dynamodb:Query
          Resource: 
            - !GetAtt ParticipantTable.Arn
            - !Sub "${ParticipantTable.Arn}/index/*"
        # NO wildcard resources!

  # VPC configuration for internal resources
  vpc:
    securityGroupIds:
      - !Ref LambdaSecurityGroup
    subnetIds:
      - !Ref PrivateSubnet1
      - !Ref PrivateSubnet2

  # Environment encryption
  environment:
    NODE_ENV: production
    # Reference secrets, don't store values
    DB_SECRET_ARN: !Ref DatabaseSecret
```

### Least Privilege IAM

```typescript
// ❌ Over-permissive IAM policy
{
  "Effect": "Allow",
  "Action": "s3:*",
  "Resource": "*"
}

// ✅ Least privilege IAM policy
{
  "Effect": "Allow",
  "Action": [
    "s3:GetObject",
    "s3:PutObject"
  ],
  "Resource": [
    "arn:aws:s3:::app-documents-prod/uploads/*"
  ],
  "Condition": {
    "StringEquals": {
      "aws:RequestTag/Environment": "production"
    }
  }
}
```

### Secrets Management

```typescript
import { SecretsManagerClient, GetSecretValueCommand } from '@aws-sdk/client-secrets-manager';

// Cache secrets to avoid repeated API calls
let cachedSecrets: Record<string, string> | null = null;

async function getSecrets(): Promise<Record<string, string>> {
  if (cachedSecrets) return cachedSecrets;
  
  const client = new SecretsManagerClient({ region: process.env.AWS_REGION });
  const command = new GetSecretValueCommand({
    SecretId: process.env.DB_SECRET_ARN
  });
  
  const response = await client.send(command);
  cachedSecrets = JSON.parse(response.SecretString!);
  return cachedSecrets;
}

// Usage
export const handler = async (event: APIGatewayEvent) => {
  const secrets = await getSecrets();
  const connection = await createConnection({
    host: secrets.host,
    user: secrets.username,
    password: secrets.password
  });
  // ...
};
```

### Lambda Layer Security

```yaml
# Keep dependencies updated
layers:
  CommonDependencies:
    path: layers/common
    description: Shared dependencies with security patches
    compatibleRuntimes:
      - nodejs18.x
    retain: false  # Remove old versions
```

---

## API Gateway Security

### Authorization Configuration

```yaml
# serverless.yml - API Gateway with Okta authorizer
functions:
  getParticipants:
    handler: src/handlers/participants.get
    events:
      - http:
          path: /api/participants
          method: get
          cors: true
          authorizer:
            name: OktaAuthorizer
            type: TOKEN
            identitySource: method.request.header.Authorization
            resultTtlInSeconds: 300

# Custom authorizer function
  OktaAuthorizer:
    handler: src/authorizers/okta.handler
    environment:
      OKTA_ISSUER: ${env:OKTA_ISSUER}
      OKTA_AUDIENCE: ${env:OKTA_AUDIENCE}
```

### Request Validation

```yaml
# OpenAPI request validation
x-amazon-apigateway-request-validators:
  all:
    validateRequestBody: true
    validateRequestParameters: true

paths:
  /participants:
    post:
      x-amazon-apigateway-request-validator: all
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateParticipantRequest'
```

### WAF Integration

```typescript
// CloudFormation for WAF rules
const wafRules = {
  Type: 'AWS::WAFv2::WebACL',
  Properties: {
    Name: 'api-waf',
    Scope: 'REGIONAL',
    DefaultAction: { Allow: {} },
    Rules: [
      {
        Name: 'RateLimitRule',
        Priority: 1,
        Action: { Block: {} },
        Statement: {
          RateBasedStatement: {
            Limit: 2000, // requests per 5 minutes
            AggregateKeyType: 'IP'
          }
        },
        VisibilityConfig: {
          CloudWatchMetricsEnabled: true,
          MetricName: 'RateLimitRule',
          SampledRequestsEnabled: true
        }
      },
      {
        Name: 'SQLInjectionRule',
        Priority: 2,
        Action: { Block: {} },
        Statement: {
          SqliMatchStatement: {
            FieldToMatch: { Body: {} },
            TextTransformations: [{ Type: 'URL_DECODE', Priority: 1 }]
          }
        },
        VisibilityConfig: {
          CloudWatchMetricsEnabled: true,
          MetricName: 'SQLInjectionRule',
          SampledRequestsEnabled: true
        }
      },
      {
        Name: 'AWSManagedRulesCommon',
        Priority: 3,
        OverrideAction: { None: {} },
        Statement: {
          ManagedRuleGroupStatement: {
            VendorName: 'AWS',
            Name: 'AWSManagedRulesCommonRuleSet'
          }
        },
        VisibilityConfig: {
          CloudWatchMetricsEnabled: true,
          MetricName: 'AWSManagedRulesCommon',
          SampledRequestsEnabled: true
        }
      }
    ]
  }
};
```

### Throttling Configuration

```yaml
# API Gateway stage throttling
provider:
  apiGateway:
    throttle:
      burstLimit: 200
      rateLimit: 100
    
    # Method-level throttling
    usagePlan:
      quota:
        limit: 10000
        period: MONTH
      throttle:
        burstLimit: 50
        rateLimit: 25
```

---

## S3 Security

### Bucket Configuration

```typescript
// CloudFormation for secure S3 bucket
const documentsBucket = {
  Type: 'AWS::S3::Bucket',
  Properties: {
    BucketName: 'app-documents-prod',
    
    // Block all public access
    PublicAccessBlockConfiguration: {
      BlockPublicAcls: true,
      BlockPublicPolicy: true,
      IgnorePublicAcls: true,
      RestrictPublicBuckets: true
    },
    
    // Encryption at rest
    BucketEncryption: {
      ServerSideEncryptionConfiguration: [{
        ServerSideEncryptionByDefault: {
          SSEAlgorithm: 'aws:kms',
          KMSMasterKeyID: { Ref: 'DocumentsKMSKey' }
        },
        BucketKeyEnabled: true
      }]
    },
    
    // Versioning for recovery
    VersioningConfiguration: {
      Status: 'Enabled'
    },
    
    // Access logging
    LoggingConfiguration: {
      DestinationBucketName: { Ref: 'AccessLogsBucket' },
      LogFilePrefix: 'documents/'
    },
    
    // Lifecycle rules
    LifecycleConfiguration: {
      Rules: [{
        Id: 'TransitionToIA',
        Status: 'Enabled',
        Transitions: [{
          StorageClass: 'STANDARD_IA',
          TransitionInDays: 90
        }]
      }]
    }
  }
};
```

### Bucket Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EnforceTLS",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::app-documents-prod",
        "arn:aws:s3:::app-documents-prod/*"
      ],
      "Condition": {
        "Bool": {
          "aws:SecureTransport": "false"
        }
      }
    },
    {
      "Sid": "EnforceEncryption",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::app-documents-prod/*",
      "Condition": {
        "StringNotEquals": {
          "s3:x-amz-server-side-encryption": "aws:kms"
        }
      }
    }
  ]
}
```

### Pre-Signed URLs

```typescript
import { S3Client, GetObjectCommand, PutObjectCommand } from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';

const s3Client = new S3Client({ region: process.env.AWS_REGION });

// Generate secure download URL
async function getDownloadUrl(key: string): Promise<string> {
  const command = new GetObjectCommand({
    Bucket: process.env.DOCUMENTS_BUCKET,
    Key: key
  });
  
  return getSignedUrl(s3Client, command, {
    expiresIn: 300 // 5 minutes
  });
}

// Generate secure upload URL with restrictions
async function getUploadUrl(key: string, contentType: string): Promise<string> {
  const command = new PutObjectCommand({
    Bucket: process.env.DOCUMENTS_BUCKET,
    Key: key,
    ContentType: contentType,
    ServerSideEncryption: 'aws:kms',
    SSEKMSKeyId: process.env.KMS_KEY_ID
  });
  
  return getSignedUrl(s3Client, command, {
    expiresIn: 300
  });
}
```

---

## RDS Aurora Security

### Database Configuration

```yaml
# CloudFormation for secure Aurora cluster
AuroraCluster:
  Type: AWS::RDS::DBCluster
  Properties:
    Engine: aurora-postgresql
    EngineVersion: '14.6'
    
    # Encryption
    StorageEncrypted: true
    KmsKeyId: !Ref DatabaseKMSKey
    
    # Authentication
    MasterUsername: !Sub '{{resolve:secretsmanager:${DatabaseSecret}:SecretString:username}}'
    MasterUserPassword: !Sub '{{resolve:secretsmanager:${DatabaseSecret}:SecretString:password}}'
    IAMDatabaseAuthenticationEnabled: true
    
    # Network
    DBSubnetGroupName: !Ref DBSubnetGroup
    VpcSecurityGroupIds:
      - !Ref DatabaseSecurityGroup
    
    # Backup
    BackupRetentionPeriod: 35
    PreferredBackupWindow: "02:00-03:00"
    DeletionProtection: true
    
    # Logging
    EnableCloudwatchLogsExports:
      - postgresql

DatabaseSecurityGroup:
  Type: AWS::EC2::SecurityGroup
  Properties:
    GroupDescription: Security group for Aurora
    VpcId: !Ref VPC
    SecurityGroupIngress:
      # Only allow from Lambda security group
      - IpProtocol: tcp
        FromPort: 5432
        ToPort: 5432
        SourceSecurityGroupId: !Ref LambdaSecurityGroup
```

### IAM Database Authentication

```typescript
import { RDSClient, GenerateAuthTokenCommand } from '@aws-sdk/client-rds';
import { Pool } from 'pg';

const rdsClient = new RDSClient({ region: process.env.AWS_REGION });

async function createAuthToken(): Promise<string> {
  const command = new GenerateAuthTokenCommand({
    hostname: process.env.DB_HOST,
    port: 5432,
    username: 'lambda_user',
    region: process.env.AWS_REGION
  });
  
  return rdsClient.send(command);
}

async function getPool(): Promise<Pool> {
  const token = await createAuthToken();
  
  return new Pool({
    host: process.env.DB_HOST,
    port: 5432,
    user: 'lambda_user',
    password: token,
    database: process.env.DB_NAME,
    ssl: {
      rejectUnauthorized: true,
      ca: fs.readFileSync('/var/task/rds-ca-bundle.pem')
    }
  });
}
```

---

## CloudWatch & Monitoring

### Security Logging

```typescript
// Lambda security logging
import { Logger } from '@aws-lambda-powertools/logger';

const logger = new Logger({
  serviceName: 'participant-api',
  logLevel: 'INFO'
});

// Log security events
logger.info('Authentication successful', {
  userId: user.id,
  sourceIp: event.requestContext.identity.sourceIp,
  userAgent: event.requestContext.identity.userAgent
});

logger.warn('Authorization denied', {
  userId: user.id,
  resource: event.path,
  requiredPrivilege: 'VIEW_PARTICIPANTS',
  reason: 'Missing privilege'
});
```

### CloudWatch Alarms

```yaml
# Security-related CloudWatch alarms
UnauthorizedApiCalls:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: App-UnauthorizedApiCalls
    MetricName: Count
    Namespace: AWS/ApiGateway
    Statistic: Sum
    Period: 300
    EvaluationPeriods: 1
    Threshold: 100
    ComparisonOperator: GreaterThanThreshold
    Dimensions:
      - Name: ApiName
        Value: !Ref ApiGateway
      - Name: Stage
        Value: prod
    TreatMissingData: notBreaching
    AlarmActions:
      - !Ref SecurityAlertTopic

FailedLogins:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: App-FailedLogins
    MetricName: FailedLoginAttempts
    Namespace: App/Security
    Statistic: Sum
    Period: 300
    EvaluationPeriods: 1
    Threshold: 50
    ComparisonOperator: GreaterThanThreshold
```

---

## KMS Key Management

```yaml
# CMK for data encryption
DocumentsKMSKey:
  Type: AWS::KMS::Key
  Properties:
    Description: KMS key for document encryption
    EnableKeyRotation: true
    KeyPolicy:
      Version: '2012-10-17'
      Statement:
        - Sid: EnableRootPermissions
          Effect: Allow
          Principal:
            AWS: !Sub 'arn:aws:iam::${AWS::AccountId}:root'
          Action: 'kms:*'
          Resource: '*'
        - Sid: AllowLambdaUse
          Effect: Allow
          Principal:
            AWS: !GetAtt LambdaRole.Arn
          Action:
            - 'kms:Decrypt'
            - 'kms:GenerateDataKey'
          Resource: '*'
          Condition:
            StringEquals:
              'kms:ViaService': !Sub 's3.${AWS::Region}.amazonaws.com'
```

---

## Security Checklist

### Lambda
- [ ] Use least-privilege IAM roles
- [ ] Store secrets in Secrets Manager
- [ ] Enable VPC for internal resources
- [ ] Set appropriate timeout/memory
- [ ] Use Lambda Powertools for logging
- [ ] Enable X-Ray tracing

### API Gateway
- [ ] Enable authorization on all endpoints
- [ ] Configure request validation
- [ ] Set up WAF rules
- [ ] Enable throttling
- [ ] Configure CORS properly
- [ ] Enable access logging

### S3
- [ ] Block public access
- [ ] Enable encryption (KMS)
- [ ] Enable versioning
- [ ] Configure bucket policies
- [ ] Enable access logging
- [ ] Use pre-signed URLs

### RDS
- [ ] Enable encryption at rest
- [ ] Use IAM authentication
- [ ] Configure VPC security groups
- [ ] Enable automated backups
- [ ] Enable audit logging
- [ ] Use SSL/TLS connections

### General
- [ ] Enable CloudTrail
- [ ] Configure CloudWatch alarms
- [ ] Enable AWS Config rules
- [ ] Use AWS Organizations SCPs
- [ ] Implement tagging strategy
- [ ] Enable GuardDuty

---

## References

- [AWS Well-Architected Framework - Security Pillar](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/)
- [AWS Lambda Security Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/security.html)
- [AWS API Gateway Security](https://docs.aws.amazon.com/apigateway/latest/developerguide/security.html)
- [AWS S3 Security Best Practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html)
- [AWS RDS Security](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.html)

---

*Last Updated: January 2026*
