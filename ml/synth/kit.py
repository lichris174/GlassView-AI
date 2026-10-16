"""Write a folder of fake sensitive content to open in REAL apps while capturing.

    python -m ml.synth.kit        # writes <data>/kit/

The real (val/test) screenshots need real apps rendering sensitive-looking
content. This kit supplies that content, all fabricated: a .env with random
keys, a transactions CSV, a chat script to paste into a message-yourself chat,
terminal commands with fake tokens, a fake identity, and logins to type (never
submit) into sign-in pages. See docs/COLLECTING.md for the session checklist.
"""

from __future__ import annotations

import random

from faker import Faker

from ..paths import data_root
from . import fake as F


def build(seed: int = 0) -> dict[str, str]:
    r, fk = random.Random(seed), Faker("en_US")
    fk.seed_instance(seed)
    pre, pw, post = F.db_url(r, fk)
    env = "\n".join([
        "# app config", f"OPENAI_API_KEY={F.api_key(r)}", f"STRIPE_SECRET_KEY={F.api_key(r)}",
        f"GITHUB_TOKEN={F.api_key(r)}", f"DATABASE_URL={pre}{pw}{post}", "PORT=3000",
        "NODE_ENV=production", f"AWS_SECRET_ACCESS_KEY={F.api_key(r)}", "SENTRY_DSN=",
        f"JWT_SECRET={F.api_key(r)}", "LOG_LEVEL=info",
    ]) + "\n"
    tx = "date,description,amount,balance\n" + "\n".join(
        f"{fk.date_this_year()},{fk.company().replace(',', '')},-{r.uniform(3, 900):.2f},"
        f"{r.uniform(500, 9000):.2f}" for _ in range(40)
    ) + "\n"
    a, b = fk.first_name(), fk.first_name()
    chat = "\n".join(f"{r.choice((a, b))}: {F.chat_line(r, fk)}" for _ in range(30)) + "\n"
    curl = "\n".join([
        f'curl -H "Authorization: Bearer {F.api_key(r)}" https://api.example.com/v1/me',
        f"export AWS_SECRET_ACCESS_KEY={F.api_key(r)}",
        f"git remote set-url origin https://x-access-token:{F.api_key(r)}@github.com/me/app.git",
        f"psql {pre}{pw}{post}",
    ]) + "\n"
    ident = "\n".join([
        f"Name: {fk.name()}", f"Date of birth: {fk.date_of_birth(minimum_age=20, maximum_age=70)}",
        f"Address: {fk.address().replace(chr(10), ', ')}", f"SSN: {fk.ssn()}",
        f"Phone: {fk.phone_number()}", f"Passport no.: {F.rand(r, 9, '0123456789')}",
        f"Card: 4242 4242 4242 4242  exp 12/{r.randrange(27, 32)}  cvc {r.randrange(100, 999)}",
        f"Card: {F.card(r, fk)}  exp {fk.credit_card_expire()}",
        f"IBAN: {fk.iban()}",
    ]) + "\n"
    logins = "\n".join(f"{fk.email()}  /  {fk.password(length=r.randrange(10, 16))}"
                       for _ in range(10)) + "\n"
    code = (f'import openai\n\nclient = openai.OpenAI(api_key="{F.api_key(r)}")\n'
            f'DB_PASSWORD = "{fk.password(length=14)}"\n\n'
            'def main():\n    print(client.models.list())\n')
    return {".env": env, "transactions.csv": tx, "chat_script.txt": chat,
            "terminal_commands.txt": curl, "identity.txt": ident, "logins.txt": logins,
            "app_with_secret.py": code}


def main() -> None:
    out = data_root() / "kit"
    out.mkdir(parents=True, exist_ok=True)
    for name, text in build().items():
        (out / name).write_text(text, encoding="utf-8")
    print(f"Kit written to {out}")


if __name__ == "__main__":
    main()
