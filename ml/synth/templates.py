"""HTML templates for fake app screens.

Each template returns an HTML fragment that fills its container and uses the
theme's CSS variables. Sensitive elements are wrapped with ``s(cls, ...)``,
which adds ``data-s="<cls>"``; the renderer turns those into boxes. Tagging
follows docs/LABELING_GUIDE.md, notably:

- only the secret *value* is tagged, never its label (``API_KEY=`` stays out);
- empty login forms, prices, and variable names are left untagged on purpose,
  as hard negatives the model must learn to ignore;
- adjacent message bubbles form one ``private_message`` region;
- (2026-10-20 change log) a filled sign-in username/email is ``credential``,
  one box per field, and a person's name, phone, email, or address entered in
  a form is ``personal_id``.

Tagged and untagged elements must look alike: pass styling through ``s()``'s
``css`` argument (class names only), never a ``class="..."`` string.
"""

from __future__ import annotations

import html
import random
from collections.abc import Callable

from faker import Faker

from . import fake as F

Template = Callable[[random.Random, Faker], str]


def esc(text: object) -> str:
    return html.escape(str(text))


def s(cls: str, inner: str, tag: str = "span", css: str = "") -> str:
    """Wrap pre-escaped HTML as a sensitive region of class ``cls``."""
    klass = f' class="{css}"' if css else ""
    return f'<{tag} data-s="{cls}"{klass}>{inner}</{tag}>'


def tagged_input(cls: str, value: str, type_: str = "text") -> str:
    """A filled form field tagged on the ``<input>`` itself, so its box is exactly
    the field and its layout matches an untagged input (a wrapping block element
    would change the input's width and make a loose box)."""
    kind = f' type="{type_}"' if type_ != "text" else ""
    return f'<input data-s="{cls}"{kind} value="{value}">'


def initials(name: str) -> str:
    return "".join(p[0] for p in name.split()[:2]).upper()


def avatar(name: str, r: random.Random) -> str:
    hue = r.randrange(360)
    return (f'<div class="av" style="background:hsl({hue} 55% 45%)">{esc(initials(name))}</div>')


def sidebar(items: list[str], active: int, title: str) -> str:
    rows = "".join(
        f'<div class="nav{" on" if i == active else ""}">{esc(t)}</div>' for i, t in enumerate(items)
    )
    return f'<aside class="side"><div class="brand">{esc(title)}</div>{rows}</aside>'


# --- sensitive screens -------------------------------------------------------
def chat(r: random.Random, fk: Faker) -> str:
    me, them = fk.name(), fk.name()
    people = [them] + [fk.name() for _ in range(r.randrange(4, 10))]
    msgs = []
    for _ in range(r.randrange(4, 12)):
        who = r.choice((me, them))
        bubble = "mine" if who == me and r.random() < 0.5 else ""
        msgs.append(
            f'<div class="msg {bubble}">{avatar(who, r)}<div><div class="meta">{esc(who)} '
            f'<span class="muted">{r.randrange(1, 12)}:{r.randrange(10, 60)} PM</span></div>'
            f'<div class="text">{esc(F.chat_line(r, fk))}</div></div></div>'
        )
    return (
        f'<div class="app row">{sidebar(people, 0, r.choice(F.CHAT_APPS))}'
        f'<main class="col grow"><header class="bar">{avatar(them, r)} <b>{esc(them)}</b></header>'
        f'{s("private_message", "".join(msgs), "div", css="thread grow")}'
        f'<div class="composer"><input placeholder="Message {esc(them)}"></div></main></div>'
    )


def email(r: random.Random, fk: Faker) -> str:
    rows = "".join(
        f'<div class="mailrow"><b>{esc(fk.name())}</b> <span>{esc(F.subject(r, fk))}</span> '
        f'<span class="muted">— {esc(fk.sentence(nb_words=8))}</span></div>'
        for _ in range(r.randrange(5, 14))
    )
    body = "".join(f"<p>{esc(fk.paragraph(nb_sentences=r.randrange(2, 5)))}</p>"
                   for _ in range(r.randrange(2, 4)))
    reading = (
        f'<section class="col grow pad"><h2>{esc(F.subject(r, fk))}</h2>'
        # Sender and body form one region, like the inbox rows.
        + s("private_message",
            f'<div class="muted">{esc(fk.name())} &lt;{esc(fk.email())}&gt;</div>{body}', "div")
        + '</section>'
    ) if r.random() < 0.7 else ""
    folders = ["Inbox", "Starred", "Sent", "Drafts", "Spam", "Archive"]
    return (
        f'<div class="app row">{sidebar(folders, 0, r.choice(F.MAIL_APPS))}'
        f'{s("private_message", rows, "div", css="list")}{reading}</div>'
    )


