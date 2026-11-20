"""Small text helpers shared by the news steps."""
import html
import re


# A UTF-8 character read as Windows-1252: a lead character, then one or two continuation characters.
MANGLED = re.compile("[Â-ß][\u0080-¿Œ-™]|[à-ï][\u0080-¿Œ-™]{2}")


def _repair(m):
    raw = bytearray()
    for ch in m.group(0):
        try:
            raw += ch.encode("cp1252")
        except UnicodeEncodeError:
            if ord(ch) > 255:
                return m.group(0)
            raw.append(ord(ch))
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return m.group(0)


def unmangle(text):
    """Repairs UTF-8 text that was read as Windows-1252 somewhere upstream, such as "â€™" for an apostrophe, one sequence
    at a time, so real accents (Câmara) and correct characters in the same title are left as they are. "â€" followed by
    a plain quote has lost its last byte and is read as a dash."""
    if not text or "â" not in text and "Ã" not in text and "Â" not in text:
        return text
    return MANGLED.sub(_repair, text.replace('â€"', "—"))


def tidy(text):
    """GDELT spaces out punctuation in titles ("$69 , 000", "U . S ."), leaves HTML entities in, and sometimes passes on
    mis-encoded characters. This puts all three right."""
    t = unmangle(html.unescape(html.unescape(text or ""))).replace("\xa0", " ")
    t = re.sub(r"\s+([,.;:?!%)\]])", r"\1", t)
    t = re.sub(r"([($\[])\s+", r"\1", t)
    t = re.sub(r"(\d), (\d{3})\b", r"\1,\2", t)
    t = re.sub(r"(\d)\. (\d)", r"\1.\2", t)
    t = re.sub(r"\b([A-Z])\. (?=[A-Z]\.)", r"\1.", t)
    t = re.sub(r"(\w) - (\w)", r"\1-\2", t)
    return re.sub(r"\s+", " ", t).strip()


def norm(text):
    """Lower case letters and digits only, to spot the same text twice."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()
