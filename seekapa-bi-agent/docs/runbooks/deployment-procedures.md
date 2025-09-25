# Deployment Procedures Runbook

## Overview
This runbook provides detailed procedures for deploying the Seekapa BI Agent to various environments.

## Pre-Deployment Checklist

### Code Review and Testing
- [ ] All code changes reviewed and approved
- [ ] Unit tests passing (coverage > 80%)
- [ ] Integration tests passing
- [ ] Performance tests show no regression
- [ ] Security scan completed with no critical issues
- [ ] Documentation updated

### Communication
- [ ] Deployment window scheduled
- [ ] Stakeholders notified
- [ ] Maintenance window created in PagerDuty
- [ ] Status page updated (if customer-facing)

### Backup and Rollback Preparation
- [ ] Database backup completed
- [ ] Current version tagged in Git
- [ ] Rollback procedure verified
- [ ] Previous version artifacts available

## Deployment Environments

### Development Environment
- **Purpose**: Feature development and testing
- **Deployment**: Automatic on feature branch push
- **Approval**: None required
- **Rollback**: Automatic on test failure

### Staging Environment
- **Purpose**: Pre-production validation
- **Deployment**: Automatic on merge to develop branch
- **Approval**: None required
- **Rollback**: Manual via ArgoCD

### Production Environment
- **Purpose**: Live customer environment
- **Deployment**: Manual trigger with approval
- **Approval**: Team lead or manager
- **Rollback**: Automated blue-green switch

## Standard Deployment Process

### Step 1: Pre-deployment Validation

```bash
# Verify CI/CD pipeline status
gh run list --workflow=ci.yml --limit=1
gh run view RUN_ID

# Check current production version
kubectl get deployment -n seekapa-production -o wide

# Verify staging deployment success
argocd app get seekapa-bi-agent-staging

# Check system health
curl https://api.seekapa.com/health
curl https://api-staging.seekapa.com/health

# Review metrics for anomalies
grafana-cli dashboard export api-performance --timerange=1h
```

### Step 2: Create Deployment Tag

```bash
# Create release tag
VERSION="v$(date +%Y.%m.%d)-$(git rev-parse --short HEAD)"
git tag -a $VERSION -m "Release $VERSION

Changes:
- Feature: [Description]
- Fix: [Description]
- Performance: [Description]"

git push origin $VERSION

# Create GitHub release
gh release create $VERSION \
  --title "Release $VERSION" \
  --notes-file RELEASE_NOTES.md \
  --target main
```

### Step 3: Deploy to Production

#### Option A: GitHub Actions Deployment
```bash
# Trigger production deployment
gh workflow run cd.yml \
  -f environment=production \
  -f version=$VERSION

# Monitor deployment
gh run watch

# View logs if needed
gh run view --log
```

#### Option B: ArgoCD Deployment
```bash
# Update production application
argocd app set seekapa-bi-agent \
  --revision $VERSION

# Sync application
argocd app sync seekapa-bi-agent \
  --prune \
  --strategy=bluegreen

# Wait for health
argocd app wait seekapa-bi-agent \
  --health \
  --timeout=600
```

#### Option C: Kubectl Deployment
```bash
# Update image tags
kubectl set image deployment/backend-deployment \
  backend=ghcr.io/seekapa/seekapa-bi-agent-backend:$VERSION \
  -n seekapa-production

kubectl set image deployment/frontend-deployment \
  frontend=ghcr.io/seekapa/seekapa-bi-agent-frontend:$VERSION \
  -n seekapa-production

# Monitor rollout
kubectl rollout status deployment/backend-deployment -n seekapa-production
kubectl rollout status deployment/frontend-deployment -n seekapa-production
```

### Step 4: Blue-Green Deployment Switch

