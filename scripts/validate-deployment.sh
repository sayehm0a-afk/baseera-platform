#!/bin/bash

###############################################################################
# Basirah Deployment Health Validation Script
# 
# This script validates the health of a Basirah deployment.
# 
# Usage: ./validate-deployment.sh [OPTIONS]
# 
# Options:
#   -n, --namespace NAMESPACE    Kubernetes namespace (default: basirah)
#   -r, --release NAME           Helm release name (default: basirah)
#   -t, --timeout SECONDS        Timeout for health checks (default: 300)
#   -h, --help                   Show this help message
###############################################################################

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
NAMESPACE="basirah"
RELEASE_NAME="basirah"
TIMEOUT=300
START_TIME=$(date +%s)

# Functions
log_info() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[!]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

log_check() {
    echo -e "${BLUE}[*]${NC} $1"
}

check_timeout() {
    local current_time=$(date +%s)
    local elapsed=$((current_time - START_TIME))
    if [ $elapsed -gt $TIMEOUT ]; then
        log_error "Timeout exceeded ($elapsed > $TIMEOUT seconds)"
        return 1
    fi
    return 0
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
        -t|--timeout)
            TIMEOUT="$2"
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

# Initialize validation results
VALIDATION_PASSED=true
CHECKS_PASSED=0
CHECKS_FAILED=0

# Validate prerequisites
log_check "Validating prerequisites..."

if ! command -v kubectl &> /dev/null; then
    log_error "kubectl is not installed"
    exit 1
fi

if ! kubectl cluster-info &> /dev/null; then
    log_error "Cannot connect to Kubernetes cluster"
    exit 1
fi

log_info "Prerequisites validated"

# Check 1: Namespace exists
log_check "Checking namespace..."
if kubectl get namespace "$NAMESPACE" &> /dev/null; then
    log_info "Namespace '$NAMESPACE' exists"
    ((CHECKS_PASSED++))
else
    log_error "Namespace '$NAMESPACE' not found"
    ((CHECKS_FAILED++))
    VALIDATION_PASSED=false
fi

# Check 2: Deployment exists
log_check "Checking deployment..."
if kubectl get deployment "$RELEASE_NAME" -n "$NAMESPACE" &> /dev/null; then
    log_info "Deployment '$RELEASE_NAME' exists"
    ((CHECKS_PASSED++))
else
    log_error "Deployment '$RELEASE_NAME' not found"
    ((CHECKS_FAILED++))
    VALIDATION_PASSED=false
fi

# Check 3: Pods are running
log_check "Checking pod status..."
READY_PODS=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/instance=$RELEASE_NAME" -o jsonpath='{.items[?(@.status.conditions[?(@.type=="Ready")].status=="True")].metadata.name}' | wc -w)
TOTAL_PODS=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/instance=$RELEASE_NAME" --no-headers | wc -l)

if [ "$READY_PODS" -gt 0 ] && [ "$READY_PODS" -eq "$TOTAL_PODS" ]; then
    log_info "All pods are ready ($READY_PODS/$TOTAL_PODS)"
    ((CHECKS_PASSED++))
else
    log_warn "Not all pods are ready ($READY_PODS/$TOTAL_PODS)"
    ((CHECKS_FAILED++))
    VALIDATION_PASSED=false
fi

# Check 4: Service exists
log_check "Checking service..."
if kubectl get svc "$RELEASE_NAME" -n "$NAMESPACE" &> /dev/null; then
    log_info "Service '$RELEASE_NAME' exists"
    ((CHECKS_PASSED++))
else
    log_error "Service '$RELEASE_NAME' not found"
    ((CHECKS_FAILED++))
    VALIDATION_PASSED=false
fi

# Check 5: Deployment rollout status
log_check "Checking deployment rollout status..."
if kubectl rollout status deployment/"$RELEASE_NAME" -n "$NAMESPACE" --timeout=30s &> /dev/null; then
    log_info "Deployment rollout is complete"
    ((CHECKS_PASSED++))
else
    log_warn "Deployment rollout is not complete"
    ((CHECKS_FAILED++))
fi

# Check 6: Health endpoint
log_check "Checking health endpoint..."
POD_NAME=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/instance=$RELEASE_NAME" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [ -n "$POD_NAME" ]; then
    if kubectl exec -n "$NAMESPACE" "$POD_NAME" -- curl -s http://localhost:8000/health/ready &> /dev/null; then
        log_info "Health endpoint is responding"
        ((CHECKS_PASSED++))
    else
        log_warn "Health endpoint is not responding"
        ((CHECKS_FAILED++))
    fi
else
    log_warn "No pods found to check health endpoint"
    ((CHECKS_FAILED++))
fi

# Check 7: Database connectivity
log_check "Checking database connectivity..."
if [ -n "$POD_NAME" ]; then
    if kubectl exec -n "$NAMESPACE" "$POD_NAME" -- python3 -c "from src.core.db.database import init_db; init_db()" &> /dev/null; then
        log_info "Database connectivity is working"
        ((CHECKS_PASSED++))
    else
        log_warn "Database connectivity check failed"
        ((CHECKS_FAILED++))
    fi
else
    log_warn "No pods found to check database connectivity"
    ((CHECKS_FAILED++))
fi

# Check 8: Resource usage
log_check "Checking resource usage..."
MEMORY_USAGE=$(kubectl top pods -n "$NAMESPACE" -l "app.kubernetes.io/instance=$RELEASE_NAME" --no-headers 2>/dev/null | awk '{print $2}' | sort -rn | head -1 || echo "0")
CPU_USAGE=$(kubectl top pods -n "$NAMESPACE" -l "app.kubernetes.io/instance=$RELEASE_NAME" --no-headers 2>/dev/null | awk '{print $1}' | sort -rn | head -1 || echo "0")

if [ -n "$MEMORY_USAGE" ] && [ -n "$CPU_USAGE" ]; then
    log_info "Resource usage - CPU: ${CPU_USAGE}m, Memory: ${MEMORY_USAGE}Mi"
    ((CHECKS_PASSED++))
else
    log_warn "Could not retrieve resource usage metrics"
    ((CHECKS_FAILED++))
fi

# Summary
echo ""
echo "=========================================="
echo "Validation Summary"
echo "=========================================="
echo "Checks Passed: $CHECKS_PASSED"
echo "Checks Failed: $CHECKS_FAILED"
echo "Total Checks: $((CHECKS_PASSED + CHECKS_FAILED))"
echo "=========================================="

if [ "$VALIDATION_PASSED" = true ] && [ "$CHECKS_FAILED" -eq 0 ]; then
    log_info "All validation checks passed!"
    exit 0
else
    log_warn "Some validation checks failed. Please review the output above."
    exit 1
fi
