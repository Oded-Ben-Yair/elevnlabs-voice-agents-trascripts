# Seekapa BI Agent - Infrastructure Deployment Guide

This guide covers the deployment of the Seekapa BI Agent using Docker Compose and Kubernetes with comprehensive infrastructure components.

## 🏗️ Architecture Overview

The Seekapa BI Agent is built with a microservices architecture supporting:

- **Backend**: FastAPI with Python 3.11, multi-stage Docker builds
- **Frontend**: React with TypeScript, Nginx production serving
- **Database**: PostgreSQL 16 with optimized configuration
- **Cache**: Redis 7 with persistence and clustering support
- **Monitoring**: Prometheus + Grafana stack
- **Security**: OAuth 2.1, RBAC, network policies, security headers
- **Scaling**: Horizontal Pod Autoscaling (HPA) and load balancing

## 📋 Prerequisites

### Docker Deployment
- Docker Engine 20.10+
- Docker Compose 2.0+
- 8GB RAM minimum
- 50GB disk space

### Kubernetes Deployment
- Kubernetes cluster 1.25+
- kubectl configured
- Helm 3.0+ (optional)
- cert-manager for SSL certificates
- Ingress controller (nginx recommended)

## 🚀 Quick Start

### Docker Compose Deployment

1. **Clone and Setup**
   ```bash
   git checkout feature/infrastructure-docker
   cd seekapa-bi-agent
   ```

2. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Deploy Development Environment**
   ```bash
   ./scripts/deploy-docker.sh deploy dev
   ```

4. **Deploy Production Environment**
   ```bash
   ./scripts/deploy-docker.sh deploy prod
   ```

### Kubernetes Deployment

1. **Deploy Full Stack**
   ```bash
   ./scripts/deploy-k8s.sh deploy --with-monitoring
   ```

2. **Check Status**
   ```bash
   ./scripts/deploy-k8s.sh status
   ```

## 🐳 Docker Compose Configurations

### Available Compose Files

| File | Purpose | Use Case |
|------|---------|----------|
| `docker-compose.yml` | Main production setup | Default production deployment |
| `docker-compose.dev.yml` | Development environment | Local development with hot reload |
| `docker-compose.prod.yml` | Production with scaling | Production with auto-scaling, monitoring |

### Development Environment Features

- Hot reload for both frontend and backend
- Development tools (Redis Commander, PgAdmin)
- Mailhog for email testing
- Volume mounts for live code editing
- Debug logging enabled

```bash
# Start development environment
./scripts/deploy-docker.sh deploy dev

# View logs
./scripts/deploy-docker.sh logs backend

# Access development tools
echo "Frontend: http://localhost:3000"
echo "Backend API: http://localhost:8000"
echo "API Docs: http://localhost:8000/docs"
echo "Redis Commander: http://localhost:8081"
echo "PgAdmin: http://localhost:8082"
```

### Production Environment Features

- Multi-replica backend services
- SSL termination with nginx
- Automated backups
- Resource limits and health checks
- Log aggregation with Fluentd
- Monitoring with Prometheus/Grafana

```bash
# Deploy production environment
./scripts/deploy-docker.sh deploy prod

# Scale services
docker-compose -f docker-compose.prod.yml up -d --scale backend=5

# View production status
./scripts/deploy-docker.sh status
```

## ☸️ Kubernetes Deployment

### Namespace Structure

```
seekapa/                    # Main application namespace
├── seekapa-backend         # API pods (3 replicas)
├── seekapa-frontend        # Frontend pods (2 replicas)
├── seekapa-postgres        # Database pod
└── seekapa-redis          # Cache pod

seekapa-monitoring/         # Monitoring namespace
├── prometheus             # Metrics collection
├── grafana               # Visualization
└── node-exporter         # System metrics
```

### Deployment Components

#### Core Services
- **Deployments**: Multi-replica application pods
- **Services**: Internal service discovery
- **Ingress**: External traffic routing with SSL
- **ConfigMaps**: Non-sensitive configuration
- **Secrets**: Sensitive data (encrypted at rest)
- **PVCs**: Persistent storage for database and cache

#### Security Features
- **RBAC**: Role-based access control
- **NetworkPolicies**: Pod-to-pod traffic rules
- **SecurityContext**: Container security constraints
- **Secrets Management**: Encrypted secret storage

#### Scaling & Reliability
- **HPA**: Horizontal Pod Autoscaling (CPU/Memory)
- **PodDisruptionBudgets**: Maintain availability during updates
- **Health Checks**: Liveness and readiness probes
- **Rolling Updates**: Zero-downtime deployments

### Deployment Steps

1. **Create Namespaces and RBAC**
   ```bash
   kubectl apply -f k8s/namespace.yaml
   ```

2. **Deploy Configuration**
   ```bash
   kubectl apply -f k8s/configmap.yaml
   kubectl apply -f k8s/secret.yaml
   ```

3. **Deploy Storage**
   ```bash
   kubectl apply -f k8s/pvc.yaml
   ```

4. **Deploy Applications**
   ```bash
   kubectl apply -f k8s/deployment.yaml
   kubectl apply -f k8s/service.yaml
   kubectl apply -f k8s/ingress.yaml
   ```

5. **Deploy Monitoring**
   ```bash
   kubectl apply -f k8s/monitoring.yaml
   ```

