#!/usr/bin/env bash
# Set Chrome Web Store API secrets on every extension repo in one go.
#
# One OAuth client + refresh token for the CWS publisher works for every item it
# owns, so the same three values go to each repo; only the extension ID differs.
# Values are read with hidden input and passed to `gh secret set` on stdin, so
# they never appear in shell history or on the command line.
#
# Usage (from ~/git-personal so .envrc selects the personal GitHub account):
#   direnv exec . .github-workflows-shared/scripts/set-cws-secrets.sh
set -euo pipefail

OWNER="ravitejakamalapuram"

# repo  secret-prefix  extension-id-secret=id [...]
# StellarTab and TeluguPanchangam CD reads CHROME_* names; the rest read CWS_*.
REPOS=(
  "echokit CWS CWS_EXTENSION_ID=jndhbmaokpclbpjoogffaimahadpidcf"
  "json-workbench CWS CWS_EXTENSION_ID=higmlhleblpmdogjccpmjlnilpmhohal"
  "cors-enabler CWS CWS_EXTENSION_ID=bfegjbdhenoahnnajgmlkcdkfcjgnjjc"
  "session-transfer CWS CWS_EXTENSION_ID=fnfmlchbfofjdfeibgdkcibfjjlfcefc"
  "GitaVerses CWS CWS_EXTENSION_ID=hebmlallhbgfnjjcnilphllknhfoddnk"
  "StellarTab CHROME CHROME_EXTENSION_ID=efpigokkcblmjdnameafogblekknbhdc"
  "TeluguPanchangam CHROME CHROME_EXTENSION_ID=obgpdlhkahmdiepklldjnnmfmbhmgenn"
)

login=$(gh api user --jq .login)
if [ "$login" != "$OWNER" ]; then
  echo "gh is using '$login', not '$OWNER'. Run this from ~/git-personal via 'direnv exec .'." >&2
  exit 1
fi

read -r -p  "CWS OAuth client ID: " CLIENT_ID
read -r -s -p "CWS OAuth client secret: " CLIENT_SECRET; echo
read -r -s -p "CWS refresh token: " REFRESH_TOKEN; echo
[ -n "$CLIENT_ID" ] && [ -n "$CLIENT_SECRET" ] && [ -n "$REFRESH_TOKEN" ] || { echo "All three values are required." >&2; exit 1; }

# Fail fast on a bad or expired refresh token before touching any repo.
if ! curl -sS --fail -o /dev/null https://oauth2.googleapis.com/token \
     --data-urlencode client_id="$CLIENT_ID" --data-urlencode client_secret="$CLIENT_SECRET" \
     --data-urlencode refresh_token="$REFRESH_TOKEN" -d grant_type=refresh_token; then
  echo "Google rejected these credentials (wrong secret, or refresh token expired/revoked). Nothing was changed." >&2
  exit 1
fi
echo "Credentials verified with Google."

for entry in "${REPOS[@]}"; do
  read -r repo prefix ids <<<"$entry"
  printf '%s' "$CLIENT_ID"     | gh secret set "${prefix}_CLIENT_ID"     -R "$OWNER/$repo"
  printf '%s' "$CLIENT_SECRET" | gh secret set "${prefix}_CLIENT_SECRET" -R "$OWNER/$repo"
  printf '%s' "$REFRESH_TOKEN" | gh secret set "${prefix}_REFRESH_TOKEN" -R "$OWNER/$repo"
  for pair in $ids; do
    printf '%s' "${pair#*=}" | gh secret set "${pair%%=*}" -R "$OWNER/$repo"
  done
  echo "✓ $repo"
done
echo "Done. Publishing is on demand: Actions → CD → Run workflow in each repo."
