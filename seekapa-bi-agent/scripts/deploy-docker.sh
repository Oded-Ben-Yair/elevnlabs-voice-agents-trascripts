#!/bin/bash

# Deploy script for Docker Compose infrastructure
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# Check if Docker and Docker Compose are installed
check_dependencies() {
    print_status "Checking dependencies..."

    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi

    print_status "Dependencies check passed."
}

# Create necessary directories
create_directories() {
    print_status "Creating necessary directories..."

    mkdir -p logs/nginx
    mkdir -p database/backups
    mkdir -p ssl
    mkdir -p monitoring/grafana/provisioning
    mkdir -p nginx/conf.d
    mkdir -p nginx/prod/conf.d

    print_status "Directories created successfully."
}

# Check environment file
check_environment() {
    print_status "Checking environment configuration..."

    if [ ! -f ".env" ]; then
        print_error ".env file not found. Please create one based on .env.example"
        exit 1
    fi

    # Check for required environment variables
    required_vars=("POSTGRES_PASSWORD" "REDIS_PASSWORD" "JWT_SECRET_KEY" "AZURE_OPENAI_API_KEY")

    for var in "${required_vars[@]}"; do
        if ! grep -q "^$var=" .env; then
            print_warning "$var not found in .env file"
        fi
    done

    print_status "Environment configuration checked."
}

# Deploy function
deploy() {
    local environment=$1
    print_status "Deploying Seekapa BI Agent in $environment mode..."

    case $environment in
        "dev"|"development")
            print_status "Starting development environment..."
            docker-compose -f docker-compose.dev.yml down --remove-orphans
            docker-compose -f docker-compose.dev.yml up -d --build
            ;;
        "prod"|"production")
            print_status "Starting production environment..."
            docker-compose -f docker-compose.prod.yml down --remove-orphans
            docker-compose -f docker-compose.prod.yml up -d --build
            ;;
        *)
            print_status "Starting default environment..."
            docker-compose down --remove-orphans
            docker-compose up -d --build
            ;;
    esac

    print_status "Waiting for services to start..."
    sleep 30

    # Health check
    health_check $environment
}

# Health check function
health_check() {
    local environment=$1
    print_status "Performing health checks..."

    local backend_url="http://localhost:8000"
    local frontend_url="http://localhost:3000"

    if [ "$environment" = "prod" ] || [ "$environment" = "production" ]; then
        frontend_url="http://localhost:80"
    fi

    # Check backend health
    if curl -f -s "$backend_url/health" > /dev/null; then
        print_status "Backend is healthy ✓"
    else
        print_error "Backend health check failed ✗"
    fi

    # Check frontend
    if curl -f -s "$frontend_url" > /dev/null; then
        print_status "Frontend is accessible ✓"
    else
        print_error "Frontend health check failed ✗"
    fi

    # Check database connection
    if docker-compose exec -T postgres pg_isready -U seekapa_admin > /dev/null 2>&1; then
        print_status "Database is ready ✓"
    else
        print_error "Database connection failed ✗"
    fi

    # Check Redis
    if docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; then
        print_status "Redis is ready ✓"
    else
        print_error "Redis connection failed ✗"
    fi
}

# Show service status
show_status() {
    print_status "Service Status:"
    docker-compose ps

    print_status "\nService URLs:"
    echo "Frontend: http://localhost:3000 (dev) or http://localhost:80 (prod)"
    echo "Backend API: http://localhost:8000"
    echo "API Documentation: http://localhost:8000/docs"
    echo "Grafana: http://localhost:3001"
    echo "Prometheus: http://localhost:9090"
    echo "Redis Commander: http://localhost:8081 (dev only)"
    echo "PgAdmin: http://localhost:8082 (dev only)"
}

# Cleanup function
cleanup() {
    print_status "Cleaning up Docker resources..."
    docker-compose down --remove-orphans --volumes
    docker system prune -f
    print_status "Cleanup completed."
}

# Main script logic
main() {
    local command=${1:-"deploy"}
    local environment=${2:-"dev"}

    case $command in
        "deploy")
            check_dependencies
            create_directories
            check_environment
            deploy $environment
            show_status
            ;;
        "status")
            show_status
            ;;
        "health")
            health_check $environment
            ;;
        "cleanup")
            cleanup
            ;;
        "logs")
            local service=${2:-""}
            if [ -z "$service" ]; then
                docker-compose logs -f --tail=100
            else
                docker-compose logs -f --tail=100 "$service"
            fi
            ;;
        *)
            echo "Usage: $0 {deploy|status|health|cleanup|logs} [environment|service]"
            echo ""
            echo "Commands:"
            echo "  deploy [dev|prod]  - Deploy the application (default: dev)"
            echo "  status            - Show service status"
            echo "  health [env]      - Run health checks"
            echo "  cleanup           - Stop and remove all containers and volumes"
            echo "  logs [service]    - Show logs (all services or specific service)"
            echo ""
            echo "Examples:"
            echo "  $0 deploy dev     - Deploy development environment"
            echo "  $0 deploy prod    - Deploy production environment"
            echo "  $0 logs backend   - Show backend logs"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"