# Requirements Document

## Introduction

The Agent Pipeline Wiring feature ensures that ARIA's three agents (Surveillance, Specialist Swarm, Advisory) behave correctly end-to-end: each agent executes its full mission loop, hands off structured data through the orchestration layer, emits stream events for frontend visibility, and drives real drone state changes in WorldState. The scope is limited to `agents/` and `sim/` — no changes to the orchestrator, main.py, or frontend.

## Glossary

- **Agent_1**: The `SurveillanceAgent` — fixed-wing reconnaissance drone controller
- **Agent_2**: The `SpecialistAgent` — multi-drone swarm controller
- **Agent_3**: The `AdvisoryAgent` — event-driven advisory generator
- **Orchestrator**: The LangGraph state machine in `orchestrator/orchestrator.py` — not modified by this feature
- **WorldState**: The `sim/world_state.py` singleton holding all drone and marker state
- **DroneModel**: The kinematic drone simulation in `sim/drone_model.py`
- **Stream_Callback**: The `broadcast_event(event_type, data)` async callback injected into agents
- **Agent_Stream_Event**: A dict with shape `{agent_id, event, content}` broadcast via `Stream_Callback`
- **Telemetry**: The `Telemetry` dataclass from `sim/drone_interface.py` with fields `drone_id, lat, lon, alt, heading, speed, state, battery_pct`
- **Swarm_Config**: A dict injected by the Orchestrator into Agent_2 from `classifier.py` — never self-selected by Agent_2
- **OODA_R_Loop**: The Observe → Orient/Reason → Act → Reflect loop implemented in `BaseAgent`
- **Tool_Handler**: An async callable registered in `BaseAgent._tool_handlers` that executes a named tool
- **GO_Signal**: The initial message sent to Agent_1 containing incident coordinates
- **Agent1_Report**: The structured dict produced by `report_classification` and stored in Orchestrator state
- **Agent2_Report**: The structured dict produced by `report_findings` and stored in Orchestrator state

---

## Requirements

### Requirement 1: Agent 1 Full Mission Loop

**User Story:** As an incident commander, I want Agent 1 to autonomously fly to the incident, collect sensor data, classify the disaster, and report back, so that the orchestrator has a confirmed classification before deploying the specialist swarm.

#### Acceptance Criteria

1. WHEN Agent_1 receives a GO_Signal containing `lat` and `lon` coordinates, THE Agent_1 SHALL call `fly_to` with the target coordinates and its assigned `drone_id` as the first tool call in the OODA_R_Loop.
2. WHEN the `fly_to` Tool_Handler is called, THE WorldState SHALL transition the target DroneModel state from `IDLE` or `LOITERING` to `FLYING` via `DroneModel.set_target`.
3. WHEN Agent_1 calls `get_sensor_reading` and the drone is within the incident marker radius, THE sensor Tool_Handler SHALL return a reading with `status: "ok"` and a non-empty `data` field.
4. WHEN Agent_1 has collected at least one sensor reading, THE Agent_1 SHALL call `loiter_over` to establish a loiter pattern over the incident area before calling `report_classification`.
5. WHEN Agent_1 calls `report_classification`, THE Tool_Handler SHALL invoke `orchestrator.receive_agent1_report` with a dict containing `classification`, `confidence`, `affected_area_m2`, and `notes`.
6. WHEN `report_classification` is called with `confidence` below 0.6, THE Agent_1 SHALL call `request_detailed_pass` before calling `report_classification` a second time.
7. IF `fly_to` returns `status: "error"` for a given `drone_id`, THEN THE Agent_1 SHALL emit an Agent_Stream_Event with `event: "error"` and a `content` field describing the failure.
8. WHEN Agent_1 completes its mission, THE Agent_1 SHALL emit an Agent_Stream_Event with `event: "completed"` containing the final `classification` and `confidence`.

---

### Requirement 2: Agent 1 Stream Event Emission

**User Story:** As a frontend operator, I want to see Agent 1's reasoning and tool calls in real time, so that the pipeline panel reflects live surveillance progress.

#### Acceptance Criteria

1. WHEN Agent_1 starts its OODA_R_Loop, THE Agent_1 SHALL emit an Agent_Stream_Event with `event: "started"` containing `model` and `drones`.
2. WHEN Agent_1 calls any tool, THE BaseAgent SHALL emit an Agent_Stream_Event with `event: "tool_call"` containing `tool` name and `input` before the Tool_Handler executes.
3. WHEN a Tool_Handler returns a result, THE BaseAgent SHALL emit an Agent_Stream_Event with `event: "tool_result"` containing `tool` name and `result`.
4. WHEN Agent_1's LLM produces a text reasoning block, THE BaseAgent SHALL emit an Agent_Stream_Event with `event: "reasoning"` containing the text.
5. WHEN Agent_1 calls `report_classification`, THE Agent_1 SHALL emit an Agent_Stream_Event with `event: "classification"` containing `incident_type`, `confidence`, and `affected_area_m2`.
6. THE Agent_Stream_Event SHALL always include `agent_id` matching the agent's constructor `agent_id` parameter.

