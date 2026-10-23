"""GST identities as bills print them and Tally keeps them: GSTINs, states and the fields a master carries them in.

Validation establishes structural consistency (format, state code, check character), not government registration
status.
"""
import re

STATES = dict(zip(
    [f"{i:02}" for i in range(1, 39)],
    ["Jammu and Kashmir", "Himachal Pradesh", "Punjab", "Chandigarh", "Uttarakhand", "Haryana", "Delhi", "Rajasthan",
     "Uttar Pradesh", "Bihar", "Sikkim", "Arunachal Pradesh", "Nagaland", "Manipur", "Mizoram", "Tripura", "Meghalaya",
     "Assam", "West Bengal", "Jharkhand", "Odisha", "Chhattisgarh", "Madhya Pradesh", "Gujarat", "Daman and Diu",
     "Dadra and Nagar Haveli and Daman and Diu", "Maharashtra", "Andhra Pradesh (Old)", "Karnataka", "Goa", "Lakshadweep",
     "Kerala", "Tamil Nadu", "Puducherry", "Andaman and Nicobar Islands", "Telangana", "Andhra Pradesh", "Ladakh"], strict=True))
ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def state_name(code):
    if code not in STATES or code in ("25", "28"):
        raise ValueError("Unsupported or obsolete GST state code.")
    return STATES[code]


def gstin(value):
    if not isinstance(value, str):
        raise ValueError("A printed GSTIN is required.")
    value = value.strip().upper()
    if not re.fullmatch(r"[0-9]{2}[A-Z]{3}[ABCFGHJLPT][A-Z][0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]", value):
        raise ValueError("Invalid GSTIN or embedded PAN format.")
    state_name(value[:2])
    total, factor = 0, 2
    for character in reversed(value[:14]):
        product = ALPHABET.index(character) * factor
        total += product // 36 + product % 36
        factor = 3 - factor
    if value[-1] != ALPHABET[(36 - total % 36) % 36]:
        raise ValueError("GSTIN check character does not match.")
    return value


def _normal(value):
    return " ".join(str(value or "").split()).casefold()


def jurisdiction(value):
    """Resolve known printed jurisdiction names and optional matching GST codes.

    Never use fuzzy substrings: `Andhra Pradesh (37)` is valid evidence while
    the same name paired with another code cannot authorize a permanent master.
    """
    text = _normal(value).replace("&", "and")
    aliases = {"orissa": "odisha", "pondicherry": "puducherry", "uttaranchal": "uttarakhand",
               "nct delhi": "delhi", "new delhi": "delhi"}
    code = None
    match = re.fullmatch(r"(.+?)\s*(?:\((\d{1,2})\)|\s*-\s*(\d{1,2}))", text)
    leading = re.fullmatch(r"(\d{1,2})\s*-\s*(.+)", text)
    if match:
        text, code = match[1].strip(), (match[2] or match[3]).zfill(2)
    elif leading:
        code, text = leading[1].zfill(2), leading[2].strip()
    text = aliases.get(text, text)
    names = {_normal(state_name(k)): k for k in STATES if k not in ("25", "28")}
    found = names.get(text)
    if found is None or (code is not None and found != code):
        raise ValueError("GST jurisdiction name and code must identify one supported state.")
    return state_name(found)


def scalar(value):
    return str(value.get("#text", "") if isinstance(value, dict) else value or "").strip()


def native_values(value, names):
    """Values of these fields anywhere in a master: Tally nests GST registrations differently by version."""
    values = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in names:
                values.update(scalar(item) for item in (child if isinstance(child, list) else [child]) if scalar(item))
            if isinstance(child, (dict, list)):
                values.update(native_values(child, names))
    elif isinstance(value, list):
        for child in value:
            values.update(native_values(child, names))
    return values
