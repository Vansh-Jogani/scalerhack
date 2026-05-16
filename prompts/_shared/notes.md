Notes for future prompt versions:

- maritime_sar: Agent 2 override prompt needed for Stage 5 (AIS receiver handling differs)
- Agent 1 orbit radii (50/100/150 m) are per CHANGE 2 spec; do not adjust without spec change
- Agent 3 previous_advisory field enables update-not-restart semantics; preserve it across re-triggers
