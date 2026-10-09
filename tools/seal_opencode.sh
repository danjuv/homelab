#!/usr/bin/env bash
# Seal the OpenCode agent's credentials into k8s/apps/opencode/opencode.sealed.yaml
# (ciphertext only). Plaintext is never written to disk or passed through
# arguments or environment variables.
#
# Secret opencode/opencode-secrets:
#   OPENROUTER_API_KEY   model provider
#   username, password   git-init clone credentials (password = GitHub PAT);
#                        the PAT is also the agent's GH_TOKEN for push and PRs
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

out="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)/k8s/apps/opencode/opencode.sealed.yaml"
trap 'printf "Failed to generate the OpenCode SealedSecret.\n" >&2' ERR

certificate=""
if [[ -z "$cert" ]]; then
  # Keep the public certificate in memory and pass it through a file descriptor.
  certificate="$(kubeseal --fetch-cert --controller-name helm-sealed-secrets \
    --controller-namespace kube-system --request-timeout=10s)"
  cert=/dev/fd/3
fi

read -r -s -p 'OpenRouter API key: ' openrouter
printf '\n' >&2
read -r -s -p 'GitHub fine-grained PAT (danjuv/homelab: Contents RW, Pull requests RW): ' github
printf '\n' >&2
if [[ -z "$openrouter" || -z "$github" ]]; then
  printf 'Both values must be nonempty.\n' >&2
  exit 1
fi

# Only base64 strings are interpolated into JSON, so special characters cannot
# alter its structure. printf is a Bash builtin, so values only reach external
# programs through stdin.
b64() { printf '%s' "$1" | base64 | tr -d '\n'; }
openrouter_data="$(b64 "$openrouter")"
github_data="$(b64 "$github")"
username_data="$(b64 x-access-token)"
unset openrouter github

printf '{"apiVersion":"v1","kind":"Secret","type":"Opaque","metadata":{"name":"opencode-secrets","namespace":"opencode"},"data":{"OPENROUTER_API_KEY":"%s","username":"%s","password":"%s"}}\n' \
  "$openrouter_data" "$username_data" "$github_data" \
  | kubeseal --cert "$cert" --scope strict --format yaml \
    3< <(printf '%s\n' "$certificate") > "$out"
unset openrouter_data github_data username_data certificate
printf 'Wrote %s\n' "${out#"$(git rev-parse --show-toplevel)/"}" >&2