---

### Requirement 3: Agent 2 Swarm Deployment

**User Story:** As an incident commander, I want Agent 2 to receive Agent 1's classification, deploy the correct swarm, and systematically survey the incident area, so that detailed zone assessments and survivor detections are available for the advisory.

#### Acceptance Criteria

1. WHEN Agent_2's `run_mission` is called with an `agent1_report`, THE Agent_2 SHALL read `swarm_config` exclusively from the constructor-injected parameter — never by calling `classifier.py` directly.
2. WHEN `run_mission` is called, THE Agent_2 SHALL call `WorldState.add_drone` for each drone in `swarm_config["drones"]`, creating DroneModel instances with unique IDs in the format `swarm-{agent_id}-{index}`.
3. WHEN a swarm drone is added via `WorldState.add_drone`, THE DroneModel SHALL be initialized with `state: "IDLE"` and a position approximately 1 km north of the incident center.
4. WHEN Agent_2 calls `fly_to` for a swarm drone, THE WorldState SHALL transition that DroneModel to `state: "FLYING"`.
5. WHEN Agent_2 completes the survey grid, THE Agent_2 SHALL call `zone_annotate` for each assessed zone with a non-empty `label` and `confidence` between 0.0 and 1.0.
6. WHEN thermal or acoustic sensor readings indicate survivors, THE Agent_2 SHALL call `survivor_marker` with `lat`, `lon`, and `count` greater than 0.
7. WHEN zone coverage reaches 70% or all priority tasks are complete, THE Agent_2 SHALL call `report_findings` with `zones_assessed`, `survivor_detections`, `hazard_markers`, `coverage_pct`, and `notes`.
8. WHEN `report_findings` is called, THE Tool_Handler SHALL invoke `orchestrator.receive_agent2_report` with the complete findings dict.
9. IF a swarm drone's `fly_to` call returns `status: "error"`, THEN THE Agent_2 SHALL skip that waypoint and continue the survey with remaining drones.

---

### Requirement 4: Agent 2 Stream Event Emission

**User Story:** As a frontend operator, I want to see Agent 2's swarm deployment and survey progress in real time, so that the pipeline panel shows which drones are active and what zones have been assessed.

#### Acceptance Criteria

1. WHEN Agent_2 finishes spawning all swarm drones, THE Agent_2 SHALL emit an Agent_Stream_Event with `event: "swarm_deployed"` containing `drones` (list of drone IDs), `type`, `count`, and `swarm` name.
2. WHEN Agent_2 completes the automated survey grid, THE Agent_2 SHALL emit an Agent_Stream_Event with `event: "survey_complete"` containing `total_readings` and `drones` count.
3. WHEN Agent_2 calls `zone_annotate`, THE BaseAgent SHALL emit an Agent_Stream_Event with `event: "tool_call"` before execution and `event: "tool_result"` after.
4. WHEN Agent_2 calls `survivor_marker`, THE BaseAgent SHALL emit an Agent_Stream_Event with `event: "tool_call"` before execution and `event: "tool_result"` after.
5. WHEN Agent_2 calls `report_findings`, THE Agent_2 SHALL emit an Agent_Stream_Event with `event: "completed"` containing `coverage_pct` and `zones_assessed` count.

---

### Requirement 5: Agent 3 Advisory Generation

**User Story:** As a first responder, I want Agent 3 to receive both agent reports and produce a structured advisory with all six required sections, so that I have a clear, actionable response plan.

#### Acceptance Criteria

1. WHEN Agent_3's `on_trigger` is called with `agent1_report` and `agent2_report`, THE Agent_3 SHALL produce an advisory containing all six sections: `SITUATION SUMMARY`, `IMMEDIATE ACTIONS`, `EXCLUSION ZONES`, `RESOURCE REQUIREMENTS`, `RISK FLAGS`, and `MONITORING`.
2. WHEN the initial advisory response is missing one or more required sections, THE Agent_3 SHALL retry the Claude API call once with a stricter prompt before falling back to the error advisory.
3. WHEN Agent_3 produces a valid advisory, THE Agent_3 SHALL emit the advisory via `stream_callback` with event type `"advisory"` and a payload containing `text`, `trigger`, `timestamp`, and `sections`.
4. WHEN `trigger_type` is `"agent_2_findings_updated"`, THE Agent_3 SHALL apply a 15-second debounce — batching multiple rapid calls into a single advisory generation.
5. WHEN Agent_3 encounters a Claude API error, THE Agent_3 SHALL return a structured error advisory using `_error_advisory` rather than raising an exception.
6. WHEN Agent_3 emits an advisory, THE Agent_3 SHALL emit an Agent_Stream_Event with `event: "completed"` containing `trigger` and `sections` keys.
7. WHEN Agent_3 starts advisory generation, THE Agent_3 SHALL emit an Agent_Stream_Event with `event: "started"` containing the `trigger_type`.

