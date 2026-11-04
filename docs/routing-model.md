# Vehicle routing and incident model

This guide describes the equations in `routing_core/agents.py` and the policies
in `mec/playground_api.py`. They are research policies, not calibrated driving
or road-safety models.

## Graph and route search

The search states are SUMO road edges. A successor must be a legal outgoing
connection for the selected vehicle class. Source OSM direction and permissions
are retained during conversion. The planner checks incident polygons against
projected road geometry; H3 narrows spatial searches but does not replace exact
intersection.

For a transition from the current edge to its successor, the added cost is:

```text
base travel time = successor length / successor speed
connector time  = distance between edge endpoints / map maximum speed
cost increment = base travel time + connector time
               + incident penalties + uphill gain × uphill weight
```

The initial edge starts at cost zero, so returned costs represent this
edge-transition objective, not a complete measured origin-to-destination ETA.
A* estimates remaining cost as straight-line distance to the destination edge's
end divided by the map maximum speed. Disabling the heuristic gives the
Dijkstra comparison used by tests. Successful routes pass the directed graph
validator and are checked again when applied to SUMO.

## Semantic effects

- **Congestion:** add `base travel time × (1 / speed ratio − 1) × congestion weight`
  for each applicable observation. A ratio of 1 adds no penalty.
- **Flood:** prohibit an edge above the profile's maximum water depth; otherwise
  add `water depth × water-risk weight` for each applicable observation.
- **Landslide/closure:** prohibit intersecting successor edges.
- **Grade:** prohibit edges whose available maximum absolute grade exceeds the
  profile limit. Missing grade is not replaced by a fabricated measurement.
- **Clear/expired fact:** does not contribute an active routing penalty.

Overlapping active observations can accumulate penalties. Facts must belong to
the same map, and the session supplies only the vehicle's delivered knowledge.
An incident does not globally replace every vehicle's knowledge or SUMO's road
speed. A vehicle can therefore continue on a route if it has not received a
fact, has a different policy, or has already passed a useful turning point.

## Default profiles

All current profiles use passenger-class permissions and a maximum grade of 0.25.

| Profile | Congestion weight | Maximum depth (m) | Water penalty (s/m) | Uphill penalty (s/m gained) |
| --- | ---: | ---: | ---: | ---: |
| `time_sensitive` | 3.0 | 0.15 | 50 | 0.10 |
| `distance_focused` | 0.03 | 0.50 | 5 | 0 |
| `low_clearance` | 1.0 | 0.15 | 50 | 0.20 |
| `high_clearance` | 1.0 | 0.50 | 5 | 0.05 |

`distance_focused` is the existing low-congestion-sensitivity policy over a
travel-time objective; it is not a pure shortest-distance solver. Colour is a
display identifier, not an algorithm or a fixed route.

If no valid route remains, the planner returns no route with infinite cost.
The session records the blocked state and stops that vehicle. It does not insert
an arbitrary detour. Route-history graphics show solid current geometry and
dashes only for retired contiguous sections absent from the new route.

## Observation and assessment

The scene defines synthetic ground-truth geometry and sensor reach. Reporters
encounter that geometry through actual SUMO movement. Ground truth is distinct
from a fact accepted by MEC. Saving an area does not immediately make every
vehicle aware of it; Publish is an explicit operator-injection path.

MEC derives severity from the incident facts, counts distinct reporting vehicles,
and returns relevant facts according to simulated tower coverage and spatial
relevance. The exact thresholds and version rules are in
[the typed API reference](playground-api.md). These assessment rules do not
choose a route. Simulation time drives motion; wall-clock time drives expiry.
