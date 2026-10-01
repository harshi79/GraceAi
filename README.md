# Aero · Grace — desktop client

A production-quality desktop client for **Aero's Grace AI assistant**, built on
the real Aero REST API (`https://api.aryankaushik.space`).

It replaces the previous single-file `grace_gui.py` prototype (still available
in git history) with a proper package: a pure-Python core that owns every rule,
and a thin Tk renderer on top.

```
grace/
  config.py            endpoints, timeouts, attachment policy, window geometry
  models.py            User / Conversation / Message / Attachment / Credits
  errors.py            error taxonomy + the only user-facing copy
  logutil.py           logging that can never emit a credential
  modes.py             the Grace mode registry (Normal … Deep Research)
  sse.py               incremental Server-Sent Events decoder
  client.py            AeroClient: login, OTP, chats, title, respond, upload
  controller.py        conversation state machine (one conversation per session)
  attachments.py       attachment validation + upload state machine
  markdown_render.py   dependency-free Markdown engine
  ui/                  Tkinter layer (theme, widgets, chat, composer, sidebar, app)
tests/                 315 tests, including a contract-faithful mock Aero server
run.py                 entry point
grace.spec             PyInstaller build
```

---

## 1. Dependencies

```
requests>=2.28,<3
```

`tkinter` ships with Python but is packaged separately on some systems:

| Platform | Command |
| --- | --- |
| Debian / Ubuntu | `sudo apt-get install python3-tk` |
| Fedora / RHEL | `sudo dnf install python3-tkinter` |
| Arch | `sudo pacman -S tk` |
| macOS (python.org) | bundled |
| Windows (python.org) | bundled |

Nothing else is required at runtime — Markdown, the SSE parser, the mode
registry and the attachment state machine are all implemented in-repo so the
dependency surface stays at one package.

Development/test only: `pytest`.

---

## 2. Run

```bash
python3 -m pip install -r requirements.txt
python3 run.py
```

Verbose (still fully redacted) logging on stderr:

```bash
python3 run.py --debug
```

**Check the environment before launching** (no window, no network):

```bash
python3 run.py --check          # 10 checks: python, requests, imports,
                                # tkinter, HTTPS-only origin, SSE decoder,
                                # markdown engine, mode registry, attachment
                                # policy, credential scan
python3 run.py --check -v       # ... plus the endpoint + mode tables
```

`--check` exits 0 when the API core is healthy and only prints a NOTE when
`tkinter` is missing (the window cannot open, but nothing else is broken).

Equivalent module form: `python3 -m grace`.

The window opens maximised, is resizable down to 940 × 620, and supports F11
for fullscreen (Escape leaves it).

---

## 3. PyInstaller build

```bash
python3 -m pip install pyinstaller
pyinstaller --noconfirm --clean grace.spec
```

Output: `dist/Grace` (Linux/macOS) or `dist\Grace.exe` (Windows).

One-file, windowed (no console). The spec lists every `grace.*` submodule in
`hiddenimports` because the package is only reached through `run.py`, and it
excludes `pytest`, `numpy`, `pandas`, `PyQt5` and `PySide6` to keep the bundle
small.

---

## 4. What the client speaks (and how it was established)

Every endpoint below was **observed on the real API or in the real web client's
bundles**. Where a contract could not be observed from the build environment it
is marked `inferred`, and the value is a single overridable constant in
`grace/config.py` rather than something buried in the code.

| Constant | Value | Provenance |
| --- | --- | --- |
| `PATH_AUTH_LOGIN` | `POST /api/auth/login` `{identifier, password}` | documented |
| `PATH_GRACE_CHATS` | `GET /api/ai/grace/chats` | documented |
| `PATH_GRACE_TITLE` | `POST /api/ai/grace/generate-title` `{message}` → `{title}` | documented |
| `PATH_GRACE_RESPOND` | `POST /api/ai/grace/respond` (SSE) | documented |
| `PATH_AUTH_OTP_VERIFY` | `POST /api/auth/login/verify-otp` `{identifier, code}` | **inferred** |
| `PATH_UPLOAD` | `POST /api/ai/grace/upload` (multipart) | **inferred** |
| `UPLOAD_FIELD` | `file` | **inferred** |
| `PATH_GRACE_ATTACH_FIELD` | `attachments` | **inferred** |

`python3 -c "from grace.config import contract_report; [print(r) for r in contract_report()]"`
prints this table from the running code, so the binary can never silently
drift from what was actually observed.

### Observed request / response shapes