---

### Requirement 6: Drone State Updates in WorldState

**User Story:** As a frontend operator, I want drone state changes commanded by agents to be immediately reflected in WorldState and broadcast via telemetry, so that the map shows accurate drone positions and states.

#### Acceptance Criteria

1. WHEN `fly_to` Tool_Handler is called with a valid `drone_id`, THE WorldState SHALL call `DroneModel.set_target` which transitions `DroneModel._state` to `"FLYING"`.
2. WHEN `DroneModel.tick` is called while `_state` is `"FLYING"` and the drone reaches within 5 meters of its target, THE DroneModel SHALL transition `_state` to `"LOITERING"`.
3. WHEN `rtl` Tool_Handler is called, THE DroneModel SHALL transition `_state` to `"RTL"` and set target to home position.
4. WHEN `abort` Tool_Handler is called, THE DroneModel SHALL immediately set `_state` to `"IDLE"` and clear `target_lat`, `target_lon`, `target_alt`.
5. WHEN `WorldState.add_drone` is called by Agent_2, THE new DroneModel SHALL appear in `WorldState.drones` and be included in subsequent `get_all_telemetry` responses.
6. WHEN the WorldState tick loop runs, THE WorldState SHALL call `DroneModel.tick` for every drone in `WorldState.drones` including swarm drones added by Agent_2.
7. WHEN `get_drone_telemetry` is called for a drone that does not exist in `WorldState.drones`, THE WorldState SHALL return `None` without raising an exception.

---

### Requirement 7: Inter-Agent Data Flow Through the Orchestrator

**User Story:** As a system integrator, I want agent handoffs to flow exclusively through the orchestrator's state, so that agents remain decoupled and the pipeline is auditable.

#### Acceptance Criteria

1. THE Agent_1 SHALL NOT hold a direct reference to Agent_2 or Agent_3 — all output is written via `report_classification` Tool_Handler to the Orchestrator.
2. THE Agent_2 SHALL NOT hold a direct reference to Agent_1 or Agent_3 — it receives `agent1_report` only as a parameter to `run_mission` passed by the Orchestrator.
3. THE Agent_3 SHALL NOT hold a direct reference to Agent_1 or Agent_2 — it receives `agent1_report` and `agent2_report` only as parameters to `on_trigger` passed by the Orchestrator.
4. WHEN `report_classification` Tool_Handler is called, THE handler SHALL call `orchestrator.receive_agent1_report` with the classification dict.
5. WHEN `report_findings` Tool_Handler is called, THE handler SHALL call `orchestrator.receive_agent2_report` with the findings dict.
6. WHEN the Orchestrator calls `Agent_2.run_mission`, THE Orchestrator SHALL pass the `agent1_report` dict as the sole source of incident area data for swarm deployment.
7. WHEN the Orchestrator calls `Agent_3.on_trigger`, THE Orchestrator SHALL pass both `agent1_report` and `agent2_report` as separate named parameters.

---

### Requirement 8: Tool Call Stream Event Emission (BaseAgent)

**User Story:** As a frontend operator, I want every tool call and result to be visible in the pipeline panel, so that I can trace exactly what each agent did and why.

#### Acceptance Criteria

1. WHEN `BaseAgent.act` executes a tool, THE BaseAgent SHALL emit an Agent_Stream_Event with `event: "tool_call"` containing `tool` name and `input` dict before calling the Tool_Handler.
2. WHEN a Tool_Handler returns, THE BaseAgent SHALL emit an Agent_Stream_Event with `event: "tool_result"` containing `tool` name and `result` dict.
3. IF a Tool_Handler raises an exception, THEN THE BaseAgent SHALL emit an Agent_Stream_Event with `event: "error"` containing `tool` name and `error` message, and record `status: "error"` in the result.
4. THE Agent_Stream_Event emitted by `BaseAgent._emit` SHALL always be broadcast via `Stream_Callback` as event type `"agent_stream"` with the full `{agent_id, event, content}` payload.
5. WHEN `Stream_Callback` raises an exception during emit, THE BaseAgent SHALL log a warning and continue execution without propagating the exception.
