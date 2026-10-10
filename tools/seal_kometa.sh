#!/usr/bin/env bash
# Seal Kometa's credentials (k8s/apps/kometa/values.yaml). Prompts for each
# value, runs the MyAnimeList OAuth exchange, and writes ciphertext only:
#   k8s/apps/kometa/sealedsecret.yaml   media/kometa
#     KOMETA_PLEX_TOKEN         Plex server admin token (X-Plex-Token)
#     KOMETA_TMDB_APIKEY        TMDb v3 API key (Kometa requires it for ID mapping)
#     KOMETA_MAL_CLIENT_ID      MyAnimeList API client (https://myanimelist.net/apiconfig,
#     KOMETA_MAL_CLIENT_SECRET    App Type "web", Redirect URL http://localhost/)
#     KOMETA_MAL_ACCESS_TOKEN   Bootstrap OAuth tokens. Kometa refreshes them and
#     KOMETA_MAL_REFRESH_TOKEN    keeps the new ones on its PVC; rerun to re-auth.
# Plaintext is never written to disk or passed through arguments or
# environment variables. The CronJob picks the new Secret up on its next run.
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

for tool in kubeseal curl jq; do
  command -v "$tool" >/dev/null || { printf '%s is required.\n' "$tool" >&2; exit 1; }
done

repo="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
trap 'printf "Failed to generate the Kometa SealedSecret.\n" >&2' ERR

certificate=""
if [[ -z "$cert" ]]; then
  certificate="$(kubeseal --fetch-cert --controller-name helm-sealed-secrets \
    --controller-namespace kube-system --request-timeout=10s)"
  cert=/dev/fd/3
fi

# prompt NAME REGEX -> prints the raw value
prompt() {
  local value
  IFS= read -rs -p "$1: " value
  printf '\n' >&2
  if [[ ! "$value" =~ $2 ]]; then
    printf '%s does not look right (expected %s).\n' "$1" "$2" >&2
    exit 1
  fi
  printf '%s' "$value"
}

b64() { printf '%s' "$1" | base64 | tr -d '\n'; }

plex="$(prompt KOMETA_PLEX_TOKEN '^[A-Za-z0-9_-]{20,}$')"
tmdb="$(prompt KOMETA_TMDB_APIKEY '^[0-9a-f]{32}$')"
mal_id="$(prompt KOMETA_MAL_CLIENT_ID '^[0-9a-f]{32}$')"
mal_secret="$(prompt KOMETA_MAL_CLIENT_SECRET '^[0-9a-f]{32,128}$')"

# MAL only supports the PKCE "plain" method: challenge == verifier.
verifier="$(head -c 96 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n' | cut -c1-128)"
printf '\nOpen this URL, click Allow, then copy the http://localhost/?code=... URL\n' >&2
printf 'from the address bar (the page itself will fail to load):\n\n' >&2
printf '  https://myanimelist.net/v1/oauth2/authorize?response_type=code&client_id=%s&code_challenge=%s\n\n' \
  "$mal_id" "$verifier" >&2
redirect="$(prompt 'Redirected URL' 'code=[^&]+')"
[[ "$redirect" =~ code=([^&]+) ]]
code="${BASH_REMATCH[1]}"

tokens="$(printf 'client_id=%s&client_secret=%s&code=%s&code_verifier=%s&grant_type=authorization_code' \
    "$mal_id" "$mal_secret" "$code" "$verifier" \
  | curl -sS --fail-with-body --data-binary @- \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    https://myanimelist.net/v1/oauth2/token)" || {
  printf 'MyAnimeList token exchange failed: %s\n' "$(jq -r '.message // .error // .' <<<"$tokens" 2>/dev/null)" >&2
  exit 1
}
mal_access="$(jq -er '.access_token' <<<"$tokens")"
mal_refresh="$(jq -er '.refresh_token' <<<"$tokens")"
unset tokens code verifier redirect

printf '{"apiVersion":"v1","kind":"Secret","type":"Opaque","metadata":{"name":"kometa","namespace":"media"},"data":{"KOMETA_PLEX_TOKEN":"%s","KOMETA_TMDB_APIKEY":"%s","KOMETA_MAL_CLIENT_ID":"%s","KOMETA_MAL_CLIENT_SECRET":"%s","KOMETA_MAL_ACCESS_TOKEN":"%s","KOMETA_MAL_REFRESH_TOKEN":"%s"}}\n' \
  "$(b64 "$plex")" "$(b64 "$tmdb")" "$(b64 "$mal_id")" "$(b64 "$mal_secret")" \
  "$(b64 "$mal_access")" "$(b64 "$mal_refresh")" \
  | kubeseal --cert "$cert" --scope strict --format yaml 3< <(printf '%s\n' "$certificate") \
  > "$repo/k8s/apps/kometa/sealedsecret.yaml"
unset plex tmdb mal_id mal_secret mal_access mal_refresh certificate
printf 'Wrote k8s/apps/kometa/sealedsecret.yaml\n' >&2