### Scaling Operations

```bash
# Manual scaling
kubectl scale deployment/seekapa-backend --replicas=5 -n seekapa

# Auto-scaling (HPA already configured)
kubectl get hpa -n seekapa

# Monitor scaling events
kubectl describe hpa seekapa-backend-hpa -n seekapa
```

## 🔧 Configuration Management

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key | Yes | - |
| `AZURE_AI_SERVICES_ENDPOINT` | Azure AI endpoint | Yes | - |
| `POWERBI_*` | Power BI configuration | Yes | - |
| `POSTGRES_PASSWORD` | Database password | Yes | - |
| `REDIS_PASSWORD` | Redis password | No | redis123 |
| `JWT_SECRET_KEY` | JWT signing key | Yes | - |

### Security Configuration

1. **Update Default Passwords**
   ```bash
   # Generate secure passwords
   openssl rand -base64 32  # For JWT_SECRET_KEY
   openssl rand -base64 24  # For POSTGRES_PASSWORD
   openssl rand -base64 24  # For REDIS_PASSWORD
   ```

2. **Configure SSL Certificates**
   ```bash
   # For Kubernetes (using cert-manager)
   kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.12.0/cert-manager.yaml

   # For Docker (place certificates in ssl/ directory)
   mkdir ssl
   # Add your SSL certificates: ssl/cert.pem, ssl/key.pem
   ```

## 📊 Monitoring & Observability

### Metrics Collection

- **Application Metrics**: Custom FastAPI metrics
- **System Metrics**: Node exporter for system stats
- **Database Metrics**: PostgreSQL exporter
- **Cache Metrics**: Redis exporter

### Access Monitoring Tools

#### Docker Compose
```bash
echo "Grafana: http://localhost:3001 (admin/admin123)"
echo "Prometheus: http://localhost:9090"
```

#### Kubernetes
```bash
# Port forward to access services
kubectl port-forward -n seekapa-monitoring svc/grafana-service 3000:3000
kubectl port-forward -n seekapa-monitoring svc/prometheus-service 9090:9090

echo "Grafana: http://localhost:3000"
echo "Prometheus: http://localhost:9090"
```

### Log Management

#### Docker Compose
```bash
# View all logs
docker-compose logs -f

# View specific service logs
./scripts/deploy-docker.sh logs backend
./scripts/deploy-docker.sh logs frontend
```

#### Kubernetes
```bash
# View application logs
./scripts/deploy-k8s.sh logs seekapa-backend 100

# Stream logs
kubectl logs -f -l app=seekapa-backend -n seekapa
```

## 🔍 Health Checks & Troubleshooting

### Health Check Endpoints

| Service | Endpoint | Port |
|---------|----------|------|
| Backend | `/health` | 8000 |
| Frontend | `/health` | 80 |
| Prometheus | `/-/healthy` | 9090 |
| Grafana | `/api/health` | 3000 |

### Common Issues

#### Database Connection Issues
```bash
# Check database status
docker-compose exec postgres pg_isready -U seekapa_admin

# View database logs
docker-compose logs postgres

# Reset database (development only)
docker-compose down -v
docker-compose up -d
```

#### Redis Connection Issues
```bash
# Check Redis status
docker-compose exec redis redis-cli ping

# View Redis logs
docker-compose logs redis

# Check Redis memory usage
docker-compose exec redis redis-cli info memory
```

#### Application Issues
```bash
# Check application logs
./scripts/deploy-docker.sh logs backend

# Test API endpoints
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/powerbi/test-connection
```

### Performance Tuning

#### Database Optimization
```sql
-- Check slow queries
SELECT query, calls, total_time, mean_time
FROM pg_stat_statements
ORDER BY total_time DESC
LIMIT 10;

-- Check database connections
SELECT count(*) FROM pg_stat_activity;
```

#### Redis Optimization
```bash
# Check Redis performance
docker-compose exec redis redis-cli info stats

# Monitor Redis operations
docker-compose exec redis redis-cli monitor
```

## 🔄 Backup & Recovery

### Automated Backups (Production)

#### Docker Compose
```bash
# Database backup (automated daily)
docker-compose exec postgres pg_dump -U seekapa_admin seekapa_bi > backup.sql

# Manual backup
./scripts/backup.sh
```

#### Kubernetes
```bash
# Create backup
./scripts/deploy-k8s.sh backup

# Restore from backup
kubectl cp backup.sql seekapa/postgres-pod:/tmp/
kubectl exec -n seekapa postgres-pod -- psql -U seekapa_admin -d seekapa_bi < /tmp/backup.sql
```

## 🚢 Production Deployment Checklist

- [ ] Update all default passwords and secrets
- [ ] Configure SSL certificates
- [ ] Set up DNS records for domains
- [ ] Configure backup strategy
- [ ] Set up monitoring alerts
- [ ] Test disaster recovery procedures
- [ ] Configure log retention policies
- [ ] Set up CI/CD pipelines
- [ ] Configure firewall rules
- [ ] Set up monitoring dashboards

## 📚 Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)

## 🆘 Support

For deployment issues:
1. Check the logs using provided scripts
2. Verify environment configuration
3. Ensure all prerequisites are met
4. Check resource usage (CPU, memory, disk)
5. Review security settings and network connectivity