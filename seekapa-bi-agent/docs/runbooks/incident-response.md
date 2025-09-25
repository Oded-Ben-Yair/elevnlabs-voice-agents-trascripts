# Incident Response Runbook

## Overview
This runbook provides step-by-step instructions for responding to production incidents in the Seekapa BI Agent system.

## Incident Severity Levels

### SEV-1 (Critical)
- **Definition**: Complete service outage or data loss
- **Response Time**: Immediate (< 5 minutes)
- **Escalation**: Page on-call engineer immediately via PagerDuty
- **Examples**:
  - Complete API unavailability
  - Database corruption
  - Security breach

### SEV-2 (High)
- **Definition**: Major feature unavailable or significant degradation
- **Response Time**: < 15 minutes
- **Escalation**: Alert on-call engineer
- **Examples**:
  - Authentication service down
  - Query execution failures > 50%
  - Payment processing errors

### SEV-3 (Medium)
- **Definition**: Minor feature degradation
- **Response Time**: < 1 hour
- **Escalation**: Notify team via Slack
- **Examples**:
  - Slow query performance
  - Non-critical service degradation
  - UI rendering issues

### SEV-4 (Low)
- **Definition**: Minor issues with workarounds
- **Response Time**: Next business day
- **Escalation**: Create ticket in tracking system

## Initial Response Checklist

### 1. Acknowledge Incident
```bash
# PagerDuty CLI
pd incident acknowledge -i INCIDENT_ID

# Or via API
curl -X PUT https://api.pagerduty.com/incidents/INCIDENT_ID \
  -H 'Authorization: Token token=YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"incident": {"type": "incident_reference", "status": "acknowledged"}}'
```

### 2. Create Incident Channel
```bash
# Create Slack channel
/incident create sev-X-YYYYMMDD-description

# Set topic
/topic Incident: [Brief Description] | Status: Investigating | Lead: @username
```

### 3. Initial Assessment (5-10 minutes)

#### Check System Status
```bash
# Check Kubernetes pods
kubectl get pods -A | grep -v Running

# Check recent deployments
kubectl get deployments -A -o wide

# Check service health
curl https://api.seekapa.com/health
curl https://app.seekapa.com/health

# Check Azure status
az monitor metrics list \
  --resource /subscriptions/XXX/resourceGroups/seekapa-rg/providers/Microsoft.ContainerService/managedClusters/seekapa-aks-prod \
  --metric "node_cpu_usage_percentage" \
  --interval PT1M
```

#### Review Monitoring Dashboards
1. Open Grafana: https://grafana.seekapa.com
   - Check API Performance dashboard
   - Check System Metrics dashboard
   - Check Database Performance dashboard

2. Open Application Insights:
   ```bash
   az monitor app-insights metrics show \
     --app seekapa-bi-insights \
     --resource-group seekapa-rg \
     --metric requests/failed \
     --interval PT5M
   ```

#### Check Recent Changes
```bash
# Check recent commits
git log --oneline -10

# Check ArgoCD sync status
argocd app get seekapa-bi-agent

# Check recent GitHub Actions runs
gh run list --limit 5
```

## Common Issues and Resolutions

### Issue: High API Latency

#### Diagnosis
```bash
# Check pod resources
kubectl top pods -n seekapa-production

# Check database connections
kubectl exec -it postgres-0 -- psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"

# Check Redis performance
kubectl exec -it redis-master-0 -- redis-cli INFO stats
```

#### Resolution
```bash
# Scale API pods
kubectl scale deployment backend-deployment --replicas=10 -n seekapa-production

# Clear Redis cache if needed
kubectl exec -it redis-master-0 -- redis-cli FLUSHDB

# Restart slow pods
kubectl delete pod POD_NAME -n seekapa-production
```

### Issue: Database Connection Errors

#### Diagnosis
```bash
# Check PostgreSQL status
kubectl get pod -n seekapa-production -l app=postgresql

# Check connection pool
kubectl logs -n seekapa-production deployment/backend-deployment | grep "connection"

# Test database connectivity
kubectl run -it --rm debug --image=postgres:15 --restart=Never -- psql -h postgres-service -U postgres
```

