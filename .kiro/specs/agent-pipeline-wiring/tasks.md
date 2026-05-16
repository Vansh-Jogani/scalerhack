# Tasks

## Task List

- [x] 1. Wire tool_call / tool_result / error stream events in BaseAgent.act()
  - [x] 1.1 In `agents/base_agent.py` `act()`, emit `event: "tool_call"` with `tool` name and `input` dict before calling the Tool_Handler for each tool use block
  - [x] 1.2 In `agents/base_agent.py` `act()`, emit `event: "tool_result"` with `tool` name and `result` dict after the Tool_Handler returns successfully
  - [x] 1.3 In `agents/base_agent.py` `act()`, wrap the Tool_Handler call in a try/except; on exception emit `event: "error"` with `tool` name and `error` message, and set `status: "error"` in the result dict
  - [x] 1.4 Verify `_emit()` broadcasts via `stream_callback` as event type `"agent_stream"` with the full `{agent_id, event, content}` payload, and that exceptions from `stream_callback` are caught, logged as a warning, and do not propagate

- [x] 2. Add classification event, Assessment_Panel_Event, and completed event to Agent 1
  - [x] 2.1 In `agents/agent1_surveillance.py`, locate the `report_classification` tool handler (or the post-tool callback); after the tool call succeeds emit an `Agent_Stream_Event` with `event: "classification"` containing `incident_type`, `confidence`, and `affected_area_m2`
  - [x] 2.2 In `agents/agent1_surveillance.py`, after emitting the `"classification"` event, emit an `Assessment_Panel_Event` (broadcast via `stream_callback` with event type `"assessment_panel"`) containing the same classification fields so the frontend panel updates
  - [x] 2.3 In `agents/agent1_surveillance.py` `receive_go()` (or the mission completion path), emit an `Agent_Stream_Event` with `event: "completed"` containing the final `classification` and `confidence` after the OODA_R_Loop finishes

- [x] 3. Add recommended_drone_count to report_tools.py
  - [x] 3.1 In `agents/report_tools.py`, add `recommended_drone_count` (integer) to the `REPORT_CLASSIFICATION_TOOL` JSON schema under `properties` and include it in the `required` list
  - [x] 3.2 In `agents/report_tools.py` `create_report_classification_handler`, extract `recommended_drone_count` from the tool input and include it in the dict passed to `orchestrator.receive_agent1_report`

- [x] 4. Spawn swarm drones from nearest response centre and add completed event to Agent 2
  - [x] 4.1 In `agents/agent2_specialist.py`, implement a haversine distance helper (or import one) to find the nearest response centre from `world_state` (or a configured list) relative to the incident coordinates
  - [x] 4.2 In `agents/agent2_specialist.py` `run_mission()` (or `_survey_zone()`), replace the current spawn position (`staging_lat` 1 km north) with the lat/lon of the nearest response centre when calling `WorldState.add_drone` for each swarm drone
  - [x] 4.3 In `agents/agent2_specialist.py`, after `report_findings` is called and the Tool_Handler returns, emit an `Agent_Stream_Event` with `event: "completed"` containing `coverage_pct` and `zones_assessed` count

- [x] 5. Migrate Agent 3 from AsyncAnthropic to Ollama and add started/completed events
  - [x] 5.1 In `agents/agent3_advisory.py`, remove the `AsyncAnthropic` import and client instantiation; add an `httpx.AsyncClient` (or `aiohttp`) configured to POST to `http://localhost:11434/api/chat` with model `llama3.1:8b`
  - [x] 5.2 In `agents/agent3_advisory.py`, rewrite the LLM call method to send the Ollama `/api/chat` request body (`{"model": "llama3.1:8b", "messages": [...], "stream": false}`) and parse the response from `response["message"]["content"]`
  - [x] 5.3 In `agents/agent3_advisory.py`, preserve existing debounce logic, section validation, and retry-on-missing-sections behaviour — only the HTTP client and response parsing change
  - [x] 5.4 In `agents/agent3_advisory.py` `on_trigger()`, emit an `Agent_Stream_Event` with `event: "started"` containing `trigger_type` before advisory generation begins
  - [x] 5.5 In `agents/agent3_advisory.py`, after a valid advisory is produced and emitted via `stream_callback`, emit an `Agent_Stream_Event` with `event: "completed"` containing `trigger` and `sections` keys

- [x] 6. Add add_event() method to Span in sim_layer/tracer.py
  - [x] 6.1 In `sim_layer/tracer.py`, add an `add_event(name: str, attributes: dict = None)` method to the `Span` class that appends a timestamped event dict `{name, timestamp, attributes}` to an internal `events` list on the span
  - [x] 6.2 Ensure the `events` list is initialised as `[]` in `Span.__init__` so callers can safely iterate it even when no events have been added
