# Curiosity LMS Chatbot

A small, separate service plus a chat widget for the Curiosity LMS.
The service reads an exported copy of the course catalogue and never touches the LMS server or database.

## Status

Phase 1, plan steps 2 to 5 are done:

1. Service skeleton: health check, chat endpoint, settings.
2. Course catalogue: 702 published items (697 courses, 5 quizzes) searched by keyword (BM25).
3. Answer layer: finds matching courses, asks a free AI model to answer from them, and adds links only for
   courses the answer names. If the AI provider fails, users get a plain list of matching courses.
4. Chat widget: one JavaScript file the service hosts itself (`/widget.js`).

Rate limits (step 7) are done: per visitor per minute and per day, plus a daily cap for the whole service.
Next: FAQ answers and support handoff (step 6). Deployment steps are in `DEPLOY.md`.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env           # then edit it, see "Add a free AI key"
set -a && source .env && set +a
uvicorn app.main:app --reload  # http://localhost:8000/docs
```

Set `DEMO_PAGE=true` in `.env` and open http://localhost:8000/demo to see the widget on a sample page.

## Add a free AI key

1. Get a free key: Google AI Studio (Gemini) or the Groq console.
2. In `.env` set, for example:
   ```
   LLM_PROVIDER=gemini
   LLM_API_KEY=your-key
   ```
   or `LLM_PROVIDER=groq`. The key can also be named `GEMINI_API_KEY` / `GROQ_API_KEY`.
3. Restart. `GET /health` shows the provider and how many courses are loaded.

Default models are `gemini-3.5-flash-lite` and `openai/gpt-oss-20b`. Free tiers and model names change,
so if a provider rejects the model, set `LLM_MODEL` to one listed in its docs. Any other
OpenAI-compatible service works with `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL` and `LLM_MODEL`.

## Put the widget on the LMS

Add one line before `</body>` on the pages that should show it. On the current LMS theme that is the end of
`resources/views/frontend/infixlmstheme/partials/_footer.blade.php`:

```html
<script src="https://YOUR-CHATBOT-HOST/widget.js" defer></script>
```

This is the only change the LMS needs, and it belongs to the LMS developers. Optional settings go on the same tag:

| Attribute | Meaning | Default |
| --- | --- | --- |
| `data-color` | Accent color, hex like `#0d6efd` | `#0d6efd` (LMS blue) |
| `data-title` | Panel title | Curi-Assist |
| `data-label` | Text on the launcher button | Ask Curi-Assist |
| `data-greeting` | First message | "Hello and welcome to Curiosity! ..." |
| `data-suggestions` | Starter questions, separated by `\|` | Browse courses by department, Python courses, How do I create an account?, What can I learn here? |
| `data-position` | `right` or `left` | right |
| `data-api` | Chatbot address | the host the script came from |

A page link can open the chat with `CuriosityChat.open()`.

How it behaves: it lives in a Shadow DOM, so the LMS styles cannot change it; it keeps the conversation while
the tab is open, including across page changes; answers are inserted as text only, never HTML, and only
http(s) links are shown; Escape closes it; it works with a keyboard and on phones (full screen). It has
screen-reader labels (dialog, live message log, named buttons) but has not been tried with a real screen reader yet.

### Before going live

- **Public HTTPS address.** The service must be reachable from visitors' browsers at a public `https://` address.
  Browsers block a public site from calling a service on `localhost` or a private network address, and block
  `http://` calls from an `https://` page.
- **Allow the LMS site.** Set `ALLOWED_ORIGINS=https://curiosity.live` (the exact address visitors use,
  comma separated for several). Any other website is refused by the browser.
- **Course links.** Set `LMS_BASE_URL=https://curiosity.live` if the widget is not served from the LMS site itself,
  and open one link from an answer to confirm the page exists.
- **Turn off the demo page:** leave `DEMO_PAGE` unset.
- **Rate limits** are built in (see Settings). Behind a proxy the service must run with `--proxy-headers` (the Dockerfile does) so limits use each visitor's real address.

## Try the API

```bash
curl localhost:8000/health
curl -X POST localhost:8000/chat -H 'Content-Type: application/json' \
     -d '{"message": "I want to learn python"}'
```

The reply has `answer`, `sources` (title and link for each course named), `session_id`, and `mode`
(`ai` normally, `search` when the AI provider was unavailable).

## Refresh the course data

```bash
python scripts/export_courses.py path/to/lms-dump.sql -o data/courses.json
python scripts/eval_search.py     # checks search quality (25 questions + 4 off-topic)
```

