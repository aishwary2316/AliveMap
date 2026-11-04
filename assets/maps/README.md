# Delhi starter road snapshot

`delhi_urban.osm.xml.gz` contains a bounded, real OpenStreetMap road extract.
It is an OpenStreetMap-derived database, © OpenStreetMap contributors,
available under the [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
Source and attribution: [OpenStreetMap copyright](https://www.openstreetmap.org/copyright).
These terms apply to the geographic database independently of project code.

The adjacent `delhi_urban.json` records the original Overpass query, footprint,
acquisition time, source attribution and SHA-256 checksums. Contributor/edit
metadata attributes were removed; road IDs, coordinates, tags and turn
restrictions remain. The XML also carries the database attribution/license URI.

This approximately 0.53 MB compressed snapshot makes the default setup independent
of live Overpass availability. SUMO conversion, H3 indexing, scenario discovery
and independent vehicle routing still run locally. It contains no preselected
detour, synthetic road network, satellite image or stored simulation outcome.
Generated full map packages remain outside Git.

Use `Setup.ps1 -RefreshMaps` to request current road data instead. A source
refresh can legitimately change the generated network, scenario and timings.
