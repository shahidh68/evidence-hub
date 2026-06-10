import * as cdk from 'aws-cdk-lib';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';
import { join } from 'path';

/**
 * AI Decision Evidence Hub — single internal deployment.
 *
 *   Function URL ─▶ Lambda (container: FastAPI + Lambda Web Adapter)
 *                     ├─ reads its evidence data ─▶ DynamoDB (single table)
 *                     ├─ reads admin + ledger keys ─▶ Secrets Manager
 *                     └─ reads the ledger over HTTPS (AUDIT_API_URL)
 *
 * No VPC, no RDS — mirrors the AI Audit Ledger's serverless house style.
 */
export class EvidenceHubStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // The deployed ledger's API base URL, e.g.
    //   --context auditApiUrl=https://xxxx.execute-api.eu-west-1.amazonaws.com/prod
    const auditApiUrl = (this.node.tryGetContext('auditApiUrl') as string | undefined) ?? '';

    // ── DynamoDB single table (append-only evidence store) ──
    // pk = "DEC#<decision_id>" | "IDX#..." ; sk = "<TYPE>#<seq>" | "<id>"
    const table = new dynamodb.Table(this, 'EvidenceHubTable', {
      partitionKey: { name: 'pk', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'sk', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // ── Secret: {admin_api_key, ledger_read_key} ──
    // Stable placeholder so redeploys never rotate the live value (same approach
    // as the ledger). Populate once via the AWS Console after the first deploy.
    const secret = new secretsmanager.Secret(this, 'EvidenceHubSecret', {
      description:
        'Evidence Hub: JSON {admin_api_key, ledger_read_key}. Populate via Console after deploy.',
      generateSecretString: {
        secretStringTemplate: JSON.stringify({
          admin_api_key: 'populate-via-console',
          ledger_read_key: 'populate-via-console',
        }),
        generateStringKey: '_unused',
        excludePunctuation: true,
        passwordLength: 16,
      },
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // ── Lambda container (FastAPI + Web Adapter) ──
    // Build context = the evidence-hub project root (where the Dockerfile lives).
    const projectRoot = join(__dirname, '..', '..', '..');
    const fn = new lambda.DockerImageFunction(this, 'EvidenceHubFn', {
      code: lambda.DockerImageCode.fromImageAsset(projectRoot),
      memorySize: 512,
      timeout: cdk.Duration.seconds(30),
      logGroup: new logs.LogGroup(this, 'EvidenceHubFnLogGroup', {
        retention: logs.RetentionDays.ONE_WEEK,
      }),
      environment: {
        EVIDENCE_STORE: 'dynamodb',
        EVIDENCE_TABLE_NAME: table.tableName,
        EVIDENCE_SECRET_ARN: secret.secretArn,
        LEDGER_SOURCE: 'live',
        AUDIT_API_URL: auditApiUrl,
      },
    });

    // Least privilege: evidence table read/write + read the secret. No access to
    // the ledger's resources — it is read over HTTPS.
    table.grantReadWriteData(fn);
    secret.grantRead(fn);

    // Function URL; the admin x-api-key is enforced inside the app.
    const fnUrl = fn.addFunctionUrl({ authType: lambda.FunctionUrlAuthType.NONE });

    // ── Outputs ──
    new cdk.CfnOutput(this, 'FunctionUrl', {
      value: fnUrl.url,
      description: 'Evidence Hub base URL (dashboard at <url>ui/)',
    });
    new cdk.CfnOutput(this, 'EvidenceTableName', { value: table.tableName });
    new cdk.CfnOutput(this, 'EvidenceSecretArn', {
      value: secret.secretArn,
      description: 'Populate {admin_api_key, ledger_read_key} here after first deploy',
    });
  }
}