```bash
# Deploy to green environment
kubectl apply -f k8s/production/green-deployment.yaml

# Update green deployment with new version
kubectl set image deployment/backend-deployment-green \
  backend=ghcr.io/seekapa/seekapa-bi-agent-backend:$VERSION \
  -n seekapa-production

# Wait for green to be ready
kubectl wait --for=condition=available \
  deployment/backend-deployment-green \
  -n seekapa-production \
  --timeout=300s

# Run smoke tests on green
./scripts/smoke-test.sh green

# Switch traffic to green
kubectl patch service backend-service \
  -n seekapa-production \
  -p '{"spec":{"selector":{"version":"green"}}}'

# Verify traffic switch
kubectl get endpoints backend-service -n seekapa-production

# Keep blue as backup
kubectl label deployment backend-deployment-blue \
  version=blue-backup \
  -n seekapa-production \
  --overwrite
```

### Step 5: Post-deployment Validation

```bash
# Health checks
./scripts/health-check.sh production

# Smoke tests
npm run test:smoke:prod

# Performance validation
k6 run tests/performance/production-load.js

# Check error rates
curl -G http://prometheus:9090/api/v1/query \
  --data-urlencode 'query=rate(http_requests_total{status=~"5.."}[5m])'

# Verify feature flags
curl https://api.seekapa.com/admin/feature-flags

# Check database migrations
kubectl exec -it postgres-0 -- \
  psql -U postgres -d seekapa -c "SELECT * FROM schema_migrations ORDER BY version DESC LIMIT 5;"
```

## Canary Deployment Process

### Step 1: Deploy Canary Version
```bash
# Create canary deployment
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend-deployment-canary
  namespace: seekapa-production
spec:
  replicas: 1
  selector:
    matchLabels:
      app: backend
      version: canary
  template:
    metadata:
      labels:
        app: backend
        version: canary
    spec:
      containers:
      - name: backend
        image: ghcr.io/seekapa/seekapa-bi-agent-backend:$VERSION
        env:
        - name: VERSION
          value: canary
EOF

# Configure traffic split (10% to canary)
kubectl apply -f - <<EOF
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: backend-vs
  namespace: seekapa-production
spec:
  http:
  - match:
    - headers:
        canary:
          exact: "true"
    route:
    - destination:
        host: backend-service
        subset: canary
      weight: 100
  - route:
    - destination:
        host: backend-service
        subset: stable
      weight: 90
    - destination:
        host: backend-service
        subset: canary
      weight: 10
EOF
```

### Step 2: Monitor Canary Metrics
```bash
# Compare canary vs stable metrics
./scripts/canary-analysis.sh

# Watch error rates
watch -n 5 'kubectl logs -l version=canary -n seekapa-production --tail=20 | grep ERROR'

# Check response times
curl -G http://prometheus:9090/api/v1/query \
  --data-urlencode 'query=histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{version="canary"}[5m]))'
```

### Step 3: Progressive Rollout
```bash
# Increase canary traffic to 25%
kubectl patch virtualservice backend-vs \
  -n seekapa-production \
  --type='json' \
  -p='[{"op": "replace", "path": "/spec/http/1/route/0/weight", "value":75},
       {"op": "replace", "path": "/spec/http/1/route/1/weight", "value":25}]'

# Wait and monitor
sleep 300
./scripts/canary-analysis.sh

# Increase to 50%
kubectl patch virtualservice backend-vs \
  -n seekapa-production \
  --type='json' \
  -p='[{"op": "replace", "path": "/spec/http/1/route/0/weight", "value":50},
       {"op": "replace", "path": "/spec/http/1/route/1/weight", "value":50}]'

# Final validation before full rollout
./scripts/canary-validation.sh
```

### Step 4: Complete Canary Rollout
```bash
# Promote canary to stable
kubectl set image deployment/backend-deployment \
  backend=ghcr.io/seekapa/seekapa-bi-agent-backend:$VERSION \
  -n seekapa-production

# Remove canary deployment
kubectl delete deployment backend-deployment-canary -n seekapa-production

# Reset traffic rules
kubectl delete virtualservice backend-vs -n seekapa-production
```

## Database Migration Procedures

