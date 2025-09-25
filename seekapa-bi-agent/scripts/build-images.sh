#!/bin/bash

# Docker image build and push script for Seekapa BI Agent
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REGISTRY=${REGISTRY:-"seekapa"}
VERSION=${VERSION:-"latest"}
BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

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

# Check dependencies
check_dependencies() {
    print_status "Checking dependencies..."

    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi

    print_status "Dependencies check passed."
}

# Build backend image
build_backend() {
    local target=${1:-"production"}
    local image_name="$REGISTRY/bi-agent-backend"
    local full_tag="$image_name:$VERSION"

    print_header "Building backend image: $full_tag (target: $target)"

    docker build \
        --target "$target" \
        --build-arg BUILD_DATE="$BUILD_DATE" \
        --build-arg GIT_COMMIT="$GIT_COMMIT" \
        --build-arg VERSION="$VERSION" \
        --tag "$full_tag" \
        --tag "$image_name:latest" \
        backend/

    if [ $? -eq 0 ]; then
        print_status "Backend image built successfully: $full_tag"
    else
        print_error "Backend image build failed"
        exit 1
    fi
}

# Build frontend image
build_frontend() {
    local target=${1:-"production"}
    local image_name="$REGISTRY/bi-agent-frontend"
    local full_tag="$image_name:$VERSION"

    print_header "Building frontend image: $full_tag (target: $target)"

    docker build \
        --target "$target" \
        --build-arg BUILD_DATE="$BUILD_DATE" \
        --build-arg GIT_COMMIT="$GIT_COMMIT" \
        --build-arg VERSION="$VERSION" \
        --build-arg VITE_API_URL="${API_URL:-http://localhost:8000}" \
        --build-arg VITE_APP_NAME="Seekapa BI Agent" \
        --build-arg VITE_APP_VERSION="$VERSION" \
        --tag "$full_tag" \
        --tag "$image_name:latest" \
        frontend/

    if [ $? -eq 0 ]; then
        print_status "Frontend image built successfully: $full_tag"
    else
        print_error "Frontend image build failed"
        exit 1
    fi
}

# Push images to registry
push_images() {
    print_header "Pushing images to registry..."

    local backend_image="$REGISTRY/bi-agent-backend"
    local frontend_image="$REGISTRY/bi-agent-frontend"

    # Push backend images
    print_status "Pushing backend image..."
    docker push "$backend_image:$VERSION"
    docker push "$backend_image:latest"

    # Push frontend images
    print_status "Pushing frontend image..."
    docker push "$frontend_image:$VERSION"
    docker push "$frontend_image:latest"

    print_status "All images pushed successfully."
}

# Test images
test_images() {
    print_header "Testing built images..."

    local backend_image="$REGISTRY/bi-agent-backend:$VERSION"
    local frontend_image="$REGISTRY/bi-agent-frontend:$VERSION"

    # Test backend image
    print_status "Testing backend image..."
    docker run --rm "$backend_image" python -c "import app.main; print('Backend image OK')"

    # Test frontend image
    print_status "Testing frontend image..."
    # Start nginx in test mode
    docker run --rm "$frontend_image" nginx -t

    print_status "All images tested successfully."
}

# Scan images for vulnerabilities (if trivy is available)
scan_images() {
    if command -v trivy &> /dev/null; then
        print_header "Scanning images for vulnerabilities..."

        local backend_image="$REGISTRY/bi-agent-backend:$VERSION"
        local frontend_image="$REGISTRY/bi-agent-frontend:$VERSION"

        print_status "Scanning backend image..."
        trivy image --exit-code 1 --severity HIGH,CRITICAL "$backend_image" || print_warning "Backend image has vulnerabilities"

        print_status "Scanning frontend image..."
        trivy image --exit-code 1 --severity HIGH,CRITICAL "$frontend_image" || print_warning "Frontend image has vulnerabilities"
    else
        print_warning "Trivy not found, skipping vulnerability scan"
    fi
}

# Show image information
show_info() {
    print_header "Image Information"

    local backend_image="$REGISTRY/bi-agent-backend"
    local frontend_image="$REGISTRY/bi-agent-frontend"

    echo "Backend Images:"
    docker images "$backend_image" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"

    echo ""
    echo "Frontend Images:"
    docker images "$frontend_image" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"

    echo ""
    echo "Build Information:"
    echo "Version: $VERSION"
    echo "Git Commit: $GIT_COMMIT"
    echo "Build Date: $BUILD_DATE"
    echo "Registry: $REGISTRY"
}

