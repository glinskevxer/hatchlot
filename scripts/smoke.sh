#!/usr/bin/env bash
# Runs the command line against a throwaway database, the way a station would on
# its first morning. Every command here has to work off a plain `pip install`
# with no test dependencies, which is the thing this catches and the unit tests
# do not.
set -euo pipefail

DB="$(mktemp -d)/station.sqlite3"
trap 'rm -f "$DB"' EXIT

step() {
  echo "--- $*"
  "$@"
}

step hatchlot --version
step hatchlot --database "$DB" station init --code cold-creek --name "Cold Creek"
step hatchlot --database "$DB" station add-source \
  --code sp-1 --name "upper spring" --flow 900 --minimum 600
step hatchlot --database "$DB" station add-unit \
  --code rw-1 --length 30 --width 3 --depth 1 --flow 450 --source sp-1
step hatchlot --database "$DB" lot pond \
  --code 2024-CHK-01 --unit rw-1 --day 2025-01-15 --fish 40000 --weight 2.5
step hatchlot --database "$DB" feed record \
  --lot 2024-CHK-01 --day 2025-03-01 --amount 22 --feed-lot FL-001
step hatchlot --database "$DB" lot mortality \
  2024-CHK-01 --day 2025-03-05 --count 500 --reason "screen failure overnight"
step hatchlot --database "$DB" water record \
  --unit rw-1 --at "2025-03-05 06:00" --temperature 10 --oxygen 9.1
step hatchlot --database "$DB" lot show 2024-CHK-01
step hatchlot --database "$DB" lot reconcile
step hatchlot --database "$DB" report production --from 2025-03-01 --to 2025-03-31
step hatchlot --database "$DB" calc loading \
  --species chinook --flow 450 --volume 3178 --weight 2.5
step hatchlot --database "$DB" doctor

echo "smoke test passed"
