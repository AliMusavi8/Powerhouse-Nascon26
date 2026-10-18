"""Synchronous chat moderation (FR-5.3, spec 5.8): leetspeak profanity masking, flood rejection, rate limit.

Deterministic: the same batch always yields the same filtered list, kicked and muted users.
"""
import itertools
import re

from ..errors import validation
from .validate import is_int

DICTIONARY = ("badword", "porn", "scam", "fuck", "shit", "bitch", "asshole", "idiotspam")
LEET = {"@": "a", "0": "o", "3": "e", "$": "s"}
AMBIGUOUS = {"1": ("i", "l", ""), "!": ("i", ""), "|": ("i", "l", "")}
ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")
FLOOD_REPEAT = re.compile(r"(\S)\1{3,}", re.IGNORECASE)
FLOOD_MARKS = re.compile(r"[!?]{3,}")
EDGE_PUNCT_TAIL = re.compile(r"[.,;:!?\"')\]]+$")
EDGE_PUNCT_HEAD = re.compile(r"^[\"'(\[]+")
MASK = "***"
RATE_LIMIT_MESSAGES = 3


def validate_request(body: dict) -> dict:
    bad = []
    room = body.get("chat_room_id")
    if not isinstance(room, str) or not (1 <= len(room) <= 128):
        bad.append("chat_room_id")
    msgs = body.get("incoming_messages")
    if not isinstance(msgs, list) or len(msgs) > 500:
        bad.append("incoming_messages")
    else:
        for m in msgs:
            if (not isinstance(m, dict) or not isinstance(m.get("message_id"), str)
                    or not isinstance(m.get("sender"), str) or not m["sender"] or not isinstance(m.get("text"), str)):
                bad.append("incoming_messages")
                break
    check = body.get("check_dlq", True)
    if check is None:
        check = True
    if not isinstance(check, bool):
        bad.append("check_dlq")
    fails = body.get("simulate_failed_notifications", 0)
    if fails is None:
        fails = 0
    if not is_int(fails) or not (0 <= fails <= 1000):
        bad.append("simulate_failed_notifications")
    if bad:
        raise validation(bad)
    return {"chat_room_id": room, "incoming_messages": msgs, "check_dlq": check,
            "simulate_failed_notifications": fails}


def _variants(token: str) -> set[str]:
    """Normalised spellings of one token (ambiguous characters are tried every way)."""
    base = ZERO_WIDTH.sub("", token.lower())
    base = "".join(LEET.get(c, c) for c in base)
    slots = [i for i, c in enumerate(base) if c in AMBIGUOUS]
    if len(slots) > 6:
        slots = slots[:6]
    out = set()
    for choice in itertools.product(*(AMBIGUOUS[base[i]] for i in slots)):
        chars = list(base)
        for i, rep in zip(slots, choice):
            chars[i] = rep
        out.add(re.sub(r"[^a-z0-9]", "", "".join(c if c not in AMBIGUOUS else "i" for c in chars)))
    return out


def is_profane(token: str) -> bool:
    return any(word in v for v in _variants(token) for word in DICTIONARY)


def mask(text: str) -> tuple[str, bool]:
    """Replace every profane whitespace-separated token with ***, keeping edge punctuation."""
    hit = False
    parts = re.split(r"(\s+)", text)
    for i, tok in enumerate(parts):
        if not tok or tok.isspace():
            continue
        head = EDGE_PUNCT_HEAD.match(tok)
        tail = EDGE_PUNCT_TAIL.search(tok)
        h = head.group(0) if head else ""
        t = tail.group(0) if tail and tail.start() > len(h) else ""
        core = tok[len(h):len(tok) - len(t)] if t else tok[len(h):]
        if core and is_profane(core):
            parts[i] = h + MASK + t
            hit = True
        elif is_profane(tok):
            parts[i] = MASK
            hit = True
    return "".join(parts), hit


def is_flood(text: str) -> bool:
    return bool(FLOOD_REPEAT.search(text) or FLOOD_MARKS.search(text))


def moderate(messages: list[dict]) -> dict:
    filtered, kicked, muted = [], [], []
    per_sender: dict[str, int] = {}
    for m in messages:
        sender, text = m["sender"], m["text"]
        per_sender[sender] = per_sender.get(sender, 0) + 1
        if is_flood(text):
            if sender not in muted:
                muted.append(sender)
            continue
        if per_sender[sender] > RATE_LIMIT_MESSAGES:
            if sender not in muted:
                muted.append(sender)
            continue
        masked, hit = mask(text)
        if hit:
            filtered.append({"message_id": m["message_id"], "sender": sender, "text": masked, "flagged": True,
                             "reason": "profanity_leetspeak"})
            if sender not in kicked:
                kicked.append(sender)
        else:
            filtered.append({"message_id": m["message_id"], "sender": sender, "text": text, "flagged": False,
                             "reason": None})
    return {"filtered_messages": filtered, "kicked_users": kicked, "muted_users": muted,
            "flagged_count": sum(1 for f in filtered if f["flagged"])}


def classify(text: str) -> tuple[str | None, str]:
    """Single live chat message: (reason or None, text to broadcast). reason flood -> do not broadcast."""
    if is_flood(text):
        return "flood_character_repeat", text
    masked, hit = mask(text)
    return ("profanity_leetspeak" if hit else None), masked


def sig_payload(room: str, flagged_count: int, kicked: list[str], queue_depth: int) -> dict:
    return {"chat_room_id": room, "flagged_count": flagged_count, "kicked_users": kicked, "queue_depth": queue_depth}
