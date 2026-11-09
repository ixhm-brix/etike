"""The places people travel between.

These are Rwanda's districts, except that Kigali city's three districts
(Nyarugenge, Gasabo, Kicukiro) count as one place, "Kigali", because that is
how buses and drivers name it. The landing-page map uses the same list.
"""

PLACES = (
    "Kigali",
    "Bugesera",
    "Burera",
    "Gakenke",
    "Gatsibo",
    "Gicumbi",
    "Gisagara",
    "Huye",
    "Kamonyi",
    "Karongi",
    "Kayonza",
    "Kirehe",
    "Muhanga",
    "Musanze",
    "Ngoma",
    "Ngororero",
    "Nyabihu",
    "Nyagatare",
    "Nyamagabe",
    "Nyamasheke",
    "Nyanza",
    "Nyaruguru",
    "Rubavu",
    "Ruhango",
    "Rulindo",
    "Rusizi",
    "Rutsiro",
    "Rwamagana",
)

# Other names for the same place: Kigali's districts and main bus park, and
# the town names that bus companies still print on tickets.
ALIASES = {
    "nyarugenge": "Kigali",
    "gasabo": "Kigali",
    "kicukiro": "Kigali",
    "nyabugogo": "Kigali",
    "kigali city": "Kigali",
    "butare": "Huye",
    "gisenyi": "Rubavu",
    "ruhengeri": "Musanze",
    "cyangugu": "Rusizi",
    "kibuye": "Karongi",
    "byumba": "Gicumbi",
    "gitarama": "Muhanga",
    "kibungo": "Ngoma",
    "gikongoro": "Nyamagabe",
}

_BY_LOWER = {p.lower(): p for p in PLACES}


def normalise_place(name):
    """Return the official place name for `name`, or None if unknown."""
    if not name:
        return None
    key = " ".join(str(name).split()).lower()
    return _BY_LOWER.get(key) or ALIASES.get(key)
