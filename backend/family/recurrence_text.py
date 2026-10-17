"""Canonical deterministic normalization for natural recurrence text.

This module contains only lexical normalization. ``action_schedule.parse_schedule``
remains the single grammar entry point and turns the normalized phrase into an
``action-schedule-v1`` value. No fuzzy matching or probabilistic interpretation
is performed here.
"""
from __future__ import annotations

import re
import unicodedata


WEEKDAY_CODES = ["MO", "TU", "WE", "TH", "FR"]

_CARDINALS = {
    "eins": "1",
    "zwei": "2", "drei": "3", "vier": "4", "fünf": "5", "fuenf": "5", "sechs": "6",
    "sieben": "7", "acht": "8", "neun": "9", "zehn": "10", "elf": "11", "zwölf": "12", "zwoelf": "12",
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
}

_COMPOUND_COUNTS = {
    "einmal": "1 mal", "zweimal": "2 mal", "dreimal": "3 mal", "viermal": "4 mal",
    "fünfmal": "5 mal", "fuenfmal": "5 mal", "sechsmal": "6 mal", "siebenmal": "7 mal",
    "achtmal": "8 mal", "neunmal": "9 mal", "zehnmal": "10 mal", "elfmal": "11 mal",
    "zwölfmal": "12 mal", "zwoelfmal": "12 mal",
    "once": "1 times", "twice": "2 times", "thrice": "3 times",
}

_DE_ORDINAL_INTERVALS = {
    "zweite": 2, "zweiter": 2, "zweiten": 2, "zweites": 2,
    "dritte": 3, "dritter": 3, "dritten": 3, "drittes": 3,
    "vierte": 4, "vierter": 4, "vierten": 4, "viertes": 4,
    "fünfte": 5, "fünfter": 5, "fünften": 5, "fünftes": 5,
    "fuenfte": 5, "fuenfter": 5, "fuenften": 5, "fuenftes": 5,
    "sechste": 6, "sechster": 6, "sechsten": 6, "sechstes": 6,
    "siebte": 7, "siebter": 7, "siebten": 7, "siebtes": 7,
    "achte": 8, "achter": 8, "achten": 8, "achtes": 8,
    "neunte": 9, "neunter": 9, "neunten": 9, "neuntes": 9,
    "zehnte": 10, "zehnter": 10, "zehnten": 10, "zehntes": 10,
    "elfte": 11, "elfter": 11, "elften": 11, "elftes": 11,
    "zwölfte": 12, "zwölfter": 12, "zwölften": 12, "zwölftes": 12,
    "zwoelfte": 12, "zwoelfter": 12, "zwoelften": 12, "zwoelftes": 12,
}

_EN_ORDINAL_INTERVALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12,
}

_DE_NTH = {
    "erste": "ersten", "erster": "ersten", "ersten": "ersten", "erstes": "ersten", "1.": "ersten",
    "zweite": "zweiten", "zweiter": "zweiten", "zweiten": "zweiten", "zweites": "zweiten", "2.": "zweiten",
    "dritte": "dritten", "dritter": "dritten", "dritten": "dritten", "drittes": "dritten", "3.": "dritten",
    "vierte": "vierten", "vierter": "vierten", "vierten": "vierten", "viertes": "vierten", "4.": "vierten",
    "fünfte": "fünften", "fünfter": "fünften", "fünften": "fünften", "fünftes": "fünften", "5.": "fünften",
    "fuenfte": "fünften", "fuenfter": "fünften", "fuenften": "fünften", "fuenftes": "fünften",
    "letzte": "letzten", "letzter": "letzten", "letzten": "letzten", "letztes": "letzten",
}

_DE_WEEKDAYS = {
    "montag": "MO", "dienstag": "TU", "mittwoch": "WE", "donnerstag": "TH",
    "freitag": "FR", "samstag": "SA", "sonntag": "SU",
}

_EN_WEEKDAYS = {
    "monday": "MO", "tuesday": "TU", "wednesday": "WE", "thursday": "TH",
    "friday": "FR", "saturday": "SA", "sunday": "SU",
}

_WEEKDAY_FORMS = {
    "montags": "jeden montag", "dienstags": "jeden dienstag", "mittwochs": "jeden mittwoch",
    "donnerstags": "jeden donnerstag", "freitags": "jeden freitag", "samstags": "jeden samstag", "sonntags": "jeden sonntag",
    "immer montags": "jeden montag", "immer dienstags": "jeden dienstag", "immer mittwochs": "jeden mittwoch",
    "immer donnerstags": "jeden donnerstag", "immer freitags": "jeden freitag", "immer samstags": "jeden samstag", "immer sonntags": "jeden sonntag",
    "mondays": "every monday", "tuesdays": "every tuesday", "wednesdays": "every wednesday",
    "thursdays": "every thursday", "fridays": "every friday", "saturdays": "every saturday", "sundays": "every sunday",
    "on mondays": "every monday", "on tuesdays": "every tuesday", "on wednesdays": "every wednesday",
    "on thursdays": "every thursday", "on fridays": "every friday", "on saturdays": "every saturday", "on sundays": "every sunday",
}

