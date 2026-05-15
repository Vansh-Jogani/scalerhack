"""Tests for the event bus (Deliverable 4)."""

import asyncio
import pytest

from orchestrator.event_bus import EventBus

FAST_WINDOW = 0.05   # 50ms — fast enough for tests without slow CI


# ---------------------------------------------------------------------------
# Basic pub/sub
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_single_event_delivered():
    bus = EventBus(coalesce_window_s=FAST_WINDOW)
    received = []

    async def handler(payload):
        received.append(payload)

    bus.subscribe("agent_1_report_received", handler)
    await bus.publish("agent_1_report_received", {"incident_id": "INC-1"})
    await asyncio.sleep(FAST_WINDOW * 3)

    assert len(received) == 1
    assert received[0]["incident_id"] == "INC-1"
    bus.stop()


@pytest.mark.asyncio
async def test_multiple_subscribers_all_called():
    bus = EventBus(coalesce_window_s=FAST_WINDOW)
    received_a, received_b = [], []

    async def handler_a(p): received_a.append(p)
    async def handler_b(p): received_b.append(p)

    bus.subscribe("agent_2_findings_updated", handler_a)
    bus.subscribe("agent_2_findings_updated", handler_b)

    await bus.publish("agent_2_findings_updated", {"coverage": 73.5})
    await asyncio.sleep(FAST_WINDOW * 3)

    assert len(received_a) == 1
    assert len(received_b) == 1
    bus.stop()


@pytest.mark.asyncio
async def test_unsubscribed_type_not_delivered():
    bus = EventBus(coalesce_window_s=FAST_WINDOW)
    received = []

    async def handler(p): received.append(p)

    bus.subscribe("agent_1_report_received", handler)
    await bus.publish("world_event_fired", {"type": "fire_grew"})  # different type
    await asyncio.sleep(FAST_WINDOW * 3)

    assert len(received) == 0
    bus.stop()


# ---------------------------------------------------------------------------
# Coalescing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rapid_publishes_coalesced_to_one():
    bus = EventBus(coalesce_window_s=FAST_WINDOW)
    received = []

    async def handler(p): received.append(p)

    bus.subscribe("agent_1_report_received", handler)

    # Publish 3 times before coalesce window closes
    await bus.publish("agent_1_report_received", {"v": 1})
    await bus.publish("agent_1_report_received", {"v": 2})
    await bus.publish("agent_1_report_received", {"v": 3})

    await asyncio.sleep(FAST_WINDOW * 4)

    assert len(received) == 1, f"Expected 1 coalesced dispatch, got {len(received)}"
    assert received[0]["v"] == 3, "Latest payload should win"
    bus.stop()


@pytest.mark.asyncio
async def test_coalescing_latest_wins_per_type():
    bus = EventBus(coalesce_window_s=FAST_WINDOW)
    received = []

    async def handler(p): received.append(p)

    bus.subscribe("agent_1_report_received", handler)
    bus.subscribe("agent_2_findings_updated", handler)

    # Mix of types — should get 2 dispatches (one per type, each with latest payload)
    await bus.publish("agent_1_report_received", {"type": "a1", "v": 1})
    await bus.publish("agent_1_report_received", {"type": "a1", "v": 2})
    await bus.publish("agent_2_findings_updated", {"type": "a2", "coverage": 73.5})

    await asyncio.sleep(FAST_WINDOW * 4)

    assert len(received) == 2
    a1_payloads = [r for r in received if r.get("type") == "a1"]
    assert len(a1_payloads) == 1
    assert a1_payloads[0]["v"] == 2
    bus.stop()


@pytest.mark.asyncio
async def test_events_spaced_apart_each_delivered():
    """Two events >coalesce_window apart must each trigger a dispatch."""
    bus = EventBus(coalesce_window_s=FAST_WINDOW)
    received = []

    async def handler(p): received.append(p)

    bus.subscribe("agent_1_report_received", handler)

    await bus.publish("agent_1_report_received", {"v": 1})
    await asyncio.sleep(FAST_WINDOW * 4)   # let first window close
    await bus.publish("agent_1_report_received", {"v": 2})
    await asyncio.sleep(FAST_WINDOW * 4)   # let second window close

    assert len(received) == 2
    assert received[0]["v"] == 1
    assert received[1]["v"] == 2
    bus.stop()


# ---------------------------------------------------------------------------
# Handler errors don't crash the bus
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handler_exception_does_not_stop_bus():
    bus = EventBus(coalesce_window_s=FAST_WINDOW)
    recovered = []

    async def bad_handler(p):
        raise RuntimeError("handler failure")

    async def good_handler(p):
        recovered.append(p)

    bus.subscribe("agent_1_report_received", bad_handler)
    bus.subscribe("agent_1_report_received", good_handler)

    await bus.publish("agent_1_report_received", {"incident_id": "INC-1"})
    await asyncio.sleep(FAST_WINDOW * 4)

    assert len(recovered) == 1, "Good handler must still run after bad one raises"
    bus.stop()


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_heartbeat_fires_after_silence(monkeypatch):
    FAST_HB = 0.1   # 100ms heartbeat for test speed
    bus = EventBus(coalesce_window_s=FAST_WINDOW, heartbeat_interval_s=FAST_HB)
    hb_received = []

    async def hb_handler(p): hb_received.append(p)
    bus.subscribe("heartbeat_check", hb_handler)

    await bus.start_heartbeat("INC-1", lambda: {"incident_id": "INC-1"})
    await asyncio.sleep(FAST_HB * 2.5)   # enough for at least one heartbeat

    assert len(hb_received) >= 1, "Heartbeat should fire after silence"
    bus.stop()
