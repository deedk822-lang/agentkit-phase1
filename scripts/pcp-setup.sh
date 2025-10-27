# Production Control Plane - Complete Setup Script
# This script sets up the entire PCP system from scratch

set -euo pipefail

COLOR_RESET='\033[0m'
COLOR_GREEN='\033[0;32m'
COLOR_BLUE='\033[0;34m'
COLOR_YELLOW='\033[1;33m'
COLOR_RED='\033[0;31m'

log(){ echo -e "$1"; }
info(){ log "${COLOR_BLUE}ℹ️  $1${COLOR_RESET}"; }
success(){ log "${COLOR_GREEN}✅ $1${COLOR_RESET}"; }
warn(){ log "${COLOR_YELLOW}⚠️  $1${COLOR_RESET}"; }
err(){ log "${COLOR_RED}❌ $1${COLOR_RESET}"; }

require(){ command -v "$1" >/dev/null 2>&1 || { err "$1 is required"; exit 1; }; }

info "Checking prerequisites"
for c in gcloud docker kubectl; do require $c; done

PROJECT_ID=${GCP_PROJECT_ID:-"quantum-observer-prod"}
REGION=${GCP_REGION:-"us-central1"}

info "Enabling GCP services"
gcloud services enable compute.googleapis.com container.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com containerregistry.googleapis.com --project "$PROJECT_ID"

info "Building images"
docker build -t gcr.io/$PROJECT_ID/mcp-orchestrator:latest -f server/mcp-orchestrator.Dockerfile .
docker build -t gcr.io/$PROJECT_ID/command-poller:latest -f agents/command-poller.Dockerfile .

docker push gcr.io/$PROJECT_ID/mcp-orchestrator:latest
docker push gcr.io/$PROJECT_ID/command-poller:latest

info "Applying infrastructure"
kubectl apply -f infrastructure/gcp-deployment.yml

success "Deployment kicked off. Use kubectl get ingress -n pcp-prod to obtain the external URL."
