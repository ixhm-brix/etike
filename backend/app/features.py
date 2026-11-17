"""Features that can be switched on and off with environment variables.

Bus booking is a future phase (bus companies would need a whole operator
system: fleets, schedules, ticket scanning). Its code, tables and data stay
in place, switched off with FEATURE_BUS_BOOKING, so it can come back later.
"""

from flask import current_app

from .errors import ApiError, bad_request

BUS_UNAVAILABLE = "Bus booking is not available yet."


def bus_enabled():
    return bool(current_app.config.get("FEATURE_BUS_BOOKING"))


def require_bus():
    """For bus-only endpoints: 404 while bus booking is switched off."""
    if not bus_enabled():
        raise ApiError(404, "bus_not_available", BUS_UNAVAILABLE)


def reject_bus_booking():
    """For endpoints shared with rides: 400 for a bus booking while it is off."""
    if not bus_enabled():
        raise bad_request(BUS_UNAVAILABLE, {"trip_id": BUS_UNAVAILABLE})


def enabled_features():
    return {
        "bus_booking": bus_enabled(),
        "demo_login": bool(current_app.config.get("DEMO_LOGIN")),
    }