#### Resolution
```bash
# Restart connection pool
kubectl rollout restart deployment/backend-deployment -n seekapa-production

# Increase connection limits (temporary)
kubectl exec -it postgres-0 -- psql -U postgres -c "ALTER SYSTEM SET max_connections = 500;"
kubectl exec -it postgres-0 -- psql -U postgres -c "SELECT pg_reload_conf();"

# Scale database read replicas
kubectl scale statefulset postgres-read --replicas=3 -n seekapa-production
```

### Issue: Memory Leak / OOM Kills

#### Diagnosis
```bash
# Check for OOM kills
kubectl get events -A | grep OOM

# Check memory usage
kubectl top pods -n seekapa-production --sort-by=memory

# Get pod restart history
kubectl get pods -n seekapa-production -o custom-columns=NAME:.metadata.name,RESTARTS:.status.containerStatuses[0].restartCount
```

#### Resolution
```bash
# Increase memory limits (temporary)
kubectl set resources deployment/backend-deployment -c backend --limits=memory=4Gi -n seekapa-production

# Rolling restart to clear memory
kubectl rollout restart deployment/backend-deployment -n seekapa-production

# Enable memory profiling
kubectl set env deployment/backend-deployment PYTHONTRACEMALLOC=1 -n seekapa-production
```

### Issue: 5XX Error Spike

#### Diagnosis
```bash
# Check error logs
kubectl logs -n seekapa-production -l app=backend --tail=100 | grep ERROR

# Check specific error patterns
kubectl logs -n seekapa-production deployment/backend-deployment | grep -E "500|502|503|504"

# Query Prometheus for error rate
curl -G http://prometheus:9090/api/v1/query \
  --data-urlencode 'query=rate(http_requests_total{status=~"5.."}[5m])'
```

#### Resolution
```bash
# Rollback to previous version
kubectl rollout undo deployment/backend-deployment -n seekapa-production

# Or use ArgoCD
argocd app rollback seekapa-bi-agent REVISION

# Enable circuit breaker
kubectl patch deployment backend-deployment -n seekapa-production \
  -p '{"spec":{"template":{"spec":{"containers":[{"name":"backend","env":[{"name":"CIRCUIT_BREAKER_ENABLED","value":"true"}]}]}}}}'
```

### Issue: Data Pipeline Failure

#### Diagnosis
```bash
# Check Airflow DAGs
kubectl exec -it airflow-webserver-0 -- airflow dags list-runs -d data_pipeline

# Check recent job status
kubectl get jobs -n seekapa-production | grep data-

# Check data quality metrics
curl http://prometheus:9090/api/v1/query?query=data_quality_score
```

#### Resolution
```bash
# Retry failed pipeline
kubectl exec -it airflow-webserver-0 -- airflow dags trigger data_pipeline

# Clear failed tasks
kubectl exec -it airflow-webserver-0 -- airflow tasks clear data_pipeline -s START_DATE -e END_DATE

# Manual data recovery
kubectl exec -it postgres-0 -- psql -U postgres -d seekapa -f /backups/recovery.sql
```

## Rollback Procedures

### Application Rollback

#### Via Kubernetes
```bash
# Check rollout history
kubectl rollout history deployment/backend-deployment -n seekapa-production

# Rollback to previous version
kubectl rollout undo deployment/backend-deployment -n seekapa-production

# Rollback to specific revision
kubectl rollout undo deployment/backend-deployment --to-revision=42 -n seekapa-production

# Monitor rollback
kubectl rollout status deployment/backend-deployment -n seekapa-production
```

#### Via ArgoCD
```bash
# List revisions
argocd app history seekapa-bi-agent

# Rollback to specific revision
argocd app rollback seekapa-bi-agent REVISION

# Sync and wait
argocd app sync seekapa-bi-agent --prune
argocd app wait seekapa-bi-agent --health
```

#### Via GitHub Actions
```bash
# Re-run previous successful deployment
gh run rerun RUN_ID

# Deploy specific tag
gh workflow run cd.yml -f environment=production -f tag=v1.2.3
```

### Database Rollback

#### Point-in-time Recovery
```bash
# Azure Database for PostgreSQL
az postgres server restore \
  --resource-group seekapa-rg \
  --name seekapa-postgres-restored \
  --source-server seekapa-postgres \
  --restore-point-in-time "2024-01-15T13:30:00Z"

# Update connection strings
kubectl set env deployment/backend-deployment \
  DATABASE_URL=postgresql://user:pass@seekapa-postgres-restored:5432/seekapa \
  -n seekapa-production
```

