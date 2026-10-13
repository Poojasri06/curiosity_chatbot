# Deploy the chatbot and connect it to curiosity.live

Do these in order. Each step ends with a check.

## 1. Run it on your laptop first
```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt
cp .env.example .env     # set LLM_PROVIDER=gemini and LLM_API_KEY=<free key>, DEMO_PAGE=true
set -a && source .env && set +a && uvicorn app.main:app --reload
```
Check: open http://localhost:8000/demo and ask "I want to learn python". You should get an answer with a course link.
If the answer says "matching courses" without AI wording, the AI key is wrong (the service is using its search fallback).

## 2. Put the service on a public HTTPS host
Any host that runs a Docker image or a Python web service works (Render, Railway, Fly.io, a small VPS). Free plans change, so
check current limits, and note that some free plans put the service to sleep when idle (the first question is then slow).
Use the included `Dockerfile` (or start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'`).

Only use `--forwarded-allow-ips='*'` behind the host's own proxy (Render, Railway, Fly). If the service is exposed directly to the internet, visitors could fake their address to dodge the limits.

Set these environment variables on the host (never commit them):

| Variable | Value |
| --- | --- |
| `LLM_PROVIDER` | `gemini` or `groq` |
| `LLM_API_KEY` | your free key |
| `ALLOWED_ORIGINS` | `https://curiosity.live` (exactly what visitors see; add `https://www.curiosity.live` if used) |
| `LMS_BASE_URL` | `https://curiosity.live` |
| `DEMO_PAGE` | leave unset |

Check: `https://YOUR-HOST/health` shows `"status":"ok"`, your provider, and `"courses":702`.

## 3. Test the live service by hand
```bash
curl -s https://YOUR-HOST/chat -H 'Content-Type: application/json' -H 'Origin: https://curiosity.live' \
     -d '{"message":"python courses"}' -D - | head -20
```
Check: status 200 and an `access-control-allow-origin: https://curiosity.live` header. Open one returned course link and confirm the page loads.

## 4. Add the widget to the LMS repo
Follow "Add it to the LMS repo (patch)" in README.md, then push the branch and open a pull request.

## 5. Turn it on (needs the Kealogics developers)
On the LMS server:
1. In `.env` add `CHATBOT_URL=https://YOUR-HOST`, then run `php artisan config:clear`.
2. In the server's CSP file (`.allowedOrigins`), allow `https://YOUR-HOST` so the browser can load the script and call `/chat`.
   Ask them how that file is formatted; I have not seen the real one.
3. Tenant sites: set `COURSE_PATH` / `QUIZ_PATH` on the chatbot to match their URL prefix.

Check: open curiosity.live, hard refresh, the "Find a course" button appears bottom right, and a question returns a course link.
If it does not appear: open browser DevTools, Console tab. A message mentioning "Content Security Policy" means step 5.2 is missing;
a CORS message means `ALLOWED_ORIGINS` does not exactly match the site address.

## 6. Keep the course list fresh
`data/courses.json` is a snapshot. When courses change, export again (`scripts/export_courses.py`), rebuild, and redeploy.
A nightly sync from the LMS database is the next improvement.

## Turning it off
Remove `CHATBOT_URL` from the LMS `.env` and run `php artisan config:clear`. The widget disappears; nothing else changes.
