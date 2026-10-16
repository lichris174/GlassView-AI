"""Fabricated values: secrets that look real but are random, and filler text.

Every key here is random characters in a real-looking format. None are valid
credentials for any service.
"""

from __future__ import annotations

import base64
import json
import random
import string

from faker import Faker

ALNUM = string.ascii_letters + string.digits

# Invented names so no page imitates a real company.
BANKS = ("Northfield Credit Union", "Harbor & Pine Bank", "Summit Trust", "Lakeview Savings",
         "Cobalt Bank", "Meridian Federal")
CHAT_APPS = ("Chatterbox", "Relay", "Huddle", "Ping", "Murmur")
MAIL_APPS = ("Postbox", "Inkwell Mail", "Courier", "Letterly")
VAULTS = ("KeyKeep", "Lockbox", "VaultLine", "Passly")
SHOPS = ("Fernwood Goods", "Atlas Outfitters", "Nimbus Store", "Copperleaf")


def rand(rng: random.Random, n: int, chars: str = ALNUM) -> str:
    return "".join(rng.choice(chars) for _ in range(n))


def api_key(rng: random.Random) -> str:
    """One secret in a randomly chosen real-world format."""
    kind = rng.randrange(9)
    if kind == 0:
        return "sk-proj-" + rand(rng, 48, ALNUM + "_-")
    if kind == 1:
        return "sk-ant-api03-" + rand(rng, 40, ALNUM + "_-")
    if kind == 2:
        return "ghp_" + rand(rng, 36)
    if kind == 3:
        return "AKIA" + rand(rng, 16, string.ascii_uppercase + string.digits)
    if kind == 4:
        return "xoxb-" + "-".join(rand(rng, 12, string.digits) for _ in range(2)) + "-" + rand(rng, 24)
    if kind == 5:
        return jwt(rng)
    if kind == 6:
        return rand(rng, 40, string.ascii_letters + string.digits + "/+")
    if kind == 7:
        return "AIza" + rand(rng, 35, ALNUM + "_-")
    return rand(rng, 32, "0123456789abcdef")


def jwt(rng: random.Random) -> str:
    def b64(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    head = b64({"alg": "HS256", "typ": "JWT"})
    body = b64({"sub": rand(rng, 10, string.digits), "iat": rng.randrange(1_600_000_000, 1_800_000_000)})
    return f"{head}.{body}.{rand(rng, 43, ALNUM + '_-')}"


def db_url(rng: random.Random, fk: Faker) -> tuple[str, str, str]:
    """(prefix, password, suffix) so only the password span is tagged."""
    user = fk.user_name()
    host = rng.choice(("db.internal", "localhost", "10.0.4.12", "pg-prod-1"))
    return f"postgres://{user}:", fk.password(length=rng.randrange(10, 18)), f"@{host}:5432/app"


def card(rng: random.Random, fk: Faker) -> str:
    n = fk.credit_card_number()
    return " ".join(n[i:i + 4] for i in range(0, len(n), 4)) if rng.random() < 0.7 else n


def masked_card(rng: random.Random) -> str:
    return rng.choice(("•••• ", "**** ", "xxxx-xxxx-xxxx-", "Card ending ")) + rand(rng, 4, string.digits)


def money(rng: random.Random, lo: float = 3, hi: float = 4000) -> str:
    return f"${rng.uniform(lo, hi):,.2f}"


_OPENERS = ("hey", "ok so", "lol", "wait", "honestly", "fyi", "quick q", "omg", "btw", "ugh")
_LINES = (
    "are we still on for {day}?", "can you send me the {thing} when you get a sec",
    "I'll be there around {time}", "did you see what {name} said about the {thing}",
    "my landlord finally fixed the {thing}", "running late, sorry!!", "call me when you're free",
    "I told {name} I'd cover their shift on {day}", "the doctor said to come back in two weeks",
    "can you not tell {name} about this yet", "rent is due {day}, venmo me when you can",
    "here's the address for {day}: {addr}", "I got the job!!", "feeling kind of off today tbh",
    "we should talk about {thing} later", "sending you the pics from {day}",
    "don't forget mom's birthday on {day}", "my code for the door is {code}",
    "that meeting with {name} went badly", "I can lend you {money} until friday",
)


def chat_line(rng: random.Random, fk: Faker) -> str:
    line = rng.choice(_LINES).format(
        day=rng.choice(("monday", "tuesday", "friday", "saturday", "the 14th", "tomorrow")),
        thing=rng.choice(("contract", "keys", "photos", "invoice", "plan", "car", "lease", "report")),
        time=f"{rng.randrange(1, 12)}:{rng.choice(('00', '15', '30', '45'))}",
        name=fk.first_name(), addr=fk.street_address(), code=rand(rng, 4, string.digits),
        money=money(rng, 20, 400),
    )
    return f"{rng.choice(_OPENERS)} {line}" if rng.random() < 0.3 else line


def subject(rng: random.Random, fk: Faker) -> str:
    return rng.choice((
        "Re: {x}", "Fwd: {x}", "{x}", "Question about {x}", "Your {x} is ready",
    )).format(x=rng.choice(("the lease", "lab results", "Friday", "the offer letter",
                            "our call", "tax documents", "the wedding", fk.bs())))


def code_identifier(rng: random.Random) -> str:
    return rng.choice(("user_id", "retry_count", "base_url", "timeout", "items", "config",
                       "response", "payload", "is_valid", "max_len", "session", "handler"))
