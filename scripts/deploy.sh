#!/bin/bash

###############################################################################
# Basirah Production Deployment Script
# 
# This script deploys Basirah to a Kubernetes cluster using Helm.
# 
# Usage: ./deploy.sh [OPTIONS]
# 
# Options:
#   -n, --namespace NAMESPACE    Kubernetes namespace (default: basirah)
#   -r, --release NAME           Helm release name (default: basirah)
#   -v, --values FILE            Custom values file
#   -t, --tag TAG                Docker image tag (default: 1.0.0)
#   -h, --help                   Show this help message
###############################################################################

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
NAMESPACE="basirah"
RELEASE_NAME="basirah"
VALUES_FILE=""
IMAGE_TAG="1.0.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_help() {
    grep '^#' "$0" | tail -n +3
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -r|--release)
            RELEASE_NAME="$2"
            shift 2
            ;;
        -v|--values)
            VALUES_FILE="$2"
            shift 2
            ;;
        -t|--tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Validate prerequisites
log_info "Validating prerequisites..."

if ! command -v kubectl &> /dev/null; then
    log_error "kubectl is not installed"
    exit 1
fi

if ! command -v helm &> /dev/null; then
    log_error "helm is not installed"
    exit 1
fi

# Check Kubernetes cluster connectivity
if ! kubectl cluster-info &> /dev/null; then
    log_error "Cannot connect to Kubernetes cluster"
    exit 1
fi

log_info "Prerequisites validated"

# Create namespace if it doesn't exist
log_info "Creating namespace: $NAMESPACE"
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# Build Helm command
HELM_CMD="helm upgrade --install $RELEASE_NAME $PROJECT_ROOT/helm"
HELM_CMD="$HELM_CMD --namespace $NAMESPACE"
HELM_CMD="$HELM_CMD --set image.tag=$IMAGE_TAG"

if [ -n "$VALUES_FILE" ]; then
    if [ ! -f "$VALUES_FILE" ]; then
        log_error "Values file not found: $VALUES_FILE"
        exit 1
    fi
    HELM_CMD="$HELM_CMD -f $VALUES_FILE"
fi

# Deploy
log_info "Deploying Basirah with Helm..."
log_info "Command: $HELM_CMD"

if eval "$HELM_CMD"; then
    log_info "Deployment initiated successfully"
else
    log_error "Deployment failed"
    exit 1
fi

# Wait for rollout
log_info "Waiting for deployment to be ready..."
if kubectl rollout status deployment/"$RELEASE_NAME" -n "$NAMESPACE" --timeout=5m; then
    log_info "Deployment completed successfully"
else
    log_error "Deployment rollout failed or timed out"
    exit 1
fi

# Display deployment info
log_info "Deployment Information:"
kubectl get deployment,pods,svc -n "$NAMESPACE" -l "app.kubernetes.io/instance=$RELEASE_NAME"

# Display access information
log_info "To access the application:"
SERVICE_IP=$(kubectl get svc "$RELEASE_NAME" -n "$NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "pending")
if [ "$SERVICE_IP" != "pending" ]; then
    log_info "Service IP: $SERVICE_IP"
else
    log_warn "Service IP is pending. Use 'kubectl get svc -n $NAMESPACE' to check"
fi

log_info "Deployment completed!"