### Pre-Migration Checks
```bash
# Backup current database
kubectl exec -it postgres-0 -- \
  pg_dump -U postgres -d seekapa -f /backup/seekapa_$(date +%Y%m%d_%H%M%S).sql

# Check migration status
kubectl exec -it backend-deployment-xxxx -- \
  alembic current

# Review pending migrations
kubectl exec -it backend-deployment-xxxx -- \
  alembic history --verbose
```

### Running Migrations
```bash
# Run migrations in staging first
kubectl exec -it backend-deployment-xxxx -n seekapa-staging -- \
  alembic upgrade head

# Verify migration success
kubectl exec -it postgres-staging-0 -- \
  psql -U postgres -d seekapa -c "\dt"

# Run production migrations
kubectl create job --from=cronjob/db-migration-job db-migration-$(date +%s) \
  -n seekapa-production

# Monitor migration job
kubectl logs -f job/db-migration-xxxxx -n seekapa-production
```

### Migration Rollback
```bash
# Rollback last migration
kubectl exec -it backend-deployment-xxxx -- \
  alembic downgrade -1

# Rollback to specific revision
kubectl exec -it backend-deployment-xxxx -- \
  alembic downgrade REVISION_ID

# Restore from backup if needed
kubectl exec -it postgres-0 -- \
  psql -U postgres -d seekapa -f /backup/seekapa_backup.sql
```

## Emergency Deployment Procedures

### Hotfix Deployment
```bash
# Create hotfix branch
git checkout -b hotfix/critical-fix main

# Make and commit fix
# ... make changes ...
git commit -am "Hotfix: Critical issue description"

# Create hotfix tag
HOTFIX_VERSION="v$(date +%Y.%m.%d)-hotfix-$(git rev-parse --short HEAD)"
git tag -a $HOTFIX_VERSION -m "Hotfix: $HOTFIX_VERSION"

# Push changes
git push origin hotfix/critical-fix
git push origin $HOTFIX_VERSION

# Fast-track deployment
gh workflow run cd.yml \
  -f environment=production \
  -f version=$HOTFIX_VERSION \
  -f skip_tests=true

# Monitor deployment
watch -n 5 'kubectl rollout status deployment/backend-deployment -n seekapa-production'
```

### Emergency Rollback
```bash
# Immediate rollback to previous version
kubectl rollout undo deployment/backend-deployment -n seekapa-production
kubectl rollout undo deployment/frontend-deployment -n seekapa-production

# Or switch blue-green immediately
kubectl patch service backend-service \
  -n seekapa-production \
  -p '{"spec":{"selector":{"version":"blue"}}}'

# Verify rollback
kubectl get pods -n seekapa-production -o wide
curl https://api.seekapa.com/version
```

## Configuration Management

### Environment Variables Update
```bash
# Update single environment variable
kubectl set env deployment/backend-deployment \
  NEW_VAR=value \
  -n seekapa-production

# Update from config map
kubectl create configmap app-config \
  --from-file=config.json \
  -n seekapa-production

kubectl set env deployment/backend-deployment \
  --from=configmap/app-config \
  -n seekapa-production
```

### Secret Rotation
```bash
# Create new secret
kubectl create secret generic app-secrets \
  --from-literal=api-key=NEW_KEY \
  --from-literal=db-password=NEW_PASSWORD \
  -n seekapa-production \
  --dry-run=client -o yaml | kubectl apply -f -

# Trigger rolling update
kubectl rollout restart deployment/backend-deployment -n seekapa-production

# Verify secret usage
kubectl describe deployment backend-deployment -n seekapa-production | grep -A5 "Environment Variables from:"
```

### Feature Flag Updates
```bash
# Enable feature flag
curl -X PUT https://api.seekapa.com/admin/feature-flags/new-feature \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "rollout_percentage": 10}'

# Check feature flag status
curl https://api.seekapa.com/admin/feature-flags

# Gradual rollout
for percentage in 25 50 75 100; do
  curl -X PATCH https://api.seekapa.com/admin/feature-flags/new-feature \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -d "{\"rollout_percentage\": $percentage}"
  sleep 300
  ./scripts/monitor-feature.sh new-feature
done
```

