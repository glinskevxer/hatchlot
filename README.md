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

## Use

    hatchlot --help
