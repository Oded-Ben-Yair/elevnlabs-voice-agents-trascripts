#!/bin/bash

# Kubernetes deployment script for Seekapa BI Agent
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}[HEADER]${NC} $1"
}

# Configuration
NAMESPACE=${NAMESPACE:-"seekapa"}
MONITORING_NAMESPACE=${MONITORING_NAMESPACE:-"seekapa-monitoring"}
KUBECTL=${KUBECTL:-"kubectl"}
CONTEXT=${CONTEXT:-""}

# Check dependencies
check_dependencies() {
    print_status "Checking dependencies..."

    if ! command -v kubectl &> /dev/null; then
        print_error "kubectl is not installed. Please install kubectl first."
        exit 1
    fi

    if ! command -v helm &> /dev/null; then
        print_warning "helm is not installed. Some features may not be available."
    fi

    # Check cluster connection
    if ! $KUBECTL cluster-info &> /dev/null; then
        print_error "Cannot connect to Kubernetes cluster. Please check your kubectl configuration."
        exit 1
    fi

    print_status "Dependencies check passed."
}

# Set kubectl context if specified
set_context() {
    if [ -n "$CONTEXT" ]; then
        print_status "Setting kubectl context to: $CONTEXT"
        $KUBECTL config use-context "$CONTEXT"
    fi
}

# Create namespaces
create_namespaces() {
    print_status "Creating namespaces..."
    $KUBECTL apply -f k8s/namespace.yaml
    print_status "Namespaces created successfully."
}

# Deploy secrets and configmaps
deploy_config() {
    print_status "Deploying ConfigMaps and Secrets..."

    # Apply configmaps
    $KUBECTL apply -f k8s/configmap.yaml

    # Apply secrets (warning about production secrets)
    print_warning "Deploying secrets from k8s/secret.yaml - Make sure to update these for production!"
    $KUBECTL apply -f k8s/secret.yaml

    print_status "Configuration deployed successfully."
}

# Deploy persistent volumes
deploy_storage() {
    print_status "Deploying persistent volumes..."
    $KUBECTL apply -f k8s/pvc.yaml

    # Wait for PVCs to be bound
    print_status "Waiting for PVCs to be bound..."
    $KUBECTL wait --for=condition=Bound pvc/postgres-pvc -n $NAMESPACE --timeout=300s
    $KUBECTL wait --for=condition=Bound pvc/redis-pvc -n $NAMESPACE --timeout=300s

    print_status "Storage deployed successfully."
}

# Deploy applications
deploy_applications() {
    print_status "Deploying applications..."

    # Deploy database and cache first
    $KUBECTL apply -f k8s/deployment.yaml

    # Wait for database to be ready
    print_status "Waiting for database to be ready..."
    $KUBECTL wait --for=condition=Ready pod -l app=seekapa-postgres -n $NAMESPACE --timeout=300s

    # Wait for Redis to be ready
    print_status "Waiting for Redis to be ready..."
    $KUBECTL wait --for=condition=Ready pod -l app=seekapa-redis -n $NAMESPACE --timeout=300s

    print_status "Applications deployed successfully."
}

# Deploy services
deploy_services() {
    print_status "Deploying services..."
    $KUBECTL apply -f k8s/service.yaml
    print_status "Services deployed successfully."
}

# Deploy ingress
deploy_ingress() {
    print_status "Deploying ingress..."
    $KUBECTL apply -f k8s/ingress.yaml
    print_status "Ingress deployed successfully."
}

# Deploy monitoring
deploy_monitoring() {
    print_status "Deploying monitoring stack..."

    # Create monitoring namespace first
    $KUBECTL create namespace $MONITORING_NAMESPACE --dry-run=client -o yaml | $KUBECTL apply -f -

    # Deploy monitoring components
    $KUBECTL apply -f k8s/monitoring.yaml

    # Wait for monitoring services
    print_status "Waiting for monitoring services to be ready..."
    $KUBECTL wait --for=condition=Ready pod -l app=prometheus -n $MONITORING_NAMESPACE --timeout=300s || true
    $KUBECTL wait --for=condition=Ready pod -l app=grafana -n $MONITORING_NAMESPACE --timeout=300s || true

    print_status "Monitoring deployed successfully."
}

# Scale applications
scale_applications() {
    local replicas=${1:-3}
    print_status "Scaling applications to $replicas replicas..."

    $KUBECTL scale deployment/seekapa-backend --replicas=$replicas -n $NAMESPACE
    $KUBECTL scale deployment/seekapa-frontend --replicas=2 -n $NAMESPACE

    print_status "Applications scaled successfully."
}

# Health check
health_check() {
    print_status "Performing health checks..."

    # Check pod status
    print_status "Pod Status:"
    $KUBECTL get pods -n $NAMESPACE

    # Check service endpoints
    print_status "Service Endpoints:"
    $KUBECTL get endpoints -n $NAMESPACE

    # Check ingress
    print_status "Ingress Status:"
    $KUBECTL get ingress -n $NAMESPACE

    # Test backend health endpoint
    backend_pod=$($KUBECTL get pods -n $NAMESPACE -l app=seekapa-backend -o jsonpath='{.items[0].metadata.name}')
    if [ -n "$backend_pod" ]; then
        if $KUBECTL exec -n $NAMESPACE "$backend_pod" -- curl -f -s http://localhost:8000/health > /dev/null; then
            print_status "Backend health check passed ✓"
        else
            print_error "Backend health check failed ✗"
        fi
    fi
}