_SIMPLE = {
    "täglich": "täglich", "taeglich": "täglich", "jeden tag": "täglich", "jeden einzelnen tag": "täglich", "daily": "daily", "every day": "daily",
    "wöchentlich": "alle 1 wochen", "woechentlich": "alle 1 wochen", "jede woche": "alle 1 wochen", "weekly": "every 1 weeks", "every week": "every 1 weeks", "every other week": "every 2 weeks",
    "monatlich": "alle 1 monate", "jeden monat": "alle 1 monate", "monthly": "every 1 months", "every month": "every 1 months",
    "quartalsweise": "alle 1 quartale", "vierteljährlich": "alle 1 quartale", "vierteljaehrlich": "alle 1 quartale", "quarterly": "every 1 quarters", "every quarter": "every 1 quarters",
    "jährlich": "alle 1 jahre", "jaehrlich": "alle 1 jahre", "jedes jahr": "alle 1 jahre", "yearly": "every 1 years", "annually": "every 1 years", "every year": "every 1 years",
}

_BUSINESS_WEEKDAYS = {
    "werktags", "wochentags", "an werktagen", "an jedem werktag", "jeden werktag", "jeder werktag",
    "montag bis freitag", "montags bis freitags", "mo-fr", "mo - fr",
    "weekdays", "every weekday", "every business day", "business days", "monday to friday", "mon-fri", "mon - fri",
}

_DE_UNIT_MAP = {
    "stunde": "stunden", "stunden": "stunden",
    "tag": "tage", "tage": "tage", "tagen": "tage",
    "werktag": "werktage", "werktage": "werktage", "werktagen": "werktage",
    "woche": "wochen", "wochen": "wochen",
    "monat": "monate", "monate": "monate", "monaten": "monate",
    "quartal": "quartale", "quartale": "quartale", "quartalen": "quartale",
    "jahr": "jahre", "jahre": "jahre", "jahren": "jahre",
}

_EN_UNIT_MAP = {
    "hour": "hours", "hours": "hours",
    "day": "days", "days": "days",
    "week": "weeks", "weeks": "weeks",
    "month": "months", "months": "months",
    "quarter": "quarters", "quarters": "quarters",
    "year": "years", "years": "years",
}


