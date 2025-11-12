# Changelog

## 1.0.0

The first release the station's records are kept in rather than checked against.

Everything a coldwater salmonid hatchery counts, in one package: water and what
is dissolved in it, broodstock and spawning, incubation on thermal units,
rearing with a movement ledger that reconciles, growth, feed and medicated feed,
fish health, marking and tag codes, distribution and release, and discharge
permits. A SQLite store with hand rolled migrations behind it, a file importer
in front of it, and a command line over the whole thing.

### The rules that refuse

Thirty seven of them, listed by `hatchlot rules`. The ones worth naming here are
the ones that catch a real mistake rather than a typo: eggs cannot be handled
inside the tender window, a lot cannot be released inside a drug withdrawal
counted in degree days, a raceway cannot be loaded past whichever of its three
limits binds first, and a marking run is not finished until a sample has been
checked.

### Known limits

- One station per database. Nothing stops two, and nothing joins them either.
- The feeding chart and the oxygen solubility table are the standard ones,
  interpolated between rows. A station with its own should pass its own.
- The fecundity and growth models are fitted from a station's own numbers or
  they are guesses with a documented shape.
- Reports print plain text and export CSV. There is no PDF and no server.
