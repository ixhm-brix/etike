"""The legal documents a driver must upload before an admin can approve them.

In Rwanda, carrying passengers for money needs authorisation from RURA (the
regulator); a driving licence alone is not enough. RURA licenses taxi
companies and cooperatives, and each vehicle needs insurance and a valid
inspection. Confirm this list with RURA before going live: change it here
and everything else (upload page, admin page, approval check) follows.
"""

from .validation import local_now

# (key, what the driver sees, needs an expiry date)
DOCUMENTS = (
    ("national_id", "National ID (Indangamuntu)", False),
    ("driving_licence", "Driving licence", True),
    # Their own, or their company's or cooperative's RURA licence with proof
    # that they drive for it (the driver page explains this).
    ("rura_authorisation", "RURA authorisation to carry paying passengers", True),
    ("vehicle_registration", "Vehicle registration card (carte jaune)", False),
    ("insurance", "Vehicle insurance certificate covering passengers", True),
    ("inspection", "Vehicle inspection certificate (contrôle technique)", True),
)
TYPES = tuple(key for key, _, _ in DOCUMENTS)
LABELS = {key: label for key, label, _ in DOCUMENTS}
NEEDS_EXPIRY = {key for key, _, expires in DOCUMENTS if expires}

MAX_BYTES = 5 * 1024 * 1024
# What we accept, recognised by the file's first bytes, never its name.
MIMETYPES = {"jpg": "image/jpeg", "png": "image/png", "pdf": "application/pdf"}


def file_kind(head):
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"%PDF-"):
        return "pdf"
    return None


def checklist(driver):
    """Every required document with its state, in the order above."""
    have = {d.doc_type: d for d in driver.documents}
    today = local_now().date()
    items = []
    for key, label, needs_expiry in DOCUMENTS:
        doc = have.get(key)
        expired = bool(doc and doc.expires_on and doc.expires_on < today)
        items.append({
            "type": key,
            "label": label,
            "needs_expiry": needs_expiry,
            "uploaded": doc is not None,
            "uploaded_at": doc.uploaded_at.isoformat() if doc else None,
            "expires_on": doc.expires_on.isoformat() if doc and doc.expires_on else None,
            "expired": expired,
        })
    return items


def problems(driver):
    """Why this driver can't be approved yet; empty when the personal details
    are filled in and every document is in."""
    out = [] if driver.has_details else ["Missing: personal details (ID number, birth date, "
                                         "gender, home, licence number)"]
    for item in checklist(driver):
        if not item["uploaded"]:
            out.append(f"Missing: {item['label']}")
        elif item["expired"]:
            out.append(f"Expired: {item['label']}")
    return out