# Show service information
show_info() {
    print_header "=== Seekapa BI Agent - Deployment Information ==="

    print_status "Namespace: $NAMESPACE"
    print_status "Monitoring Namespace: $MONITORING_NAMESPACE"

    echo ""
    print_status "Pods:"
    $KUBECTL get pods -n $NAMESPACE -o wide

    echo ""
    print_status "Services:"
    $KUBECTL get services -n $NAMESPACE

    echo ""
    print_status "Ingress:"
    $KUBECTL get ingress -n $NAMESPACE

    # Get external IPs if available
    external_ip=$($KUBECTL get service -n $NAMESPACE seekapa-frontend-external -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
    if [ -n "$external_ip" ]; then
        echo ""
        print_status "External Access:"
        echo "Frontend: http://$external_ip"
        echo "API: http://$external_ip/api"
    fi

    echo ""
    print_status "Monitoring:"
    monitoring_pods=$($KUBECTL get pods -n $MONITORING_NAMESPACE --no-headers 2>/dev/null | wc -l || echo "0")
    echo "Monitoring pods: $monitoring_pods"

    if [ "$monitoring_pods" -gt 0 ]; then
        echo "Prometheus: kubectl port-forward -n $MONITORING_NAMESPACE svc/prometheus-service 9090:9090"
        echo "Grafana: kubectl port-forward -n $MONITORING_NAMESPACE svc/grafana-service 3000:3000"
    fi
}

# Get logs
get_logs() {
    local service=${1:-"seekapa-backend"}
    local lines=${2:-100}

    print_status "Getting logs for $service (last $lines lines)..."
    $KUBECTL logs -n $NAMESPACE -l app=$service --tail=$lines -f
}

# Cleanup
cleanup() {
    print_warning "This will delete all Seekapa resources. Are you sure? (y/N)"
    read -r confirmation
    if [ "$confirmation" = "y" ] || [ "$confirmation" = "Y" ]; then
        print_status "Cleaning up resources..."
        $KUBECTL delete namespace $NAMESPACE --ignore-not-found=true
        $KUBECTL delete namespace $MONITORING_NAMESPACE --ignore-not-found=true
        print_status "Cleanup completed."
    else
        print_status "Cleanup cancelled."
    fi
}

# Backup
backup() {
    local backup_dir="backups/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup_dir"

    print_status "Creating backup in $backup_dir..."

    # Backup database
    postgres_pod=$($KUBECTL get pods -n $NAMESPACE -l app=seekapa-postgres -o jsonpath='{.items[0].metadata.name}')
    if [ -n "$postgres_pod" ]; then
        $KUBECTL exec -n $NAMESPACE "$postgres_pod" -- pg_dump -U seekapa_admin seekapa_bi > "$backup_dir/postgres_backup.sql"
        print_status "Database backup created: $backup_dir/postgres_backup.sql"
    fi

    # Backup Kubernetes manifests
    $KUBECTL get all,configmap,secret,pvc,ingress -n $NAMESPACE -o yaml > "$backup_dir/k8s_resources.yaml"
    print_status "Kubernetes resources backup created: $backup_dir/k8s_resources.yaml"
}

# Full deployment
full_deploy() {
    print_header "=== Full Deployment Starting ==="

    check_dependencies
    set_context
    create_namespaces
    deploy_config
    deploy_storage
    deploy_applications
    deploy_services
    deploy_ingress

    if [ "$1" = "--with-monitoring" ]; then
        deploy_monitoring
    fi

    print_status "Waiting for all pods to be ready..."
    sleep 30

    health_check
    show_info

    print_header "=== Deployment Complete ==="
}

# Main script logic
main() {
    local command=${1:-"deploy"}

    case $command in
        "deploy")
            full_deploy $2
            ;;
        "scale")
            scale_applications $2
            ;;
        "status"|"info")
            show_info
            ;;
        "health")
            health_check
            ;;
        "logs")
            get_logs $2 $3
            ;;
        "cleanup")
            cleanup
            ;;
        "backup")
            backup
            ;;
        "monitoring")
            deploy_monitoring
            ;;
        *)
            echo "Usage: $0 {deploy|scale|status|health|logs|cleanup|backup|monitoring} [options]"
            echo ""
            echo "Commands:"
            echo "  deploy [--with-monitoring]  - Full deployment (optionally with monitoring)"
            echo "  scale [replicas]           - Scale backend deployment (default: 3)"
            echo "  status                     - Show deployment status"
            echo "  health                     - Run health checks"
            echo "  logs [service] [lines]     - Show logs (default: seekapa-backend, 100 lines)"
            echo "  cleanup                    - Delete all resources"
            echo "  backup                     - Create backup of database and configs"
            echo "  monitoring                 - Deploy monitoring stack only"
            echo ""
            echo "Environment variables:"
            echo "  NAMESPACE                  - Kubernetes namespace (default: seekapa)"
            echo "  MONITORING_NAMESPACE       - Monitoring namespace (default: seekapa-monitoring)"
            echo "  CONTEXT                    - Kubectl context to use"
            echo ""
            echo "Examples:"
            echo "  $0 deploy --with-monitoring"
            echo "  $0 scale 5"
            echo "  $0 logs seekapa-backend 200"
            echo "  CONTEXT=production $0 deploy"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"