Later this export is replaced by a nightly sync from the LMS database, producing the same JSON.

## Test it

```bash
pytest        # no API key needed: the AI provider is faked in tests
```

Browser tests run the real widget in Chromium. They need `playwright install chromium` once and are skipped
if a browser is not available.

## Settings (environment variables)

| Variable | Meaning | Default |
| --- | --- | --- |
| `LLM_PROVIDER` | `echo`, `gemini`, `groq` or `openai_compatible` | `echo` |
| `LLM_API_KEY` | Provider key (also `GEMINI_API_KEY`, `GROQ_API_KEY`) | none |
| `LLM_BASE_URL`, `LLM_MODEL` | Override provider endpoint or model | provider default |
| `LLM_TIMEOUT` | Seconds to wait for the AI provider | `20` |
| `COURSES_PATH` | Exported course data | `data/courses.json` |
| `LMS_BASE_URL` | Site address for course links | empty (relative links) |
| `COURSE_PATH`, `QUIZ_PATH` | Link patterns, `{slug}` is replaced (e.g. `/acme/courses-details/{slug}` for a tenant site) | `/courses-details/{slug}`, `/quiz-details/{slug}` |
| `ALLOWED_ORIGINS` | Websites allowed to call the API from a browser | none |
| `DEMO_PAGE` | Serve `/demo`, a sample page with the widget | off |
| `RATE_PER_MINUTE`, `RATE_PER_DAY`, `RATE_GLOBAL_PER_DAY` | Question limits per visitor and for everyone (0 = off) | 10, 150, 2000 |

## Layout

```
app/main.py        API: GET /health, POST /chat, GET /widget.js (and /demo when enabled)
app/answer.py      Search, ask the AI, add links, fall back to search results
app/catalogue.py   Course data and keyword search
app/llm.py         AI providers (Gemini, Groq, any OpenAI-compatible service)
app/prompts.py     Instructions sent to the AI model
app/config.py      Settings from environment variables
app/schemas.py     Request and response shapes
widget/widget.js   The chat widget (one file, no dependencies)
widget/demo.html   Sample page with deliberately hostile styles, for testing
scripts/           export_courses.py, eval_search.py
data/courses.json  Exported course catalogue
tests/             Automated tests (API, search, AI client, widget in a real browser)
```

## Known limits (planned in later steps)


- The service keeps no chat history: each message is answered on its own (the widget shows the conversation).
- Search is keyword-based; it cannot match a topic described in different words than the course text.
- Answer quality with a real AI model should be checked with real questions before launch.
- The widget is English-only for its own text (buttons, messages).

## Add it to the LMS repo (patch)

`lms-integration.patch` changes three files in the LMS repo and is off until `CHATBOT_URL` is set:
`config/chatbot.php` (new), `resources/views/frontend/infixlmstheme/partials/_chatbot.blade.php` (new),
and one `@include` line at the end of `_footer.blade.php`.

```bash
cd curiasity_live && git checkout -b feature/course-chatbot
git apply --check /path/to/lms-integration.patch && git apply /path/to/lms-integration.patch
git add config/chatbot.php resources/views/frontend/infixlmstheme/partials/_chatbot.blade.php \
        resources/views/frontend/infixlmstheme/partials/_footer.blade.php
git commit -m "Add course chatbot widget (off unless CHATBOT_URL is set)"
```

Then in the LMS `.env`: `CHATBOT_URL=https://your-chatbot-host`, and run `php artisan config:clear`.
The LMS Content-Security-Policy (`.allowedOrigins` file on the server) must allow the chatbot host for scripts and connections.
Tenant sites need `COURSE_PATH` / `QUIZ_PATH` set on the chatbot to match their URL prefix.

## Curi-Assist features

- **Browse by department.** "List all courses" asks which department (Programming, Business, Technology ...), then lists that
  department's courses 8 at a time with "Show more" and "Other departments" buttons. No AI is used, so the lists are exact.
  Similar categories are merged for display (see `ALIASES` in `app/browse.py`).
- **Website help with direct links.** Questions about creating an account, signing in, forgotten passwords, contacting the team,
  becoming an instructor, verifying a certificate and similar get a fixed answer plus the page link (see `app/help.py`).
  Links use `LMS_BASE_URL`. Edit the paths there if the site changes them.
- **Settings are read from `.env` automatically** when you start with `uvicorn` (variables set in the terminal or on the host win).
