# AI Decision Evidence Hub — Admin Runbook

Operating the deployed Evidence Hub. Commands are PowerShell (Windows). The Hub
is serverless on AWS: a container **Lambda** behind a **Function URL**, a
**DynamoDB** table, and one **Secrets Manager** secret — no servers, no VPC.

---

## This deployment (reference)

| | |
|---|---|
| Region / account | `eu-west-1` / `174405733864` |
| CloudFormation stack | `EvidenceHubStack` |
| Function URL | `https://vn3ukm7afm57odbw7yinp7arp40ebapb.lambda-url.eu-west-1.on.aws/` |
| Dashboard | `<Function URL>ui/` |
| Lambda | `EvidenceHubStack-EvidenceHubFn5A0305B3-c9nEt4bWOeHI` |
| DynamoDB table | `EvidenceHubStack-EvidenceHubTableF2AA72EF-C8C5N687C1HA` |
| Secret | `EvidenceHubSecret…` (holds `admin_api_key`, `ledger_read_key`) |
| Reads ledger at | `https://m3csva3l3h.execute-api.eu-west-1.amazonaws.com/prod` |
| Ledger dashboard | `https://d2pfirb2397ixy.cloudfront.net` |

Pull current values any time:
```powershell
$region = "eu-west-1"
$out = aws cloudformation describe-stacks --stack-name EvidenceHubStack --region $region --query "Stacks[0].Outputs" | ConvertFrom-Json
$url       = ($out | ? OutputKey -eq "FunctionUrl").OutputValue
$secretArn = ($out | ? OutputKey -eq "EvidenceSecretArn").OutputValue
$table     = ($out | ? OutputKey -eq "EvidenceTableName").OutputValue
$fn        = aws cloudformation describe-stack-resources --stack-name EvidenceHubStack --region $region --query "StackResources[?ResourceType=='AWS::Lambda::Function'].PhysicalResourceId" --output text
"$url`n$secretArn`n$table`n$fn"
```

---

## Prerequisites

- **AWS credentials** for account `174405733864`, region `eu-west-1`
  (`aws sts get-caller-identity` must succeed).
- **Docker** running — CDK builds the Lambda image at deploy.
- **Node 20+** and the CDK deps (`cd infra/cdk; npm install`).

---

## Deploy / redeploy

Any code or dashboard change ships with one command (CDK rebuilds the image,
pushes to ECR, updates the Lambda):

```powershell
cd "C:\Users\AI Data Logger\evidence-hub\infra\cdk"
npx cdk deploy --context auditApiUrl=https://m3csva3l3h.execute-api.eu-west-1.amazonaws.com/prod
```

- `--context auditApiUrl=…` sets the ledger the Hub reads. **Always pass the real
  URL** or the Lambda gets a broken `AUDIT_API_URL`.
- Preview changes first with `npx cdk diff …`.
- First-ever deploy in a fresh account also needs `npx cdk bootstrap aws://174405733864/eu-west-1`.

---

## Secrets & key management

The secret is JSON: `{"admin_api_key": "...", "ledger_read_key": "..."}`.
The Lambda reads it **once at cold start** and caches it — see the reload step.

### Populate (first time)
```powershell
$adminKey = -join ((48..57)+(65..90)+(97..122) | Get-Random -Count 40 | %{[char]$_})
$payload  = @{ admin_api_key = $adminKey; ledger_read_key = "<ledger ADMIN read key>" } | ConvertTo-Json -Compress
aws secretsmanager put-secret-value --region $region --secret-id $secretArn --secret-string $payload
"ADMIN KEY (store in your password manager): $adminKey"
```
`ledger_read_key` should be a ledger **admin** read key (mapped to `"*"`) so the
Hub can evaluate decisions across all tenants.

### Rotate the admin key
```powershell
$new = -join ((48..57)+(65..90)+(97..122) | Get-Random -Count 40 | %{[char]$_})
$cur = aws secretsmanager get-secret-value --region $region --secret-id $secretArn --query SecretString --output text | ConvertFrom-Json
$cur.admin_api_key = $new
aws secretsmanager put-secret-value --region $region --secret-id $secretArn --secret-string ($cur | ConvertTo-Json -Compress)
# force fresh containers so the new key takes effect immediately:
aws lambda update-function-configuration --region $region --function-name $fn --description ("rotate " + (Get-Date -Format o)) | Out-Null
"new admin key: $new"
```
Rotating the **ledger read key** is the same pattern (replace `ledger_read_key`).

### The cold-start cache gotcha
After any secret change, the **warm** Lambda still holds the old value until the
container recycles. The `update-function-configuration` line above forces new
execution environments. Allow ~10–15s, then the next call uses the new secret.

---

## Configuration reference (Lambda env vars)