## Communication Templates

### Initial Incident Notification
```
🚨 INCIDENT DECLARED - SEV-[X]
Time: [Timestamp]
Service: [Affected Service]
Impact: [User Impact Description]
Status: Investigating
Lead: @[Username]
Channel: #incident-[date]-[description]

Current Status:
- [Symptom 1]
- [Symptom 2]

Next Steps:
- [Action 1]
- [Action 2]
```

### Status Update Template
```
📊 INCIDENT UPDATE - [Time since start]
Status: [Investigating/Identified/Monitoring/Resolved]

What we know:
- [Finding 1]
- [Finding 2]

What we've done:
- [Action taken 1]
- [Action taken 2]

Next steps:
- [Planned action 1]
- [Planned action 2]

ETA: [Estimate or "Updates in 15 minutes"]
```

### Resolution Notification
```
✅ INCIDENT RESOLVED
Duration: [Total time]
Root Cause: [Brief description]
Resolution: [What fixed it]

Impact Summary:
- Affected Users: [Number/Percentage]
- Downtime: [Duration]
- Data Loss: [None/Description]

Follow-up Actions:
- [ ] Post-mortem scheduled for [Date/Time]
- [ ] Action items documented
- [ ] Monitoring enhanced

Thank you to everyone who helped resolve this incident.
```

## Post-Incident Activities

### 1. Immediate (Within 1 hour)
- [ ] Verify system stability
- [ ] Document timeline in incident tracker
- [ ] Send resolution notification
- [ ] Archive Slack channel

### 2. Short-term (Within 24 hours)
- [ ] Create post-mortem document
- [ ] Gather metrics and logs
- [ ] Schedule post-mortem meeting
- [ ] Update status page

### 3. Long-term (Within 1 week)
- [ ] Conduct blameless post-mortem
- [ ] Create action items and assign owners
- [ ] Update runbooks based on learnings
- [ ] Share learnings with team

## Escalation Contacts

### On-Call Rotation
Check PagerDuty: https://seekapa.pagerduty.com/schedules

### Escalation Path
1. Primary On-Call Engineer
2. Secondary On-Call Engineer
3. Team Lead
4. Engineering Manager
5. CTO

### External Vendors
- **Azure Support**: 1-800-AZURE-HELP
- **Datadog Support**: support@datadoghq.com
- **PagerDuty Support**: support@pagerduty.com

## Useful Commands Reference

### Kubernetes
```bash
# Get all resources
kubectl get all -A

# Describe problematic pod
kubectl describe pod POD_NAME -n NAMESPACE

# Get pod logs
kubectl logs -f POD_NAME -n NAMESPACE --tail=100

# Execute command in pod
kubectl exec -it POD_NAME -n NAMESPACE -- /bin/bash

# Port forward for debugging
kubectl port-forward POD_NAME 8080:8080 -n NAMESPACE
```

### Docker
```bash
# Check container resource usage
docker stats

# Inspect container
docker inspect CONTAINER_ID

# Clean up resources
docker system prune -a
```

### Azure CLI
```bash
# Check AKS cluster status
az aks show -n seekapa-aks-prod -g seekapa-rg

# Get AKS credentials
az aks get-credentials -n seekapa-aks-prod -g seekapa-rg

# Check Azure service health
az monitor activity-log list --resource-group seekapa-rg --start-time 1h
```

### Database
```bash
# PostgreSQL connections
SELECT pid, usename, application_name, client_addr, state
FROM pg_stat_activity
WHERE state != 'idle';

# Kill long-running queries
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state != 'idle'
AND query_start < now() - interval '10 minutes';

# Table sizes
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 10;
```

### Performance Analysis
```bash
# CPU flame graph
kubectl exec POD_NAME -- py-spy record -d 30 -f flame.svg

# Memory profiling
kubectl exec POD_NAME -- python -m memory_profiler app.py

# Network analysis
kubectl exec POD_NAME -- tcpdump -i any -w capture.pcap
```

## Review and Updates
This runbook should be reviewed and updated:
- After every SEV-1 or SEV-2 incident
- Quarterly by the on-call team
- When new services or dependencies are added

Last Updated: 2024-01-15
Next Review: 2024-04-15
Owner: DevOps Team