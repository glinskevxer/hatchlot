# hatchlot

Production accounting for a coldwater salmonid hatchery.

A hatchery takes eggs from broodstock, incubates them on a water temperature
nobody controls, rears the fish through a year or more of raceways and feed,
marks them so they can be told apart later, and hands them to whoever manages
the water they go into. Every step is a number somebody has to defend: the egg
count off a spawn take, the loading a raceway is allowed to carry, the
withdrawal period on a medicated feed, the tag code on a release group.

`hatchlot` is the register those numbers land in, and the engine that decides
whether a lot can be moved, fed, treated, marked or released.

It is a command line tool over a SQLite file. No server, no web UI.

## Install

    pip install -e ".[dev]"

## Getting started

Set a station up, put some water and a raceway on it, and pond a lot:

    hatchlot -d station.sqlite3 station init --code cold-creek --name "Cold Creek"
    hatchlot -d station.sqlite3 station add-source \
        --code sp-1 --name "upper spring" --flow 900 --minimum 600
    hatchlot -d station.sqlite3 station add-unit \
        --code rw-1 --length 30 --width 3 --depth 1 --flow 450 --source sp-1
    hatchlot -d station.sqlite3 lot pond \
        --code 2024-CHK-01 --unit rw-1 --day 2025-01-15 --fish 40000 --weight 2.5

Then feed it, record what died, and print the month:

    hatchlot -d station.sqlite3 feed record \
        --lot 2024-CHK-01 --day 2025-03-01 --amount 22 --feed-lot FL-001
    hatchlot -d station.sqlite3 lot mortality \
        2024-CHK-01 --day 2025-03-05 --count 500 --reason "screen failure overnight"
    hatchlot -d station.sqlite3 report production --from 2025-03-01 --to 2025-03-31

`hatchlot commands` lists everything the tool can do. Every listing takes
`--format csv` so it can go straight into a spreadsheet.

## The sums, without a database

Most of the daily arithmetic needs nothing stored:

    hatchlot calc loading --species chinook --flow 450 --volume 3178 --weight 2.5
    hatchlot calc ration --biomass 1000 --weight 2.5 --water 10
    hatchlot incubate schedule --species chinook --spawned 2024-09-13 --water 10
    hatchlot health treatment --chemical formalin --concentration 167 \
        --minutes 60 --water 10 --flow 500

## What is in it

| area | what it covers |
| --- | --- |
| `water` | sources and blends, dissolved oxygen, gas, chemistry, thermal units, carrying capacity |
| `brood` | broodstock, fecundity, egg counting, crosses, pedigree, pathogen screening, spawn takes |
| `incubation` | egg lots, degree day milestones, picking, shocking, trays and jars, movements |
| `rearing` | containers, lots, the movement ledger, mortality, sampling, loading, cleaning |
| `growth` | thermal growth model, projection to a date or a size, size grading |
| `feed` | feed lots, the store, feeding rate tables, conversion, medicated feed and withdrawals |
| `health` | examinations, treatments, cases, biosecurity zones |
| `marking` | marks and tag codes, marking runs, quality checks, retention |
| `distribution` | stocking requests, allocation, hauls, releases |
| `permits` | discharge limits, monitoring, period reports, feed based effluent estimates |
| `ingest` | vendor file profiles, reading, deduplication |
| `store` | SQLite schema, migrations, repositories |
| `reporting` | tables, lot history, production and compliance reports, CSV export |

## Exit codes

Zero is fine. Two is the station saying no: a validation error, a rule refusing,
a record that is not there. Anything else is a bug, and it comes with a
traceback.

## Checking a database

    hatchlot -d station.sqlite3 doctor

Exits two if anything wants a look, so it can go in a cron job.

## Development

    ruff check . && ruff format --check .
    mypy
    pytest -q --cov=hatchlot --cov-fail-under=90
