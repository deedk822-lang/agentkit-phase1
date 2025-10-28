#!/bin/bash
set -euo pipefail

# ... (All color and log functions remain the same) ...
COLOR_RESET='\033[0m'
COLOR_GREEN='\033[0;32m'
COLOR_BLUE='\033[0;34m'
COLOR_YELLOW='\033[1;33m'
COLOR_RED='\033[0;31m'
log_info() { echo -e "${COLOR_BLUE}ℹ️ $1${COLOR_RESET}"; }
log_success() { echo -e "${COLOR_GREEN}✅ $1${COLOR_RESET}"; }
log_warning() { echo -e "${COLOR_YELLOW}⚠️ $1${COLOR_RESET}"; }
log_error() { echo -e "${COLOR_RED}❌ $1${COLOR_RESET}"; }
confirm() { read -p "$1 [y/N]: " response; case "$response" in [yY][eE][sS]|[yY]) return 0;; *) return 1;; esac; }

check_prerequisites() {
# ... (remains the same) ...
log_info "Checking prerequisites..."; local missing_tools=(); command -v docker >/dev/null 2>&1 || missing_tools+=("docker"); command -v kubectl >/dev/null 2>&1 || missing_tools+=("kubectl"); command -v gcloud >/dev/null 2>&1 || missing_tools+=("gcloud"); command -v python3 >/dev/null 2>&1 || missing_tools+=("python3"); command -v openssl >/dev/null 2>&1 || missing_tools+=("openssl"); if [ ${#missing_tools[@]} -ne 0 ]; then log_error "Missing required tools: ${missing_tools[*]}"; exit 1; fi; log_success "All prerequisites met"
}

setup_configuration() {
# ... (remains the same, ensures .env is loaded) ...
log_info "Setting up configuration..."; if [ ! -f .env ]; then log_warning ".env file not found. Please copy .env.template to .env and fill it out."; exit 1; fi; set -a; source .env; set +a; log_success "Configuration loaded from .env"
}

setup_gcp_cluster() {
log_info "Setting up GCP and GKE cluster..."
if ! confirm "Have you authenticated with GCP? (run: gcloud auth login)"; then gcloud auth login; fi
gcloud config set project "${GCP_PROJECT_ID}"

log_info "Enabling required GCP APIs..."
gcloud services enable container.googleapis.com secretmanager.googleapis.com storage-api.googleapis.com iamcredentials.googleapis.com

if ! gcloud container clusters describe pcp-cluster --region="${GCP_REGION}" &>/dev/null; then
log_info "Creating GKE cluster with Workload Identity and Secret CSI Driver..."
gcloud container clusters create pcp-cluster \
--region="${GCP_REGION}" \
--workload-pool="${GCP_PROJECT_ID}.svc.id.goog" \
--addons=GcpSecretManagerCsiDriver \
--num-nodes=2 \
--machine-type=e2-medium
else
log_success "GKE cluster 'pcp-cluster' already exists."
log_info "Ensuring Secret CSI Driver is enabled..."
gcloud container clusters update pcp-cluster --update-addons=GcpSecretManagerCsiDriver=ENABLED --region="${GCP_REGION}"
fi
gcloud container clusters get-credentials pcp-cluster --region="${GCP_REGION}"
log_success "GCP and GKE setup complete."
}

setup_workload_identity() {
log_info "Setting up Workload Identity..."
GSA_NAME="pcp-sa"
GSA_EMAIL="${GSA_NAME}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
KSA_NAME="pcp-ksa"
NAMESPACE="pcp-prod"

# Create Namespace
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# Create Google Service Account
if ! gcloud iam service-accounts describe ${GSA_EMAIL} &>/dev/null; then
log_info "Creating Google Service Account (GSA): ${GSA_NAME}"
gcloud iam service-accounts create ${GSA_NAME} --display-name="Production Control Plane Service Account"
else
log_success "GSA '${GSA_NAME}' already exists."
fi

# Create Kubernetes Service Account
kubectl create serviceaccount ${KSA_NAME} --namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
log_success "Kubernetes Service Account '${KSA_NAME}' created/verified."

# Bind GSA to KSA
log_info "Binding GSA to KSA for Workload Identity..."
gcloud iam service-accounts add-iam-policy-binding ${GSA_EMAIL} \
--role="roles/iam.workloadIdentityUser" \
--member="serviceAccount:${GCP_PROJECT_ID}.svc.id.goog[${NAMESPACE}/${KSA_NAME}]" \
--quiet

log_success "Workload Identity configured successfully."
}

setup_secrets() {
log_info "Setting up secrets in GCP Secret Manager..."
GSA_EMAIL="pcp-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com"

create_and_grant_secret() {
local secret_name=$1
local secret_value=$2

if gcloud secrets describe "${secret_name}" &>/dev/null; then
log_info "Updating secret: ${secret_name}"
echo -n "${secret_value}" | gcloud secrets versions add "${secret_name}" --data-file=-
else
log_info "Creating secret: ${secret_name}"
echo -n "${secret_value}" | gcloud secrets create "${secret_name}" --data-file=- --replication-policy=automatic
fi

log_info "Granting GSA access to secret: ${secret_name}"
gcloud secrets add-iam-policy-binding "${secret_name}" \
--member="serviceAccount:${GSA_EMAIL}" \
--role="roles/secretmanager.secretAccessor" \
--quiet
}

# Create all required secrets
create_and_grant_secret "notion-token" "${NOTION_TOKEN}"
create_and_grant_secret "mcp-private-key" "$(openssl rand -hex 32)"
create_and_grant_secret "groq-api-key" "${GROQ_API_KEY}"
create_and_grant_secret "mistral-api-key" "${MISTRAL_API_KEY}"
create_and_grant_secret "google-doc-id" "${GOOGLE_DOC_ID}"
# Add any other secrets here

log_warning "The local Kubernetes secret 'pcp-secrets' is no longer used. All secrets are now managed in GCP."
log_success "GCP secrets setup complete."
}

main() {
check_prerequisites
setup_configuration
setup_gcp_cluster
setup_workload_identity
setup_secrets
log_success "🎉 Production Control Plane setup is complete!"
log_info "You can now deploy the applications using: kubectl apply -f infrastructure/gcp-deployment.yml"
}

main
