# Usable geographic demonstrations

Open **Open AliveMap Maps.cmd**. The geographic viewer replaces the earlier blurry
static background as the main presentation. Existing SUMO, routing and MEC code
still drives the experiment; the map does not animate invented positions.

## Play a guided demonstration

### Compare without and with an incident

1. Choose a map/subregion and click **Run without incident**. This uses the same
   trips, profiles and seed with no automatic hazard reports. Let it finish to
   record the reference arrival times in the comparison line above the map.
2. Choose **Congestion**, **Flood (0.25 m)** or **Landslide / road closure**, then
   click **Run with incident**. A fresh experiment uses identical seeded trips.
   The chosen incident is reported at **20 simulated seconds** and remains active
   until you explicitly click **Clear incident**; there is no automatic escalation
   into another incident type or automatic 100-second clearance in these runs.
3. **Pause to inspect each route change** is on by default. The controller pauses
   when a real new route or no-feasible-route decision occurs. Inspect the inset,
   route counter and event log, then press **Resume** to drive the new route.
   Uncheck it for continuous playback; the setting also works during a run.
4. **Apply selected** injects the selected incident immediately into the current
   run. A reference run that receives a manual incident is relabelled `manual:…`
   and cannot be recorded as the no-incident baseline. Clear removes this run's
   incident; independent vehicles recompute their routes again.

The comparison retains completed reference times within the current application
session. Run changes create new UUIDs and never mix remote hazard records. A
profile may retain its route if that is still cheapest; a closure may leave no
feasible route. Such a stop is displayed separately and is **not** counted as a
successful reroute. Changing a past road after a vehicle has passed it does not
force a fictional detour.

The large **SIM** clock displays actual elapsed SUMO time, including half-second
steps. **WALL** is real elapsed time since the scenario loaded, including pauses.
During a pause SIM freezes while WALL continues. Requested and measured playback
rates remain distinct. Reset creates the same selected case paused; Resume still
arms its scheduled incident. The older command-line acceptance runs retain their
original timeline unless explicitly configured otherwise.

### Route inset

The box in the map's bottom-left corner is a fixed network overview:

- Light grey: actual passenger-accessible canonical OSM/SUMO road geometry.
- Solid vehicle color: the current planned trip and the roads already driven.
- Dashed vehicle color: earlier plans retained at actual semantic route changes.
- Dots: live vehicle positions; red square: the semantic incident location.
- `STOP`: no feasible route. Its old plan remains dashed; it is not displayed as
  a valid new intended route while the vehicle is stopped.

The frame stays fixed while the main view follows a vehicle. It expands only if
a computed detour leaves its bounds. Double-click to enlarge/shrink the inset.
Shared solid routes have small drawing offsets so vehicle colors do not hide one
another. Old dashes remain above solids where an old path shares a road with
another vehicle's current path. These are display styles, not changed geography.

### One-click map presets

Click one of the four **Play guided demo** buttons:

- Delhi congestion: same semantic traffic fact, different vehicle cost policies.
- Gujarat flood: different vehicle water-depth tolerances.
- Mantripukhri landslide: a real-road closure and computed detour.
- Mayangkhang closure: a corridor with no feasible detour; clear the incident to
  let the stopped vehicle proceed.

Each button uses its existing validated map/scenario, creates a fresh epoch,
spawns the fleet, starts playback and follows Blue at street scale. The narration
and event history show reports, acknowledgements, semantic snapshots and decisions.
No alternate route list is preprogrammed. Existing offline map assets must have
been built; see `map-system.md` for another machine.

**Local demo (no SSH)** is selected by default so a demonstration starts without
passwords or network setup. It uses the inspected API implementation locally,
through its real FastAPI contract. It is visibly labelled LOCAL DEMO API and is
not evidence of physical MEC processing. Select **Physical MEC (SSH)** before
starting a demo to use the original forwarded physical API. Connection failures
pause that mode; it never silently falls back to local. Existing physical-MEC
verification remains separate in `evidence/maps/`.

## Map, vehicles and time

- **Blue / Orange / Green** center and continuously follow that vehicle, with its
  current intended route shown in its color. These positions are read from TraCI.