def bank(r: random.Random, fk: Faker) -> str:
    acct = F.rand(r, r.randrange(8, 12), "0123456789")
    tx = "".join(
        f"<tr><td>{fk.date_this_year()}</td><td>{esc(fk.company())}</td>"
        f"<td>{'-' if r.random() < 0.8 else '+'}{F.money(r, 2, 900)}</td></tr>"
        for _ in range(r.randrange(5, 12))
    )
    cards = "".join(
        f'<div class="card"><div class="muted">{name}</div>'
        f'<div class="big">{s("financial", esc(F.money(r, 50, 25000)))}</div>'
        f'<div class="muted">Acct {s("financial", esc(F.masked_card(r) if r.random() < .5 else acct))}'
        f"</div></div>"
        for name in r.sample(("Checking", "Savings", "Credit card", "Joint"), r.randrange(1, 4))
    )
    addr = (f'<div class="pad muted">Customer: {s("personal_id", esc(fk.name()))}<br>'
            f'{s("personal_id", esc(fk.address()).replace(chr(10), "<br>"))}</div>'
            if r.random() < 0.4 else "")
    return (
        f'<div class="app row">{sidebar(["Accounts", "Transfers", "Bill pay", "Statements"], 0, r.choice(F.BANKS))}'
        f'<main class="col grow pad"><h2>Good {r.choice(("morning", "afternoon"))}, '
        f'{esc(fk.first_name())}</h2><div class="row wrap gap">{cards}</div>'
        f'<h3>Recent activity</h3>{s("financial", f"<table>{tx}</table>", "div")}{addr}</main></div>'
    )


def login(r: random.Random, fk: Faker) -> str:
    filled = r.random() < 0.75  # empty forms are hard negatives
    show = r.random() < 0.25
    pw = fk.password(length=r.randrange(9, 16))
    # A filled sign-in username/email is a credential too (guide, 2026-10-20).
    if filled:
        user_html = tagged_input("credential", esc(fk.email()))
        pw_html = tagged_input("credential", esc(pw), "text" if show else "password")
    else:
        user_html = '<input placeholder="Email">'
        pw_html = '<input type="password" placeholder="Password">'
    otp = ""
    if filled and r.random() < 0.3:
        otp = (f'<label>Verification code</label>'
               f'{tagged_input("credential", F.rand(r, 6, "0123456789"))}')
    return (
        f'<div class="app center"><form class="panel pad col gap" style="width:360px">'
        f'<h2>Sign in to {esc(fk.company())}</h2><label>Email</label>{user_html}'
        f'<label>Password</label>{pw_html}{otp}<button>Sign in</button>'
        f'<a class="muted">Forgot password?</a></form></div>'
    )


def vault(r: random.Random, fk: Faker) -> str:
    sites = [fk.domain_name() for _ in range(r.randrange(6, 14))]
    pw = fk.password(length=r.randrange(12, 22))
    shown = esc(pw) if r.random() < 0.5 else "•" * len(pw)
    detail = (
        f'<section class="col grow pad gap"><h2>{esc(sites[0])}</h2>'
        f'<label>Username</label>{s("credential", esc(fk.user_name()), "div", css="field")}'
        f'<label>Password</label>{s("credential", shown, "div", css="field mono")}'
    )
    if r.random() < 0.5:
        detail += (f'<label>One-time code</label>'
                   f'{s("credential", F.rand(r, 3, "0123456789") + " " + F.rand(r, 3, "0123456789"), "div", css="field mono big")}')
    if r.random() < 0.3:
        codes = " ".join(F.rand(r, 8, "abcdefghjkmnpqrstuvwxyz23456789") for _ in range(6))
        detail += f'<label>Recovery codes</label>{s("credential", codes, "div", css="field mono")}'
    detail += "</section>"
    return f'<div class="app row">{sidebar(sites, 0, r.choice(F.VAULTS))}{detail}</div>'


