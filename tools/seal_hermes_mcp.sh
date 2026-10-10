#!/usr/bin/env bash
# Seal bearer tokens for Hermes' MCP servers (k8s/apps/hermes/values.yaml
# config.values.mcp_servers). Prompts for each token and writes ciphertext only:
#   k8s/apps/hermes/hermes-mcp.sealed.yaml   hermes/hermes-mcp
#     HINDSIGHT_API_KEY   Hindsight "homelab" tenant API key
#     GITHUB_MCP_TOKEN    GitHub PAT for api.githubcopilot.com/mcp/readonly
# Plaintext is never written to disk or passed through arguments or
# environment variables. Bump hermes.home.lab/credentials-revision afterwards.
set -euo pipefail
set +x
umask 077

cert=""
case "${1:-}" in
  --help|-h)
    printf 'Usage: bash %s [--cert CONTROLLER_PUBLIC_CERT]\n' "$0"
    exit 0
    ;;
  --cert)
    if [[ $# != 2 || -z "$2" ]]; then
      printf 'Expected --cert followed by a controller public certificate.\n' >&2
      exit 1
    fi
    cert="$2"
    ;;
  "") ;;
  *)
    printf 'Unknown argument: %s\n' "$1" >&2
    exit 1
    ;;
esac

repo="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
trap 'printf "Failed to generate the Hermes MCP SealedSecret.\n" >&2' ERR

certificate=""
if [[ -z "$cert" ]]; then
  certificate="$(kubeseal --fetch-cert --controller-name helm-sealed-secrets \
    --controller-namespace kube-system --request-timeout=10s)"
  cert=/dev/fd/3
fi

prompt_b64() {
  local value
  IFS= read -rs -p "$1: " value
  printf '\n' >&2
  if [[ -z "$value" ]]; then
    printf '%s must not be empty.\n' "$1" >&2
    exit 1
  fi
  printf '%s' "$value" | base64 | tr -d '\n'
}

hindsight="$(prompt_b64 HINDSIGHT_API_KEY)"
github="$(prompt_b64 GITHUB_MCP_TOKEN)"

printf '{"apiVersion":"v1","kind":"Secret","type":"Opaque","metadata":{"name":"hermes-mcp","namespace":"hermes"},"data":{"HINDSIGHT_API_KEY":"%s","GITHUB_MCP_TOKEN":"%s"}}\n' \
  "$hindsight" "$github" \
  | kubeseal --cert "$cert" --scope strict --format yaml 3< <(printf '%s\n' "$certificate") \
  > "$repo/k8s/apps/hermes/hermes-mcp.sealed.yaml"
unset hindsight github certificate
printf 'Wrote k8s/apps/hermes/hermes-mcp.sealed.yaml\n' >&2