- Solid colored circles with direction arrows are active vehicles. Grey markers
  are explicitly queued spawn positions, not moving vehicles. Hollow destination
  markers say **arrived** after a vehicle leaves SUMO.
- **All routes / overview** fits OD locations and shows routes for active vehicles.
  Dragging pans freely; select a vehicle again to resume following.
- Mouse wheel and **+ / −** load new map tiles at the selected zoom, rather than
  enlarging one fixed satellite image. The layer's supported maximum is enforced.
- **Time speed** sets targets from 1x to 100x (default 20x). High speeds batch
  ordinary 0.5-second SUMO steps, preserving event ordering and collision checks.
  **Step** always advances just one step. The display distinguishes target from
  measured rate; computer performance and remote HTTP latency affect the latter.
- **Pause / Resume / Reset** and manual **Incident / Close / Clear** remain usable.
  A manual report turns off that run's automatic incident timeline.
- **Also open native SUMO window** opens the diagnostic simulator view on the next
  load. The AliveMap map remains connected to the same actual vehicle states.

## Streets, terrain and road provenance

**Streets** uses OpenStreetMap's public interactive tiles, with attribution,
identified requests and response caching. **Terrain** uses OpenTopoMap's shaded
relief/contour tiles (OSM + SRTM, CC-BY-SA). Both were fetched and checked locally.
Only visible tiles are requested, not bulk/offline downloads. Availability depends
on the public services and internet connection. If background tiles are unavailable,
the viewer draws the actual cached OSM-derived SUMO road geometry with vehicle
and route overlays; it labels this fallback.

The selected vehicle's road name and **OSM way IDs** appear below the map. These
come from the original downloaded OSM extract and canonical converted network.
Roads are not hand drawn. The display uses Web Mercator only for placing map
tiles; canonical UTM coordinates and routing data remain unchanged.

The elevation chart uses valid **Copernicus GLO-30 DSM** road samples from the
package. OpenTopoMap relief is a separate SRTM-based context layer, not a change
to routing elevations. Neither source is a surveyed lane-height model. No-data
samples are excluded. There is no claim of 3D buildings or Google Earth terrain.

## Satellite: why the original view blurred, and how to add a source

The earlier background was one approximately 10 m/pixel Sentinel-2 raster.
Zooming cannot recover sub-metre road/vehicle detail from it. Making the area
smaller also cannot create that missing detail. The current default therefore
prioritizes sharp streets and terrain, as requested. High-resolution satellite
has not been enabled without an appropriate provider credential; no upscaled
Sentinel image is presented as high-resolution imagery.

Possible accounts with free keys or usage allowances:

- [ArcGIS Location Platform](https://developers.arcgis.com/pricing/): check the
  free allowance and enable basemap access on the credential.
- [MapTiler API keys](https://docs.maptiler.com/guides/developer/credentials/api-key/):
  creating a key is free. Check satellite entitlement/resolution for the plan and
  the actual location; a key alone does not guarantee sharper imagery.
- [Mapbox signup](https://docs.mapbox.com/accounts/guides/signup/): usage allowances
  apply; signup may require a payment card. Its documented satellite raster
  endpoint works with this viewer's configurable tile interface.

Once a provider is chosen, create the ignored file `.local/map-provider.json`.
For example, with a Mapbox public access token and licensed satellite access:

```json
{
  "Satellite": {
    "url": "https://api.mapbox.com/v4/mapbox.satellite/{z}/{x}/{y}.jpg90?access_token=YOUR_LOCAL_TOKEN",
    "attribution": "© Mapbox © OpenStreetMap contributors; imagery attribution per provider",
    "max_zoom": 19
  }
}
```

Restart the viewer; the layer appears under **Map layer**. Provider requests use
HTTPS, keys remain in ignored local settings, and custom-provider tiles are kept
in memory rather than exported to a persistent offline cache. Retain the required
provider attribution and respect its account limits. The template mechanism is
implemented and tested with generated tiles; keyed satellite access itself has
not been verified because no user credential has been supplied.

Source references: [OSM tile policy](https://operations.osmfoundation.org/policies/tiles/),
[OpenTopoMap](https://www.opentopomap.org/about),
[Mapbox Satellite raster template](https://docs.mapbox.com/data/tilesets/reference/mapbox-satellite/).
