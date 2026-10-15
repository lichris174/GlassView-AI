# Labeling Guide: Sensitive Screen Regions

This guide defines what the detector is supposed to find. Every reported number (recall, false-blur
rate) is only as meaningful as these definitions, so they are written down before labeling starts
and changed only with a dated note at the bottom.

## 1. Safety rules for collecting data

- **Fake data only.** Use alt accounts, made-up names, test API keys (revoked or never valid), demo
  bank sites, and conversations written for the dataset. Never capture real credentials, real
  messages, or real IDs.
- **Capture deliberately.** `ml.capture` saves whatever is on screen. Run it only during a planned
  session, and stop it (Ctrl+C) before switching to anything personal.
- **Review before labeling.** Delete any frame that shows something real by accident. Deleting is
  always safe before the split is frozen.
- **Data stays local.** Frames are saved under `%LOCALAPPDATA%\GlassView\dataset`, outside the repo
  and outside OneDrive. Only metrics and a few hand-checked, fully fake examples are ever published.

## 2. Classes

Draw a box around each region that would be harmful to send to a third party.

| Class | Box it | Do not box |
|---|---|---|
| `credential` | Password fields with content (dots count), visible passwords, one-time codes, recovery codes, security-question answers, login forms with username + password filled | Empty login forms; a "Forgot password?" link |
| `api_key` | API keys, tokens, secrets, private keys, `.env` values, connection strings with passwords, `Authorization:` headers | Variable *names* without values (`OPENAI_API_KEY=` with nothing after); public keys clearly labeled public |
| `financial` | Card numbers (full or partial), account and routing numbers, IBANs, balances tied to an account, transaction lists | Prices in a shop; stock tickers; generic charts with no account |
| `private_message` | Message bodies in chat and email apps (DMs, group chats, email threads), both sides of the conversation | Public posts (Reddit, X, forums); channel or folder names; the app's empty state |
| `personal_id` | Faces in photos or video calls, ID and passport images, government ID numbers, home addresses, dates of birth | Avatars smaller than ~32 px; cartoon or stock illustrations; your own UI avatar in a title bar |

### Edge cases (decided once, applied everywhere)

- **Inbox list** (sender + subject + preview line): `private_message`. The preview leaks content.
- **Partially visible secret** (scrolled half off screen, cut by a window edge): box the visible part
  if a person could read any of it.
- **Masked values** (`•••• 4242`, `sk-...abcd`): box them. Masks are partial leaks and the model
  should not learn "masked means safe".
- **Blurry or tiny text you cannot read at 100% zoom:** do not box it. The target is what a reader
  could extract.
- **Code that *uses* a secret** (`client = OpenAI(api_key="sk-...")`): box the literal value only,
  not the whole line.
- **The same secret repeated** (in an editor and a terminal): box every occurrence.

## 3. Box rules

- One box per contiguous region. A conversation of 8 bubbles is **one** `private_message` box if
  the bubbles are adjacent, or several boxes if other content separates them.
- Tight but complete: include all characters, keep padding to a few pixels.
- No box for a class that is not present. **Frames with no boxes are valuable**: they are how the
  false-blur rate is measured. Aim for roughly a third of frames with nothing sensitive.

## 4. Collection plan

Each row is one or more capture sessions (`python -m ml.capture --session <name>`). Splits are made
per session (see `ml/splits.py`), so variety *between* sessions matters more than frame count.

| Session theme | Mostly yields | Ideas |
|---|---|---|
| `login-*` | credential | Sign-in pages, password managers with fake vault, 2FA screens |
| `devkeys-*` | api_key | `.env` in an editor, cloud console key pages, `curl` with a bearer token in a terminal |
| `bank-*` | financial | Demo banking sites, spreadsheets of fake transactions, checkout forms with test cards |
| `chat-*` | private_message | Discord/Slack DMs with an alt, webmail with fake threads, SMS on a phone mirror |
| `id-*` | personal_id | Video call with webcam on, sample ID images, address forms |
| `clean-*` | (negatives) | Coding, docs, YouTube, news, settings pages, games |
| `mixed-*` | several | Real-looking multitasking: editor + chat + browser side by side |

Vary themes (light and dark), zoom levels, window sizes, and apps within each theme.

**Target:** ~300 labeled frames from at least 15 sessions. About 35% are frozen as test before any
model is trained.

## 5. Labeling workflow

1. Capture sessions, then review and delete accidental real content.
2. Freeze the split: `python -m ml.splits assign`. From this point test frames are never edited.
   `python -m ml.splits verify` checks it.
3. Label in [Label Studio](https://labelstud.io) (local, `pip install label-studio`) using the five
   classes above, and export in YOLO format.
4. **Consistency check:** a week after labeling, re-label 30 random frames without looking at the
   first pass. Agreement between the passes is reported next to the results, so readers know how
   reliable the labels themselves are.

## Change log

- 2026-10-14: initial version.