def env_editor(r: random.Random, fk: Faker) -> str:
    lines = []
    for _ in range(r.randrange(8, 20)):
        roll = r.random()
        if roll < 0.35:
            key = r.choice(("OPENAI_API_KEY", "STRIPE_SECRET_KEY", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY",
                            "ANTHROPIC_API_KEY", "JWT_SECRET", "SENDGRID_API_KEY", "SLACK_BOT_TOKEN"))
            lines.append(f'{key}={s("api_key", esc(F.api_key(r)))}')
        elif roll < 0.45:
            pre, pw, post = F.db_url(r, fk)
            lines.append(f"DATABASE_URL={esc(pre)}{s('api_key', esc(pw))}{esc(post)}")
        elif roll < 0.55:
            lines.append(f"{r.choice(('OPENAI_API_KEY', 'API_TOKEN', 'SECRET_KEY'))}=")  # empty: negative
        elif roll < 0.7:
            lines.append(f"# {esc(fk.sentence(nb_words=5))}")
        else:
            key = r.choice(("PORT", "DEBUG", "NODE_ENV", "LOG_LEVEL", "REGION", "TIMEOUT_MS", "APP_NAME"))
            lines.append(f"{key}={esc(r.choice(('3000', 'true', 'production', 'info', 'us-east-1', '5000', fk.word())))}")
    numbered = "".join(f'<div><span class="ln">{i}</span>{line}</div>' for i, line in enumerate(lines, 1))
    tabs = "".join(f'<span class="tab{" on" if i == 0 else ""}">{t}</span>'
                   for i, t in enumerate((".env", "app.py", "config.ts", "README.md")))
    return f'<div class="app col"><div class="tabs">{tabs}</div><pre class="code grow">{numbered}</pre></div>'


def terminal(r: random.Random, fk: Faker) -> str:
    user = fk.user_name()
    out = []
    for _ in range(r.randrange(4, 9)):
        roll = r.random()
        prompt = f'<span class="accent">{esc(user)}@dev</span>:~/app$ '
        if roll < 0.3:
            out.append(prompt + f'curl -H "Authorization: Bearer {s("api_key", esc(F.api_key(r)))}" '
                       f"https://api.{esc(fk.domain_name())}/v1/items")
            out.append('{"items": [], "count": 0}')
        elif roll < 0.45:
            out.append(prompt + f"export {r.choice(('API_KEY', 'AWS_SECRET_ACCESS_KEY', 'TOKEN'))}="
                       f"{s('api_key', esc(F.api_key(r)))}")
        elif roll < 0.7:
            out.append(prompt + "git log --oneline -3")
            out += [f"{F.rand(r, 7, '0123456789abcdef')} {esc(fk.sentence(nb_words=5))}" for _ in range(3)]
        else:
            out.append(prompt + r.choice(("npm run build", "pytest -q", "ls -la", "docker ps")))
            out += [esc(fk.sentence(nb_words=r.randrange(3, 9))) for _ in range(r.randrange(1, 4))]
    # The <pre> sits inside the .app flex container rather than being it: a
    # flex <pre> lays each text run out as its own column.
    return f'<div class="app"><pre class="term grow">{chr(10).join(out)}</pre></div>'


def checkout(r: random.Random, fk: Faker) -> str:
    items = "".join(f'<div class="row between"><span>{esc(fk.word().title())} '
                    f'{esc(fk.word())}</span><span>{F.money(r, 5, 300)}</span></div>'
                    for _ in range(r.randrange(2, 5)))  # prices: negative
    # Only values are tagged, one box per field; the <label> texts stay out.
    card_block = (f'<label>Card number</label>{tagged_input("financial", esc(F.card(r, fk)))}'
                  f'<div class="row gap">{tagged_input("financial", esc(fk.credit_card_expire()))}'
                  f'{tagged_input("financial", esc(fk.credit_card_security_code()))}</div>')
    addr = (f'<label>Shipping address</label>'
            f'<textarea data-s="personal_id">{esc(fk.address())}</textarea>')
    shop = esc(r.choice(F.SHOPS))
    buyer = tagged_input("personal_id", esc(fk.name()))  # a name entered in a form
    return (
        f'<div class="app row"><main class="col grow pad gap"><h2>{shop} checkout</h2>'
        f'<label>Name</label>{buyer}{addr}{card_block}<button>Pay now</button></main>'
        f'<aside class="side pad col gap"><h3>Order summary</h3>{items}</aside></div>'
    )


def profile(r: random.Random, fk: Faker) -> str:
    # A full name is a contact detail (personal_id); a username is not, so it
    # stays untagged as a hard negative.
    fields = [("Full name", esc(fk.name()), "personal_id"),
              ("Date of birth", esc(fk.date_of_birth(minimum_age=18, maximum_age=80)), "personal_id"),
              ("Home address", esc(fk.address()).replace("\n", ", "), "personal_id"),
              ("SSN", esc(fk.ssn()), "personal_id"),
              ("Phone", esc(fk.phone_number()), "personal_id"),
              ("Username", esc(fk.user_name()), None)]
    r.shuffle(fields)
    # Every field shares the .field style, so styling never gives a label away.
    rows = "".join(f'<label>{k}</label>' + (s(c, v, "div", css="field") if c
                                             else f'<div class="field">{v}</div>')
                   for k, v, c in fields[:r.randrange(3, 7)])
    idcard = ""
    if r.random() < 0.4:
        idcard = s("personal_id", (
            f'<div class="idcard row gap"><div class="photo"></div><div class="col">'
            f'<b>{esc(r.choice(("DRIVER LICENSE", "IDENTIFICATION CARD", "PASSPORT")))}</b>'
            f'<span>{esc(fk.name().upper())}</span><span>DOB {esc(fk.date_of_birth())}</span>'
            f'<span>No. {esc(F.rand(r, 9, "0123456789ABCDEFGHJK"))}</span></div></div>'), "div")
    return (f'<div class="app row">{sidebar(["Profile", "Security", "Billing", "Privacy"], 0, "Account")}'
            f'<main class="col grow pad gap"><h2>Personal information</h2>{rows}{idcard}</main></div>')


