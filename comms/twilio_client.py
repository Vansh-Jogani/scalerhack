import os
from twilio.rest import Client
import structlog

log = structlog.get_logger()

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")
MSG_SID     = os.getenv("TWILIO_MESSAGING_SERVICE_SID")
NUMBER_1    = os.getenv("TWILIO_INCIDENT_COMMANDER_NUMBER")
NUMBER_2    = os.getenv("TWILIO_SECONDARY_ALERT_NUMBER")


def _client():
    if not ACCOUNT_SID or not AUTH_TOKEN:
        log.warning("twilio.not_configured")
        return None
    return Client(ACCOUNT_SID, AUTH_TOKEN)


# ── SMS ──────────────────────────────────────────────────────────────────

def send_sms(to: str, body: str) -> dict:
    """Send a single SMS. Never raises — returns status dict."""
    client = _client()
    if not client:
        return {"status": "skipped", "reason": "twilio_not_configured"}
    try:
        msg = client.messages.create(
            messaging_service_sid=MSG_SID,
            to=to,
            body=body
        )
        log.info("twilio.sms_sent", to=to, sid=msg.sid, status=msg.status)
        return {"status": "sent", "sid": msg.sid}
    except Exception as e:
        log.error("twilio.sms_failed", to=to, error=str(e))
        return {"status": "error", "error": str(e)}


def send_survivor_alert(lat: float, lon: float, count: int, incident_id: str) -> list:
    """
    Called by Agent 2 when a thermal hit is confirmed.
    Sends SMS to both configured numbers simultaneously.
    """
    body = (
        f"ARIA DISASTER ALERT\n"
        f"{count} survivor signature(s) detected.\n"
        f"Location: {lat:.4f}N {lon:.4f}E\n"
        f"Incident: {incident_id}\n"
        f"Medical drone tasked — ETA calculating.\n"
        f"ARIA Autonomous Response System"
    )
    results = []
    for number in [NUMBER_1, NUMBER_2]:
        if number:
            results.append(send_sms(number, body))
    return results


def send_advisory_broadcast(
    disaster_type: str,
    severity: str,
    location_name: str,
    immediate_action: str,
    incident_id: str
) -> list:
    """
    Called by Agent 3 when advisory is issued.
    Sends evacuation/safety instructions to both numbers.
    """
    body = (
        f"ARIA EMERGENCY ADVISORY\n"
        f"Incident: {disaster_type.replace('_', ' ').title()} — {severity.upper()}\n"
        f"Area: {location_name}\n"
        f"Action: {immediate_action[:120]}\n"
        f"Ref: {incident_id}\n"
        f"Stay tuned for updates."
    )
    results = []
    for number in [NUMBER_1, NUMBER_2]:
        if number:
            results.append(send_sms(number, body))
    return results


# ── VOICE CALL ───────────────────────────────────────────────────────────

def make_alert_call(
    to: str,
    disaster_type: str,
    location_name: str,
    severity: str,
    incident_id: str
) -> dict:
    """
    Make an automated voice call using Twilio TwiML text-to-speech.
    Called immediately on DEPLOY INCIDENT for high/critical severity.
    Never raises — returns status dict.
    """
    client = _client()
    if not client:
        return {"status": "skipped", "reason": "twilio_not_configured"}

    disaster_readable = disaster_type.replace("_", " ")
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Pause length="1"/>
  <Say voice="alice" language="en-IN">
    This is an automated ARIA disaster response alert.
    A {disaster_readable} has been detected in {location_name}.
    Severity level: {severity}.
    Emergency drones have been deployed to the area.
    Please evacuate the affected zone immediately and await further instructions.
    Incident reference: {incident_id}.
    This message will repeat once.
  </Say>
  <Pause length="1"/>
  <Say voice="alice" language="en-IN">
    This is an automated ARIA disaster response alert.
    A {disaster_readable} has been detected in {location_name}.
    Severity level: {severity}.
    Emergency drones have been deployed to the area.
    Please evacuate the affected zone immediately and await further instructions.
    Incident reference: {incident_id}.
  </Say>
</Response>"""

    try:
        call = client.calls.create(
            twiml=twiml,
            to=to,
            from_=os.getenv("TWILIO_FROM_NUMBER", NUMBER_1)
        )
        log.info("twilio.call_initiated", to=to, sid=call.sid, status=call.status)
        return {"status": "initiated", "sid": call.sid}
    except Exception as e:
        log.error("twilio.call_failed", to=to, error=str(e))
        return {"status": "error", "error": str(e)}


def call_incident_commander(
    disaster_type: str,
    location_name: str,
    severity: str,
    incident_id: str
) -> list:
    """
    Calls both configured numbers.
    Used on incident deploy for high and critical severity.
    """
    results = []
    for number in [NUMBER_1, NUMBER_2]:
        if number:
            results.append(
                make_alert_call(number, disaster_type, location_name, severity, incident_id)
            )
    return results