## Monitoring During Deployment

### Key Metrics to Watch
```bash
# Real-time error rate
watch -n 2 'curl -s http://prometheus:9090/api/v1/query?query=rate(http_requests_total{status=~"5.."}[1m]) | jq .data.result[].value[1]'

# Response time percentiles
watch -n 5 'curl -s http://prometheus:9090/api/v1/query?query=histogram_quantile(0.95,rate(http_request_duration_seconds_bucket[1m])) | jq .data.result[].value[1]'

# Active connections
watch -n 2 'kubectl exec -it backend-deployment-xxxx -- ss -s'

# CPU and Memory
watch -n 5 'kubectl top pods -n seekapa-production'
```

### Dashboards to Monitor
1. **Grafana Dashboards**
   - API Performance: https://grafana.seekapa.com/d/api-performance
   - System Metrics: https://grafana.seekapa.com/d/system-metrics
   - Deployment Progress: https://grafana.seekapa.com/d/deployment

2. **Azure Monitor**
   - Application Insights: https://portal.azure.com/#blade/AppInsights
   - AKS Metrics: https://portal.azure.com/#blade/AKSMetrics

3. **ArgoCD**
   - Application Status: https://argocd.seekapa.com/applications

## Post-Deployment Tasks

### Verification
- [ ] All health checks passing
- [ ] No increase in error rates
- [ ] Response times within SLA
- [ ] All feature flags working
- [ ] Database migrations completed
- [ ] Background jobs running

### Documentation
- [ ] Update release notes
- [ ] Document any issues encountered
- [ ] Update runbooks if needed
- [ ] Record metrics baseline

### Cleanup
- [ ] Remove old deployments
- [ ] Clean up unused images
- [ ] Archive logs
- [ ] Close deployment ticket

## Troubleshooting Common Issues

### Issue: Deployment Stuck in Progress
```bash
# Check rollout status
kubectl rollout status deployment/backend-deployment -n seekapa-production

# Check pod events
kubectl describe pods -l app=backend -n seekapa-production

# Force progress
kubectl rollout restart deployment/backend-deployment -n seekapa-production
```

### Issue: Health Checks Failing
```bash
# Check health endpoint directly
kubectl exec -it backend-deployment-xxxx -- curl localhost:8000/health

# Check readiness probe
kubectl get pods -n seekapa-production -o json | jq '.items[].status.conditions'

# Temporarily disable health checks
kubectl patch deployment backend-deployment -n seekapa-production \
  -p '{"spec":{"template":{"spec":{"containers":[{"name":"backend","livenessProbe":null}]}}}}'
```

### Issue: Image Pull Errors
```bash
# Check image availability
docker pull ghcr.io/seekapa/seekapa-bi-agent-backend:$VERSION

# Check registry credentials
kubectl get secret regcred -n seekapa-production -o yaml

# Update registry credentials
kubectl create secret docker-registry regcred \
  --docker-server=ghcr.io \
  --docker-username=$GITHUB_USER \
  --docker-password=$GITHUB_TOKEN \
  -n seekapa-production \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Approval Matrix

| Environment | Deployment Type | Approver Required | Rollback Authority |
|------------|----------------|-------------------|-------------------|
| Development | Feature Branch | None | Developer |
| Staging | Develop Branch | None | Developer |
| Production | Standard | Team Lead | On-call Engineer |
| Production | Hotfix | Engineering Manager | On-call Engineer |
| Production | Emergency | CTO/VP Engineering | Incident Commander |

## References and Resources

- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Azure AKS Best Practices](https://docs.microsoft.com/en-us/azure/aks/best-practices)
- [ArgoCD User Guide](https://argo-cd.readthedocs.io/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Prometheus Querying](https://prometheus.io/docs/prometheus/latest/querying/)

## Review Schedule
This runbook is reviewed:
- Monthly by the DevOps team
- After major deployment issues
- When deployment process changes

Last Updated: 2024-01-15
Next Review: 2024-02-15
Owner: DevOps Team