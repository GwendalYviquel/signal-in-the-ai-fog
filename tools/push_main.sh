#!/usr/bin/env bash
# Pushes the workflow's commit to main, even when another show's run pushed first.
# The files shared by every show (.gitattributes, merge=shared) never conflict: the
# pull keeps main's copy, and they are rebuilt here from the data of every show.
# Usage: tools/push_main.sh   (after git commit, from the repository root)
set -euo pipefail
for attempt in 1 2 3; do
  git -c merge.shared.driver=true pull --rebase origin main
  python -m engine.overview >/dev/null
  python -c "from engine import site; site.write_shared()"
  git add shows/COSTS.md shows/costs-dashboard-*.svg shows/STATS.md shows/usage-dashboard-*.svg docs/index.html docs/i18n.json
  git diff --cached --quiet || git commit -m "Reports shared by every show"
  git push && exit 0
  echo "main moved during the push (attempt $attempt): pulling again"
done
exit 1