* Login success → the user object carrying `accessToken`. A 200 with no token
  is the documented "OTP sent to registered email" branch and switches the UI
  to the 6-digit code step (matching the web client's `verifyOtp` flow).
* Unauthenticated API error shape, confirmed live:
  `{"message": "Unauthorized - No token provided", "code": "NO_TOKEN"}`.
  `GET /api/ai/grace/chats` and `GET /api/storage/files` both return exactly
  this, which is how their existence was confirmed.
* `/respond` SSE events: `{"type":"status","content":"…"}`,
  `{"type":"chunk","content":"…"}`,
  `{"type":"done", …}` then the `data: [DONE]` sentinel.
* `done` fields consumed: `fullContent`, `usedCredits`, `remainingCredits`,
  `tier`, `thinking`, `effort`, `updatedAt`, `conversationId`, `messageId`.
* Grace request fields: `message`, `conversationHistory`, `conversationId`,
  `clientMessageId`, `capabilities`, `mode`, `effort`.
* Capabilities observed on the wire: `workspace_v2`, `ask_user`,
  `drawings_v1`.

### How discovery was done

The web app is a Vite SPA behind Cloudflare. `fetch_page` strips `<script>`
tags, so asset URLs were recovered by fetching the page through
`https://validator.w3.org.nu/?doc=<url>&showsource=yes`, which returns raw
source. From there each `/assets/*.js` chunk was read directly. Confirmed and
read: the i18n bootstrap, `LoginPage`, `DrivePage`, `useWorkspaceStore`,
`StoragePlansPanel`, `AnalyticsDashboardPage`, `GraceUsagePolicyPage`, the
service worker and the react-virtuoso vendor chunk.

The Grace chat screen itself lives inside `bootstrap-DBTTzygF.js`, whose 42
`__vite__mapDeps` entries contain no Grace chat chunk — i.e. the chat UI is
inlined in the entry bundle, which the fetch tool caps at ~65 KB. That is the
hard limit on how much further static discovery can go, and it is the reason
for the `inferred` rows above.

The visual design was matched against a screenshot of the shipped Grace 2.0
web UI: the "Grace 2.0" wordmark, the "Recents" conversation rail, the account
card showing `Grace Credits <used> / <total>`, the "What are we working on?"
empty state, the four suggestion chips, the `Message Grace…` composer with a
leading `+` and a `<Mode> · <Thinking>` selector, and the footer disclaimer
"Grace can make mistakes. Your conversations are private and encrypted."

---

## 5. Feature list — what is implemented

**Window & shell**
- Opens maximised, resizable, minimum 940 × 620, F11 fullscreen, Escape leaves.
- Sidebar + main area + composer are grid-managed, so the composer stays pinned
  to the bottom and the message list re-wraps on every resize.
- Golden-green dark theme: near-black green canvas, golden-green/lime accent,
  muted olive secondary text, warm white primary text, hairline dark-green
  borders. Custom-drawn rounded buttons, avatars and scroll surfaces — no
  default Tk chrome anywhere.

**Chat**
- Left rail: Aero wordmark, Grace profile + credit balance, the current
  conversation, the signed-in account (name, handle, plan), a connection
  indicator and Sign out.
- Main area: Markdown rendering (headings, lists, tables, blockquotes, rules,
  inline code/bold/italic/strikethrough, links that open in the browser),
  fenced code blocks with a language label and a working **Copy** button,
  timestamps, per-turn mode/credit metadata, smooth scrolling with
  auto-follow only while the reader is already at the bottom.
- Empty state with the real headline, subtitle, privacy note and four
  suggestion chips that pre-fill the composer.

**Streaming**
- Incremental SSE decoder: multi-line `data:`, comments/heartbeats,
  `event:`/`id:`/`retry:`, CRLF, `[DONE]`, malformed JSON frames (skipped, not
  fatal), and UTF-8 sequences split across TCP chunks.
- "Grace is thinking…" state, live `status` labels, progressive re-render
  throttled to ~55 ms (220 ms for long answers).
- `fullContent` from the `done` event replaces the streamed text; `tier`,
  `thinking` and `effort` echoes are recorded per turn and shown in the footer.
- Credits are updated from `remainingCredits` / `usedCredits`.
- Handles HTTP errors, timeouts, connection resets mid-stream (partial answer
  is kept), server 5xx, 429 rate limiting, and user-initiated Stop.

**Composer**
- Multiline, auto-growing to 8 lines, Enter sends, Shift+Enter newlines,
  Ctrl+Enter also sends, empty/whitespace input never sends, duplicate sends
  are refused by the controller (not just the widget), send becomes Stop while
  streaming and the composer is restored on completion or error.

**Modes** — all six/seven selector entries:
`Normal`, `Normal · Thinking`, `Medium`, `Medium · Thinking`, `Ultra`,
`Ultra · Thinking`, `Deep Research`. Each contributes `mode` + `effort`; if the
server refuses a pair the client falls back once to the verified
`normal`/`instant` pair and tells the user.

**Attachments** — full workflow: picker restricted to formats Aero Drive can
preview (text/code, documents, images, audio, video, archives) with
executables explicitly blocked, size and count limits, chips with per-file
state, upload progress, success/failure, retry, remove, and the reference
passed to Grace. Files are validated *before* any network call.

**Conversation**
- Exactly one Grace conversation per client session. On start the most recently
  updated conversation from `GET /api/ai/grace/chats` is loaded (the same
  ordering the web client's "Recents" rail uses), with ordering, IDs, roles,
  content and timestamps preserved, and is then continued. A fresh account gets
  one locally minted id. There is no "+ New Chat" anywhere.
- History is rebuilt from the conversation on every request, so stale state can
  never be transmitted and an empty assistant placeholder is never sent.
- Titles come from the real `generate-title`; "New" / empty responses keep
  "New conversation".

**Security**
- The access token lives only in memory on the `requests.Session`; nothing is
  written to disk, ever.
- HTTPS is enforced — a non-loopback `http://` base URL is rejected outright.
- A real `Authorization: Bearer …` header is sent.
- A redaction filter runs over every log record: bearer tokens, JWTs,
  `password=`/`token=` assignments, e-mails, query strings and long opaque
  strings are replaced before anything reaches stderr or a debug log. The
  password field is cleared after every login attempt.
- Users never see a traceback; every failure maps to one calm sentence from
  `grace/errors.py`.

---

## 6. Testing

```bash
python3 -m pytest tests/ -q
```

**333 tests, all passing** (run 13 consecutive times with no flakes).

| File | Covers |
| --- | --- |
| `tests/mock_aero.py` | contract-faithful local Aero server (login, OTP, chats, title, SSE respond, multipart upload) |
| `test_sse.py` | SSE framing: multi-line data, comments, `[DONE]`, malformed JSON, byte-level and UTF-8 chunk splits, CRLF, unterminated frames, stats |
| `test_client.py` | login success / invalid credentials / unknown user / OTP challenge + verify + rejection, chats list parsing in five plausible shapes, block-content messages, role normalisation, title generation, SSE happy path, payload shape, 401/429/500/400, network failure, timeout, truncated stream, cancellation, 200-chunk streams, upload success/progress/failure/auth, multipart field name, HTTPS enforcement |
| `test_controller.py` | one-conversation rule, no-new-conversation API, empty-message refusal, duplicate-send protection (single and 8 concurrent threads), event ordering, streaming accumulation, `fullContent` reconciliation, status forwarding, credits, title generation once + "New" handling + failure tolerance, history rebuild, payload shape, attachment referencing and clearing, server error recovery, mode rejection fallback, verified-mode non-retry, cancellation, mode registry |
| `test_attachments.py` | accepted formats, blocked executables, unknown extensions, missing/empty/oversize/duplicate files, quota, mixed batches, upload lifecycle, failure + retry, progress, remove/clear, idempotent uploads, size formatting |
| `test_modes.py` | registry size, labels matching the shipped selector, verified default, thinking flags, payload round-trip, fallbacks, hints, unique keys |
| `test_markdown.py` | every block type, every inline style, partial-document parsing, progressive growth over a 100+ character document, 400-section performance |
| `test_errors.py` | friendly copy for every error, no tracebacks, credential scrubbing, HTTP/exception mapping, retryable flags |
| `test_redaction.py` | bearer/JWT/e-mail/query/assignment redaction, nested mappings, header scrubbing, the logging filter end-to-end |
| `test_selfcheck.py` | every `--check` probe, HTTPS-origin failure detection, the credential scan (including that it ignores the deliberate fake credentials in `tests/`), and that a missing `tkinter` is a NOTE rather than a hard failure |
| `test_integration.py` | full lifecycle against the mock server, fresh-account flow, server-supplied conversation id, long streams, malformed frames, server-error recovery, every mode end-to-end, attachment round trip, mid-stream connection drop |
| `test_ui_smoke.py` | GUI construction against a Tk stub: every widget, MarkdownView over 16 sample documents, composer keyboard/state machine, sidebar updates, chat bubbles, and the whole `GraceApp` shell including event handling, login errors, OTP switching, fullscreen, sign-out and a header/grid collision guard |

### Verified vs. not verified — read this before claiming anything

**Verified by execution in this environment:** all 333 tests above, plus `python3 run.py --check` (10/10 pass here, with the expected `tkinter` NOTE), including
the full HTTP/SSE/attachment/conversation stack against the mock server, plus
`python3 -m compileall` and `pyflakes` (clean) over the whole tree.

**Not verified, and why:** the Tk GUI itself. This build environment has no
`tkinter` build (no installation candidate for `python3-tk`) and no display, so
the GUI cannot be launched here. The `test_ui_smoke.py` suite runs the entire
`grace.ui` layer against a functional Tk stub, which proves every widget
constructs, mutates and tears down without raising and that the composer /
chat / login / sidebar / app-shell logic behaves — but it does **not** prove
pixel layout, real mouse-wheel scrolling, real font metrics, or how the theme
actually looks. Those need a machine with a display.

Likewise, no request was ever made against the live
`api.aryankaushik.space` from here (the sandbox's TLS handshake to that host is
reset, and no credentials exist). Every claim about the live API comes from the
observed evidence listed in §4.

---

## 7. API features that are **not** implementable from the exposed contract

These are things the brief asked about that the real backend does not expose
(or does not expose observably). They are listed honestly rather than faked.

1. **OTP verification endpoint.** The login *challenge* is documented (a 200
   with no token), but the second leg's URL is not observable from this
   environment. The client implements the full code-entry screen and posts to
   `POST /api/auth/login/verify-otp` `{identifier, code}` — a single
   overridable constant (`AERO_OTP_VERIFY_PATH`). If the real path differs,
   change the constant; nothing else moves.

2. **Attachment upload contract.** The browser's "Grace → Attach file" request
   could not be captured. The client implements the complete UX and posts
   multipart to `POST /api/ai/grace/upload` with field `file`
   (`AERO_UPLOAD_PATH` / `AERO_UPLOAD_FIELD`), then forwards the returned id in
   an `attachments` array on `/respond` (`AERO_ATTACH_FIELD`). The documented
   `/respond` shape carries no attachment field, so this is the one part of the
   pipeline that is inferred rather than observed. The whole thing sits behind
   `Settings.send_attachments`, a single switch.

3. **Grace capability identifiers beyond the three observed.** Only
   `workspace_v2`, `ask_user` and `drawings_v1` were seen on the wire. There is
   no evidence for capability ids for dock context, tasks, notes, calendar,
   memories, deep research or thinking, so none are invented — the client sends
   exactly the three observed values.

4. **Exact `mode` / `effort` enum values.** `("normal", "instant")` is
   documented and is the default. The remaining pairs (`medium`, `ultra`,
   `deep_research`, and `effort: "thinking"`) are inferred from the mode
   selector visible in the shipped UI (`Ultra · Thinking`) and are labelled
   `verified=False` in `grace/modes.py`. If the server rejects one, the client
   falls back to Normal and says so.

5. **Mermaid diagrams and real LaTeX typesetting.** Grace's output format for
   either could not be verified, so both are rendered as clearly-labelled
   source blocks rather than being guessed at or silently dropped. Everything
   else in Markdown is fully rendered.

6. **Drive / Workspace features.** `GET /api/storage/files`,
   `/workspace/overview`, `/workspace/notes`, `/workspace/tasks`,
   `/workspace/calendar/*` and the storage subscription endpoints are all real
   and were confirmed, but they are outside the Grace chat contract this client
   implements and are not wired up.

7. **Conversation creation / deletion / rename.** Only `GET
   /api/ai/grace/chats`, `POST /respond` and `POST /generate-title` are in
   scope, so the client loads and continues one conversation and lets the
   server mint titles. It cannot create, rename or delete conversations,
   which is also why there is deliberately no "+ New Chat" button.

8. **Session persistence.** No token, password or refresh token is stored, so
   the client always starts at the sign-in screen. The real web client persists
   a token; this client deliberately does not, per the security requirement.

---

## 8. Keyboard & UI reference

| Input | Action |
| --- | --- |
| `Enter` | Send |
| `Shift+Enter` | Newline |
| `Ctrl+Enter` | Send |
| `F11` | Toggle fullscreen |
| `Escape` | Leave fullscreen |
| `Ctrl+L` | Focus the composer |
| `Ctrl+D` | Toggle debug logging (still redacted) |
| `python3 run.py --check` | Environment self-check, no window |
| Mouse wheel | Scroll the message list (works over any child, including after a resize) |