def _clean(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("Repeat text must be a string.")
    value = unicodedata.normalize("NFKC", text).casefold().strip()
    value = value.replace("×", "x").replace("–", "-").replace("—", "-").replace("−", "-")
    value = value.replace("’", "'")
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[!?;,]+$", "", value).strip()
    value = re.sub(r"(?<!\d)\.$", "", value).strip()
    return value


def _extract_clock(value: str) -> tuple[str, str | None]:
    patterns = [
        r"\s+(?:um|at)\s+(\d{1,2})(?:[:.](\d{2}))?\s*(?:uhr)?$",
        r"\s+(\d{1,2})[:.](\d{2})\s*(?:uhr)?$",
        r"\s+(\d{1,2})\s*uhr$",
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if not match:
            continue
        hour = int(match[1])
        minute = int(match[2] or 0) if match.lastindex and match.lastindex >= 2 else 0
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("Time must use a valid 24-hour clock.")
        return value[:match.start()].strip(), f"{hour:02d}:{minute:02d}"
    return value, None


def _replace_count_words(value: str) -> str:
    for word, replacement in _COMPOUND_COUNTS.items():
        value = re.sub(rf"\b{re.escape(word)}\b", replacement, value)
    for word, replacement in _CARDINALS.items():
        value = re.sub(rf"\b{re.escape(word)}\b", replacement, value)
    return re.sub(r"\s+", " ", value).strip()


def _canonical_weekday_interval(value: str) -> tuple[str, int] | None:
    de_weekdays = "|".join(_DE_WEEKDAYS)
    de_ordinals = "|".join(sorted((re.escape(item) for item in _DE_ORDINAL_INTERVALS), key=len, reverse=True))
    de = re.fullmatch(rf"jeden\s+(\d+\.?|{de_ordinals})\s+({de_weekdays})", value)
    if de:
        token = de[1]
        interval = int(token.rstrip(".")) if token[0].isdigit() else _DE_ORDINAL_INTERVALS[token]
        return _DE_WEEKDAYS[de[2]], interval

    en_weekdays = "|".join(_EN_WEEKDAYS)
    en_ordinals = "|".join(_EN_ORDINAL_INTERVALS)
    en = re.fullmatch(rf"every\s+(other|{en_ordinals})\s+({en_weekdays})", value)
    if en:
        interval = 2 if en[1] == "other" else _EN_ORDINAL_INTERVALS[en[1]]
        return _EN_WEEKDAYS[en[2]], interval
    return None


def _canonical_interval(value: str) -> str | None:
    business_en = re.fullmatch(r"(?:every|each)?\s*(\d+)\.?\s*business\s*days?", value)
    if business_en:
        return f"alle {int(business_en[1])} werktage"
    de = re.fullmatch(
        r"(?:(?:alle|jede|jeden|jedes|jeweils(?: alle)?)\s+)?(\d+)\.?\s*"
        r"(stunde|stunden|tag|tage|tagen|werktag|werktage|werktagen|woche|wochen|monat|monate|monaten|quartal|quartale|quartalen|jahr|jahre|jahren)",
        value,
    )
    if de:
        return f"alle {int(de[1])} {_DE_UNIT_MAP[de[2]]}"
    en = re.fullmatch(r"(?:(?:every|each)\s+)?(\d+)\.?\s*(hour|hours|day|days|week|weeks|month|months|quarter|quarters|year|years)", value)
    if en:
        return f"every {int(en[1])} {_EN_UNIT_MAP[en[2]]}"
    return None


def _ordinal_interval(value: str) -> str | None:
    de = re.fullmatch(r"(?:jeden|jede|jedes)\s+(\w+)\s+(tag|werktag|woche|monat|quartal|jahr)", value)
    if de and de[1] in _DE_ORDINAL_INTERVALS:
        return f"alle {_DE_ORDINAL_INTERVALS[de[1]]} {_DE_UNIT_MAP[de[2]]}"
    en_business = re.fullmatch(r"(?:every|each)\s+(\w+)\s+business\s+day", value)
    if en_business and en_business[1] in _EN_ORDINAL_INTERVALS:
        return f"alle {_EN_ORDINAL_INTERVALS[en_business[1]]} werktage"
    en = re.fullmatch(r"(?:every|each)\s+(\w+)\s+(hour|day|week|month|quarter|year)", value)
    if en and en[1] in _EN_ORDINAL_INTERVALS:
        return f"every {_EN_ORDINAL_INTERVALS[en[1]]} {_EN_UNIT_MAP[en[2]]}"
    return None


def _canonical_quota(value: str) -> str | None:
    de = re.fullmatch(r"(\d+)\s*(?:x|mal|-\s*mal)?\s*(?:pro|je|die|im|in der|in jeder)\s+(tag|woche|monat)", value)
    if de:
        return f"{int(de[1])}x pro {de[2]}"
    de_adverb = re.fullmatch(r"(\d+)\s*(?:x|mal|-\s*mal)?\s*(täglich|taeglich|wöchentlich|woechentlich|monatlich)", value)
    if de_adverb:
        period = {"täglich": "tag", "taeglich": "tag", "wöchentlich": "woche", "woechentlich": "woche", "monatlich": "monat"}[de_adverb[2]]
        return f"{int(de_adverb[1])}x pro {period}"
    en = re.fullmatch(r"(\d+)\s*(?:x|times?)?\s*(?:per|a|each)\s+(day|week|month)", value)
    if en:
        return f"{int(en[1])} times per {en[2]}"
    en_adverb = re.fullmatch(r"(\d+)\s*(?:x|times?)?\s*(daily|weekly|monthly)", value)
    if en_adverb:
        period = {"daily": "day", "weekly": "week", "monthly": "month"}[en_adverb[2]]
        return f"{int(en_adverb[1])} times per {period}"
    return None


def _canonical_nth(value: str) -> str | None:
    weekdays = "montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag"
    ordinal = "|".join(sorted((re.escape(item) for item in _DE_NTH), key=len, reverse=True))
    match = re.fullmatch(
        rf"(?:immer\s+)?(?:am\s+)?({ordinal})\s+({weekdays})\s+"
        r"(?:im|in jedem|in jeden|jedes|jeden)\s+(monat|monats|quartal|quartals|januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)",
        value,
    )
    if not match:
        return None
    period = {"monats": "monat", "quartals": "quartal"}.get(match[3], match[3])
    return f"{_DE_NTH[match[1]]} {match[2]} im {period}"


def normalize_recurrence_text(text: str) -> tuple[str, str | None, dict | None]:
    """Return ``(canonical_phrase, clock, recurrence_override)``.

    Overrides are used only where expressing the normalized meaning as a short
    phrase would lose semantics (calendar weekdays and Nth-weekday intervals).
    """
    value, clock = _extract_clock(_clean(text))
    value = _replace_count_words(value)

    if value in _BUSINESS_WEEKDAYS:
        return value, clock, {"frequency": "weekly", "interval": 1, "weekdays": WEEKDAY_CODES}
    if value in _WEEKDAY_FORMS:
        value = _WEEKDAY_FORMS[value]
    weekday_interval = _canonical_weekday_interval(value)
    if weekday_interval:
        weekday, interval = weekday_interval
        return value, clock, {"frequency": "weekly", "interval": interval, "weekdays": [weekday]}
    if value in _SIMPLE:
        value = _SIMPLE[value]
    for normalizer in (_canonical_quota, _ordinal_interval, _canonical_interval, _canonical_nth):
        phrase = normalizer(value)
        if phrase:
            value = phrase
            break
    return value, clock, None