# Clean up old images
cleanup() {
    print_header "Cleaning up old images..."

    # Remove untagged images
    docker image prune -f

    # Remove old versions (keep last 3)
    local backend_image="$REGISTRY/bi-agent-backend"
    local frontend_image="$REGISTRY/bi-agent-frontend"

    docker images "$backend_image" --format "{{.ID}} {{.Tag}}" | grep -v latest | tail -n +4 | awk '{print $1}' | xargs -r docker rmi || true
    docker images "$frontend_image" --format "{{.ID}} {{.Tag}}" | grep -v latest | tail -n +4 | awk '{print $1}' | xargs -r docker rmi || true

    print_status "Cleanup completed."
}

# Build multi-arch images
build_multiarch() {
    print_header "Building multi-architecture images..."

    # Check if buildx is available
    if ! docker buildx version &> /dev/null; then
        print_error "Docker buildx is not available. Multi-arch builds require buildx."
        exit 1
    fi

    # Create builder if it doesn't exist
    docker buildx create --name multiarch --use --driver docker-container --bootstrap || true

    local backend_image="$REGISTRY/bi-agent-backend"
    local frontend_image="$REGISTRY/bi-agent-frontend"

    # Build backend multi-arch
    print_status "Building multi-arch backend image..."
    docker buildx build \
        --platform linux/amd64,linux/arm64 \
        --target production \
        --build-arg BUILD_DATE="$BUILD_DATE" \
        --build-arg GIT_COMMIT="$GIT_COMMIT" \
        --build-arg VERSION="$VERSION" \
        --tag "$backend_image:$VERSION" \
        --tag "$backend_image:latest" \
        --push \
        backend/

    # Build frontend multi-arch
    print_status "Building multi-arch frontend image..."
    docker buildx build \
        --platform linux/amd64,linux/arm64 \
        --target production \
        --build-arg BUILD_DATE="$BUILD_DATE" \
        --build-arg GIT_COMMIT="$GIT_COMMIT" \
        --build-arg VERSION="$VERSION" \
        --tag "$frontend_image:$VERSION" \
        --tag "$frontend_image:latest" \
        --push \
        frontend/

    print_status "Multi-arch images built and pushed successfully."
}

# Main script logic
main() {
    local command=${1:-"build"}
    local target=${2:-"production"}

    # Set version from git tag if available
    if [ "$VERSION" = "latest" ]; then
        local git_tag=$(git describe --tags --exact-match 2>/dev/null || echo "")
        if [ -n "$git_tag" ]; then
            VERSION=$git_tag
            print_status "Using git tag as version: $VERSION"
        fi
    fi

    case $command in
        "build")
            check_dependencies
            build_backend "$target"
            build_frontend "$target"
            show_info
            ;;
        "backend")
            check_dependencies
            build_backend "$target"
            ;;
        "frontend")
            check_dependencies
            build_frontend "$target"
            ;;
        "push")
            push_images
            ;;
        "test")
            test_images
            ;;
        "scan")
            scan_images
            ;;
        "multiarch")
            check_dependencies
            build_multiarch
            ;;
        "all")
            check_dependencies
            build_backend "$target"
            build_frontend "$target"
            test_images
            scan_images
            push_images
            show_info
            ;;
        "info")
            show_info
            ;;
        "cleanup")
            cleanup
            ;;
        *)
            echo "Usage: $0 {build|backend|frontend|push|test|scan|multiarch|all|info|cleanup} [target]"
            echo ""
            echo "Commands:"
            echo "  build [target]    - Build both images (default: production)"
            echo "  backend [target]  - Build backend image only"
            echo "  frontend [target] - Build frontend image only"
            echo "  push             - Push images to registry"
            echo "  test             - Test built images"
            echo "  scan             - Scan images for vulnerabilities"
            echo "  multiarch        - Build multi-architecture images"
            echo "  all [target]     - Build, test, scan, and push"
            echo "  info             - Show image information"
            echo "  cleanup          - Remove old images"
            echo ""
            echo "Targets:"
            echo "  development      - Build development images"
            echo "  production       - Build production images (default)"
            echo "  testing          - Build testing images"
            echo ""
            echo "Environment variables:"
            echo "  REGISTRY         - Docker registry (default: seekapa)"
            echo "  VERSION          - Image version tag (default: latest)"
            echo "  API_URL          - Frontend API URL"
            echo ""
            echo "Examples:"
            echo "  $0 build production"
            echo "  REGISTRY=myregistry VERSION=v1.0.0 $0 all"
            echo "  $0 multiarch"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"