# --- harmless screens (hard negatives) -----------------------------------------
def docs(r: random.Random, fk: Faker) -> str:
    body = ""
    for _ in range(r.randrange(2, 5)):
        body += f"<h3>{esc(fk.catch_phrase())}</h3><p>{esc(fk.paragraph(nb_sentences=4))}</p>"
        if r.random() < 0.5:
            var = F.code_identifier(r)
            body += (f'<pre class="code">api_key = os.environ["API_KEY"]\n{var} = '
                     f'client.get("{esc(fk.uri_path())}")\nprint({var})</pre>')
    nav = [fk.catch_phrase() for _ in range(r.randrange(6, 12))]
    return (f'<div class="app row">{sidebar(nav, r.randrange(len(nav)), "Docs")}'
            f'<main class="col grow pad"><h1>{esc(fk.catch_phrase())}</h1>{body}</main></div>')


def dashboard(r: random.Random, fk: Faker) -> str:
    tiles = "".join(f'<div class="card"><div class="muted">{esc(fk.word().title())}</div>'
                    f'<div class="big">{r.choice((F.money(r, 1e3, 9e6), f"{r.randrange(1, 99)}%", str(r.randrange(100, 99999))))}</div></div>'
                    for _ in range(r.randrange(3, 6)))
    bars = "".join(f'<div class="barc" style="height:{r.randrange(10, 100)}%"></div>' for _ in range(r.randrange(8, 24)))
    return (f'<div class="app row">{sidebar(["Overview", "Reports", "Team", "Settings"], 0, fk.company())}'
            f'<main class="col grow pad gap"><div class="row wrap gap">{tiles}</div>'
            f'<div class="chart row">{bars}</div></main></div>')


def news(r: random.Random, fk: Faker) -> str:
    cards = "".join(f'<div class="card"><div class="thumb"></div><b>{esc(fk.sentence(nb_words=8))}</b>'
                    f'<p class="muted">{esc(fk.sentence(nb_words=16))}</p></div>' for _ in range(r.randrange(4, 10)))
    return f'<div class="app col pad"><h1>{esc(fk.company())} News</h1><div class="grid">{cards}</div></div>'


def code_view(r: random.Random, fk: Faker) -> str:
    lines = []
    for _ in range(r.randrange(10, 28)):
        v = F.code_identifier(r)
        lines.append(r.choice((
            f"def {fk.word()}_{v}({v}):", f"    {v} = {r.randrange(100)}",
            f"    return {v} + 1", f'    logger.info("{esc(fk.sentence(nb_words=4))}")',
            'API_KEY = os.getenv("API_KEY")', f"class {fk.word().title()}Service:",
            f"    if not {v}:", "        raise ValueError(\"missing\")", "",
        )))
    numbered = "".join(f'<div><span class="ln">{i}</span>{line}</div>' for i, line in enumerate(lines, 1))
    return f'<div class="app col"><div class="tabs"><span class="tab on">main.py</span></div><pre class="code grow">{numbered}</pre></div>'


def shop(r: random.Random, fk: Faker) -> str:
    cards = "".join(f'<div class="card"><div class="thumb"></div><b>{esc(fk.word().title())}</b>'
                    f'<div>{F.money(r, 5, 500)}</div><button>Add to cart</button></div>'
                    for _ in range(r.randrange(4, 12)))
    return f'<div class="app col pad"><h2>{esc(r.choice(F.SHOPS))}</h2><div class="grid">{cards}</div></div>'


SENSITIVE: dict[str, Template] = {
    "chat": chat, "email": email, "bank": bank, "login": login, "vault": vault,
    "env_editor": env_editor, "terminal": terminal, "checkout": checkout, "profile": profile,
}
CLEAN: dict[str, Template] = {
    "docs": docs, "dashboard": dashboard, "news": news, "code_view": code_view, "shop": shop,
}
