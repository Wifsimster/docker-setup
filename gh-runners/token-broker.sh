#!/usr/bin/env bash
# Seul détenteur du PAT. Toutes les 30 min, pour chaque repo de BROKER_REPOS :
#   1. vérifie que le repo est PRIVÉ (sinon : supprime le token et refuse) ;
#   2. demande un token d'enregistrement de runner (valide 1 h) ;
#   3. l'écrit dans /tokens/<repo>/token, seul fichier visible du runner.
# Le PAT n'est jamais écrit ailleurs ni affiché.
set -uo pipefail

PAT_FILE=/run/secrets/github_pat
API=https://api.github.com
INTERVAL=${BROKER_INTERVAL:-1800}

[[ -s "$PAT_FILE" ]] || { echo "broker: $PAT_FILE vide ou absent" >&2; exit 1; }

gh_api() {
  curl -fsS --max-time 20 \
    -H "Authorization: Bearer $(<"$PAT_FILE")" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "$@"
}

refresh() {
  local repo=$1 dir=/tokens/$1 private token
  private=$(gh_api "$API/repos/$GITHUB_OWNER/$repo" | jq -r '.private') || {
    echo "broker: $repo — lecture du repo impossible" >&2; return 1; }
  if [[ "$private" != "true" ]]; then
    rm -f "$dir/token"
    echo "broker: $repo n'est pas privé — aucun token émis, runner bloqué" >&2
    return 1
  fi
  token=$(gh_api -X POST "$API/repos/$GITHUB_OWNER/$repo/actions/runners/registration-token" \
    | jq -r '.token') || { echo "broker: $repo — token refusé (droits du PAT ?)" >&2; return 1; }
  [[ -n "$token" && "$token" != "null" ]] || return 1
  umask 077
  printf '%s' "$token" > "$dir/token.tmp" && mv -f "$dir/token.tmp" "$dir/token"
  echo "broker: $repo — token renouvelé"
}

while true; do
  for repo in $BROKER_REPOS; do refresh "$repo"; done
  sleep "$INTERVAL"
done
