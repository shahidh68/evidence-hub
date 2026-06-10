#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { EvidenceHubStack } from '../lib/evidence-hub-stack';

const app = new cdk.App();

new EvidenceHubStack(app, 'EvidenceHubStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION ?? 'eu-west-1',
  },
  description: 'AI Decision Evidence Hub — Lambda (Web Adapter) + DynamoDB, single internal deployment',
});

app.synth();
