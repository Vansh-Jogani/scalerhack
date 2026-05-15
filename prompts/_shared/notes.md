# ARIA Prompt System — Notes

## TODO: maritime_sar Agent 2 override (Stage 5)

**Added:** 2026-05-15
**Flagged for:** Stage 5 review, before the maritime_sar scenario is built

The generic `agent2_specialist.md` assumes fixed-zone classification:
deploy swarm → scan zones → classify each zone → report coverage.

Maritime SAR does not map cleanly to this model:

- Search pattern is **moving** (expanding square, creeping line) not a static grid
- Targets are **dynamic** — persons in water drift; the zone concept breaks down
- `update_zone_classification` makes little sense when what you're tracking is a moving object trail
- The comms relay chain constraint (maintain_comms_relay_chain) requires spatial awareness of all three drones simultaneously, not per-drone independence
- Vessel coordination is a new responsibility class not present in any other swarm type

### Recommended Stage 5 actions

1. Create `prompts/agent2_maritime_sar.md` with a type-specific prompt:
   - Replace zone-based mission protocol with track-based protocol
   - Define `log_track_point(drone_id, lat, lon, timestamp, object_type, confidence)` tool
   - Replace `update_zone_classification` with `update_search_track`
   - Keep `mark_survivor`, `mark_hazard`, `report_swarm_findings` — they still apply

2. In `agent2_specialist.py`, check classification at dispatch time:
   ```python
   prompt_name = "agent2_maritime_sar" if classification == "maritime_sar" else "agent2_specialist"
   self._prompt = load_prompt(prompt_name)
   ```

3. Decide whether `report_swarm_findings` schema covers maritime output or needs a subtype.

4. Add `log_track_point` to `agents/tools/schemas.py` and the maritime tool set.
