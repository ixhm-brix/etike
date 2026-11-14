"""SMS through Africa's Talking (https://developers.africastalking.com).

Sending an SMS must never break a booking: every failure is logged and
swallowed. When SMS is not configured, messages are logged and skipped.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app

log = logging.getLogger(__name__)

LIVE_URL = "https://api.africastalking.com/version1/messaging"
SANDBOX_URL = "https://api.sandbox.africastalking.com/version1/messaging"


def send(phone, message):
    """Send one SMS. Returns True if Africa's Talking accepted it."""
    cfg = current_app.config
    username, api_key = cfg.get("AT_USERNAME"), cfg.get("AT_API_KEY")
    if not (username and api_key):
        log.info("SMS not configured; skipped a message to %s", _mask(phone))
        return False

    form = {"username": username, "to": phone, "message": message}
    if cfg.get("AT_SENDER_ID"):
        form["from"] = cfg["AT_SENDER_ID"]
    req = urllib.request.Request(
        SANDBOX_URL if username == "sandbox" else LIVE_URL,
        data=urllib.parse.urlencode(form).encode(),
        headers={
            "apiKey": api_key,
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as res:
            body = json.loads(res.read() or b"{}")
        recipients = body.get("SMSMessageData", {}).get("Recipients", [])
        ok = bool(recipients) and recipients[0].get("status") == "Success"
        if not ok:
            log.warning("SMS to %s not accepted: %s", _mask(phone), body)
        return ok
    except Exception as err:  # an SMS problem must never break a booking
        log.warning("SMS to %s failed: %s", _mask(phone), err)
        return False


def booking_confirmed(booking):
    """Tell the passenger (and the driver, for a ride) that a booking is paid."""
    target = booking.trip or booking.offer
    when = target.departure_time.strftime("%a %d %b %H:%M")
    route = f"{target.route.origin} to {target.route.destination}"
    seats = f"{booking.seats_booked} seat{'s' if booking.seats_booked > 1 else ''}"

    passenger = booking.user
    send(
        passenger.phone,
        f"ETIKE: booking #{booking.booking_id} confirmed. {route}, {when}, {seats}. "
        f"Paid RWF {booking.total_price:,}.",
    )
    if booking.offer:
        driver = booking.offer.driver.user
        send(
            driver.phone,
            f"ETIKE: {passenger.full_name} booked {seats} on your ride {route}, {when} "
            f"(booking #{booking.booking_id}).",
        )


def _mask(phone):
    # Keep phone numbers out of logs, apart from the last digits.
    return f"***{str(phone)[-3:]}"
