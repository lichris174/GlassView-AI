# Collecting the Real Screenshots: Checklist

About **45 min capturing + 60–90 min labeling**. Training data is synthetic and already labeled
(`python -m ml.synth.render`); these real screenshots are the **validation and test sets**, which
is why they must come from real apps. All content comes from the fake kit, so nothing real is ever
captured.

## 0. Setup (5 min)

Install the ML extras once: `./setup.ps1 -ML` (or `pip install -r requirements-ml.txt` and
`python -m playwright install chromium`).

**Dataset location.** Everything below lives under `GLASSVIEW_DATA` (on the main dev machine:
`D:\GlassView\dataset`). If the variable is not set *in the current shell*, `ml/paths.py` silently
falls back to `%LOCALAPPDATA%\GlassView\dataset`, which on that machine is a stale copy with **no
labels**. A shell or IDE opened before the variable was set will not see it, so check first:

```powershell
$env:GLASSVIEW_DATA                           # must print the dataset path
.venv\Scripts\python -m ml.synth.kit          # fake content -> $env:GLASSVIEW_DATA\kit
explorer $env:GLASSVIEW_DATA\kit
```

Before every session: close or minimize anything personal (real chats, email, banking). Capture
grabs the whole primary monitor.

## 1. Sessions (~3 min each)

Start each with the command shown, do the actions slowly (switch windows, scroll, resize, zoom),
then press **Ctrl+C**. Similar frames are skipped automatically, so keep things changing.

```powershell
.venv\Scripts\python -m ml.capture --session <name> --interval 2
```

| # | Session name | What to do (content from the kit) | Mostly yields |
|---|---|---|---|
| 1 | `devkeys-vscode` | Open `.env` and `app_with_secret.py` in VS Code. Light theme once, dark theme once; zoom in/out (Ctrl +/-) | api_key |
| 2 | `devkeys-terminal` | Paste lines from `terminal_commands.txt` into PowerShell / Windows Terminal (don't press Enter on `psql`/`git`) | api_key |
| 3 | `devkeys-notepad` | Open `.env` in Notepad, then in a browser tab (drag the file in) | api_key |
| 4 | `login-web` | Visit 4–5 sign-in pages (any big sites). Type an email + password from `logins.txt`. **Don't submit.** Toggle "show password" where offered | credential |
| 5 | `login-empty` | Same sign-in pages left **empty** (hard negatives) | (clean) |
| 6 | `bank-excel` | Open `transactions.csv` in Excel or Google Sheets; scroll, add a SUM row | financial |
| 7 | `bank-forms` | Any store's checkout or a donation form: type the 4242 test card + fake address from `identity.txt`. **Don't submit.** | financial, personal_id |
| 8 | `chat-self` | In a message-yourself chat (WhatsApp Web "Message yourself", Discord DM to yourself, Slack self-DM, or Signal Note to Self) paste 10–15 lines from `chat_script.txt` | private_message |
| 9 | `chat-mail` | Gmail/Outlook: compose a draft to yourself with a few chat lines; capture the draft and the Drafts list | private_message |
| 10 | `id-forms` | Paste `identity.txt` values into a contact/profile form or a Word doc | personal_id |
| 11 | `id-webcam` | Open the Windows Camera app (your face = personal_id). Optional; skip if you prefer | personal_id |
| 12 | `clean-coding` | Normal coding in VS Code on this repo (no `.env` open) | (clean) |
| 13 | `clean-browsing` | Docs, Wikipedia, YouTube home, news, a shopping page with prices | (clean) |
| 14 | `mixed-split` | Snap two windows side by side (Win+←/→): `.env` + browser, chat + docs, Excel + email draft | several |

Target: **150–200 frames** total. Check with `dir $env:GLASSVIEW_DATA\raw\*`. (The first round actually
produced **108 frames from 9 sessions**; see DEVLOG 2026-10-20.)

## 2. Review (5 min)

Flip through `$env:GLASSVIEW_DATA\raw\<session>\` and delete any frame showing
something real (a notification popup, your real inbox). Deleting is safe until step 3.

## 3. Freeze the split (1 min)

```powershell
.venv\Scripts\python -m ml.splits assign --test-frac 0.55 --val-frac 0.30 --seed 5
```

`make split` runs the same command. These are not `ml/splits.py`'s own defaults (0.35 / 0.15,
seed 0), so always pass them.

Real frames are mostly for evaluation: ~55% test, ~30% val (picks the confidence threshold),
~15% train (lets an ablation measure how much a little real data helps). Splits are whole
sessions, so the result only approximates these targets: the frozen split is 63 test / 35 val /
10 train frames (58% / 32% / 9%). After this, test frames are never edited.

## 4. Label in Label Studio (60–90 min)

```powershell
.venv\Scripts\python -m pip install label-studio
label-studio start        # opens http://localhost:8080
```

1. Create a project → **Labeling Setup → Custom template**, paste:

   ```xml
   <View>
     <Image name="image" value="$image" zoom="true" zoomControl="true"/>
     <RectangleLabels name="label" toName="image">
       <Label value="credential" background="#ff3b30" hotkey="1"/>
       <Label value="api_key" background="#ff9500" hotkey="2"/>
       <Label value="financial" background="#34c759" hotkey="3"/>
       <Label value="private_message" background="#0a84ff" hotkey="4"/>
       <Label value="personal_id" background="#bf5af2" hotkey="5"/>
     </RectangleLabels>
   </View>
   ```
2. **Import** all PNGs from `raw\*\` (drag the files in).
3. For each frame: press **1–5**, drag a box, repeat; press **Submit** even when there is nothing
   to box (that records "clean"). Rules: `docs/LABELING_GUIDE.md`. Box only the secret value,
   one box per run of messages, nothing for empty forms or prices.
4. **Export → JSON** (Label Studio's own format; preferred), then:

   ```powershell
   .venv\Scripts\python -m ml.labels import <export>.json
   ```

   A **YOLO** export still works: unzip it and pass the folder instead of the `.json` file.
   Class order and Label Studio's renamed files are handled automatically. Importing overwrites
   existing label files, including any hand-fixed test labels, so never re-import an export made before those fixes.

## 5. Done

`make verify-split` confirms the test set is intact. Training and evaluation take it from here.
A week later, re-label 30 random frames for the consistency check (LABELING_GUIDE §5).
