# Evidence Hub as a Lambda container image.
# The AWS Lambda Web Adapter lets the unmodified FastAPI app run in Lambda: it
# proxies the Function URL / API Gateway event to a local HTTP server on :8080.
FROM public.ecr.aws/docker/library/python:3.12-slim

COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.8.4 /lambda-adapter /opt/extensions/lambda-adapter

ENV PORT=8080 \
    AWS_LWA_PORT=8080 \
    EVIDENCE_STORE=dynamodb \
    LEDGER_SOURCE=live \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[aws]"

# Adapter forwards to this; the app serves the API and the /ui/ dashboard.
CMD ["python", "-m", "uvicorn", "evidence_hub.api:app", "--host", "0.0.0.0", "--port", "8080"]
