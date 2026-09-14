#!/usr/bin/env bash
# BasePilot release stats. Usage: bash tools/release_stats.sh
# Requires the GitHub CLI (gh auth login). Traffic needs push access to the repo.
set -u
REPO="${1:-efebolukbasi/BasePilot}"

echo "=== $REPO ==="
gh repo view "$REPO" --json stargazerCount,forkCount,watchers \
  --jq '"stars: \(.stargazerCount)   forks: \(.forkCount)   watchers: \(.watchers.totalCount)"'

echo
echo "--- downloads per release asset (all time) ---"
gh api "repos/$REPO/releases" --paginate \
  --jq '.[] | "\(.tag_name)  published \(.published_at[0:10])\n" +
        ([.assets[] | "    \(.name)  \(.download_count) downloads"] | join("\n"))'

TOTAL=$(gh api "repos/$REPO/releases" --paginate --jq '[.[].assets[].download_count] | add // 0')
echo
echo "TOTAL DOWNLOADS: $TOTAL"

echo
echo "--- traffic (rolling 14 days) ---"
gh api "repos/$REPO/traffic/views" --jq '"views:  \(.count) total, \(.uniques) unique"' 2>/dev/null \
  || echo "views:  unavailable (needs push access)"
gh api "repos/$REPO/traffic/clones" --jq '"clones: \(.count) total, \(.uniques) unique"' 2>/dev/null \
  || echo "clones: unavailable"

echo
echo "--- top referrers (where visitors came from) ---"
gh api "repos/$REPO/traffic/popular/referrers" \
  --jq '.[] | "    \(.referrer)  \(.count) views, \(.uniques) unique"' 2>/dev/null \
  || echo "    unavailable"