| Var | Value here | Purpose |
|---|---|---|
| `EVIDENCE_STORE` | `dynamodb` | storage backend |
| `EVIDENCE_TABLE_NAME` | the table name | DynamoDB table |
| `EVIDENCE_SECRET_ARN` | the secret ARN | admin + ledger keys |
| `LEDGER_SOURCE` | `live` | read the real ledger over HTTPS |
| `AUDIT_API_URL` | the ledger prod URL | which ledger |
| `EVIDENCE_LEDGER_DASHBOARD_URL` | CloudFront URL | dashboard cross-link (blank hides it) |
| `EVIDENCE_MANIFEST_PATH` | (unset) | repo manifest for auto-resolve, if used |

Inspect live:
```powershell
aws lambda get-function-configuration --region $region --function-name $fn --query "Environment.Variables"
```

---

## Routine operations

```powershell
$H = @{ "x-api-key" = "<admin key>" }

# health (open, no key)
Invoke-RestMethod "$($url)health"

# smoke the four dashboard endpoints (each backs a tab)
"decisions","gaps","models","audit-packs" | % { "$_ = " + (Invoke-RestMethod "$($url)dashboard/$_" -Headers $H).Count }

# evaluate a ledger decision
Invoke-RestMethod -Method POST "$($url)evidence/evaluate" -Headers ($H + @{ "content-type"="application/json" }) -Body '{"event_id":"<ledger event_id>"}'

# readiness + audit pack
Invoke-RestMethod "$($url)evidence/readiness/<decision_id>" -Headers $H
Invoke-RestMethod -Method POST "$($url)audit-pack" -Headers ($H + @{ "content-type"="application/json" }) -Body '{"scope":"per_decision","decision_id":"<decision_id>"}'
```

---

## Observability

```powershell
# tail recent logs
aws logs tail "/aws/lambda/$fn" --region $region --since 15m --follow

# Lambda error count (last hour)
aws cloudwatch get-metric-statistics --region $region --namespace AWS/Lambda `
  --metric-name Errors --dimensions Name=FunctionName,Value=$fn `
  --start-time (Get-Date).AddHours(-1).ToString("o") --end-time (Get-Date).ToString("o") `
  --period 3600 --statistics Sum
```
Log group retention is 1 week. The Hub also writes its own audit-log items into
DynamoDB (every evaluate / update / pack / access).

---

## Data store

```powershell
# item count
aws dynamodb scan --region $region --table-name $table --select COUNT

# all items for one decision (append-only history)
aws dynamodb query --region $region --table-name $table `
  --key-condition-expression "pk = :p" `
  --expression-attribute-values "{\":p\":{\"S\":\"DEC#<decision_id>\"}}"
```
The table is **append-only** and **RETAIN** with **PITR** on — a `cdk destroy`
will *not* delete it, and you can restore to any point in the last 35 days.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `401` on every data call | admin key missing/wrong, or stale cache | check `x-api-key`; re-run the reload step after a secret change |
| `404` "no evaluation for decision" | decision not evaluated yet | `POST /evidence/evaluate` first |
| `404`/`502` on evaluate | bad/empty `AUDIT_API_URL`, or ledger read key wrong | check env var; verify the ledger read key in the secret |
| dashboard loads but tables empty / errors | browser has no/!wrong key | click 🔑, re-enter key (wrong key self-re-prompts) |
| `docker ... daemon` error at deploy | Docker Desktop not running | start it, wait for `docker info`, redeploy |
| ledger cross-link 404 | ledger dashboard not redeployed | redeploy the ledger stack |
| changes not visible after deploy | CloudFront/browser cache | hard-refresh; CloudFront invalidates automatically on ledger deploy |

---

## Dashboard cross-link maintenance

The Hub links to the ledger dashboard via `EVIDENCE_LEDGER_DASHBOARD_URL`
(config). The **ledger** dashboard links back to the Hub via a **hard-coded
Function URL** in `ai-audit-ledger/dashboard/index.html` (two spots, marked with
a comment). The Function URL is stable unless the Lambda is recreated — if it
ever changes, update both spots and redeploy the ledger stack.

---

## Cost

Lambda (scale-to-zero) + DynamoDB on-demand + a Function URL ≈ **$0 when idle**;
you pay per request and per item. No VPC/NAT/RDS. The single Secrets Manager
secret is the only fixed cost (cents/month).

---

## Teardown

```powershell
cd "C:\Users\AI Data Logger\evidence-hub\infra\cdk"
npx cdk destroy
```
The DynamoDB table and the secret are **RETAIN** — they survive teardown by
design (evidence + keys are not thrown away). Delete them manually only if you
are sure.

---

## Security notes

- Function URL auth is `NONE`; access is gated by the in-app admin `x-api-key`.
  Treat the admin key like a password; rotate on staff changes.
- The Hub is **read-only** on the ledger and stores no PII (hashes/references
  only). Its own data is append-only.
- IAM is least-privilege: the Lambda can read/write only its table and read only
  its secret — no access to the ledger's AWS resources.
