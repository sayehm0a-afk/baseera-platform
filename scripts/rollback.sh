#!/bin/bash

###############################################################################
# Basirah Production Rollback Script
# 
# This script rolls back a Basirah deployment to a previous version.
# 
# Usage: ./rollback.sh [OPTIONS]
# 
# Options:
#   -n, --namespace NAMESPACE    Kubernetes namespace (default: basirah)
#   -r, --release NAME           Helm release name (default: basirah)
#   -v, --revision REVISION      Revision to rollback to (default: 0 for previous)
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
REVISION=0

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
        -v|--revision)
            REVISION="$2"
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

# List available revisions
log_info "Available revisions for release '$RELEASE_NAME':"
helm history "$RELEASE_NAME" -n "$NAMESPACE" || {
    log_error "Release not found: $RELEASE_NAME in namespace $NAMESPACE"
    exit 1
}

# Confirm rollback
if [ "$REVISION" -eq 0 ]; then
    log_warn "Rolling back to previous version (revision 0)"
else
    log_warn "Rolling back to revision $REVISION"
fi

read -p "Are you sure you want to proceed? (yes/no): " -r CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    log_info "Rollback cancelled"
    exit 0
fi

# Perform rollback
log_info "Performing rollback..."
if [ "$REVISION" -eq 0 ]; then
    helm rollback "$RELEASE_NAME" -n "$NAMESPACE"
else
    helm rollback "$RELEASE_NAME" "$REVISION" -n "$NAMESPACE"
fi

# Wait for rollout
log_info "Waiting for deployment to be ready..."
if kubectl rollout status deployment/"$RELEASE_NAME" -n "$NAMESPACE" --timeout=5m; then
    log_info "Rollback completed successfully"
else
    log_error "Rollback rollout failed or timed out"
    exit 1
fi

# Display deployment info
log_info "Current Deployment Status:"
kubectl get deployment,pods,svc -n "$NAMESPACE" -l "app.kubernetes.io/instance=$RELEASE_NAME"

log_info "Rollback completed!"
