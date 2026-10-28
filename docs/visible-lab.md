# See and control AliveMap

From the project folder, double-click **Open AliveMap Lab.cmd**, or run:

```powershell
.\.venv\Scripts\python.exe -m laptop.lab
```

Keep both existing SSH windows open. The lab uses the original physical MEC API
through laptop port 18765 and its deployed semantic view through port 18766.
It opens two native windows: **AliveMap — Live MEC Routing Lab** and the detailed
**SUMO** viewer. Use the AliveMap window's timing controls. It starts paused at
0.5 simulated seconds, after the four vehicles have entered the network.

## First experiment

1. While paused, click **Warning**. The physical MEC acknowledges the report;
   the blue vehicle computes a detour. Orange keeps its original route because
   its warning penalty is zero. Both responses appear in the explanation log.
2. Click **Play** to watch actual SUMO vehicles move. **Pause** holds time;
   **Step +0.5 s** advances one simulator step. The slider changes the pause
   between steps; network requests can add further delay.
3. Click **Close road**. Orange must now compute a route excluding that road.
   Blue may already be on a detour. Each vehicle plans from its own current edge.
4. Click **Clear road**. They recompute shortest routes from where they are now.
   A vehicle already past the decision point may keep its current route.
5. **Reset / manual** opens a fresh paused scenario. It clears this run's own
   outstanding report before closing its SUMO session. Other MEC records remain.

**Replay guided demo** resets and runs the verified warning-at-1s,
closure-at-45s, clear-at-100s sequence. The controls remain available. Pressing a
manual road button switches back to manual hazard timing.

## Reading the view

- Blue: cautious vehicle. Warning cost is 300 seconds times severity.
- Orange: standard vehicle. Zero warning penalty; a closure is still excluded.
- Green: vehicle whose original route uses a different row.
- Purple: stationary probe supplying the actual road-coordinate report.
- Dots: live positions read from SUMO through TraCI.
- Colored lines: remaining routes read back from SUMO after computed routes are
  applied. Select a vehicle on **Vehicle decisions** to emphasize its route and
  inspect the explanation, current edge and speed.
- Dashed highlighted road: the report location. Amber means warning; red means
  closed. Purple is its clear/reference outline.
- **Show MEC H3 cell**: draws the geographic cell returned by the server after a
  report. It is an index around the coordinate, not a road-edge identifier.
- **What just happened?**: actual report acknowledgements and routing decisions.

The lab's map is a live visualization of real SUMO state. The separate native SUMO
window provides another view of the same session. No prerecorded motion or route
animation is used. The road network and scheduled detector events are synthetic.
The MEC round trips and per-vehicle graph routing are real.

## Connection and close behavior

A failed request pauses the lab and displays the error. Keep the SSH connections
open and use **Refresh / reconnect MEC**, then **Play**. If you closed the native
SUMO window, use **Reset / manual** to open a new session.

Close the AliveMap lab to stop its own SUMO session and attempt to clear its own
outstanding event. Keep the window open while cleanup finishes. The original MEC
has no expiration/deletion endpoint, so failed network cleanup is reported rather
than hidden. Per-session logs are retained in ignored `runs/interactive/UUID/`.

The manual step and warning/closure/clear flow were verified through the GUI
against the physical MEC and deployed view. Separate automated arrival evidence
is under `evidence/physical-mec-direct/`.
