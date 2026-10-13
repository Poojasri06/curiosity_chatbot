/*! Curiosity LMS chat widget. One file, no dependencies.
 *
 * Add before </body> on any page:
 *   <script src="https://YOUR-CHATBOT-HOST/widget.js" defer></script>
 *
 * Optional settings, as data- attributes on that script tag:
 *   data-api          Chatbot API address. Default: the host the script was loaded from.
 *   data-color        Accent color as hex, e.g. #0d6efd (default).
 *   data-title        Panel title. Default: "Curi-Assist".
 *   data-label        Text on the launcher button. Default: "Ask Curi-Assist".
 *   data-greeting     First message shown in an empty chat.
 *   data-suggestions  Starter questions separated by |.
 *   data-position     "right" (default) or "left".
 *
 * Page scripts can call window.CuriosityChat.open() / .close().
 * Everything user-visible is added with textContent, never innerHTML.
 */
(function () {
  'use strict';
  if (window.CuriosityChat) return;

  var script = document.currentScript || document.querySelector('script[src*="widget.js"]');
  var data = (script && script.dataset) || {};

  // ---- settings ---------------------------------------------------------------
  var HEX = /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i;
  var accent = HEX.test(data.color || '') ? data.color : '#0d6efd';
  var origin = '';
  try { origin = new URL(script.src).origin; } catch (e) { /* inline script: use page origin */ }
  var apiBase = String(data.api || origin).replace(/\/+$/, '');
  var cfg = {
    title: data.title || 'Curi-Assist',
    label: data.label || 'Ask Curi-Assist',
    greeting: data.greeting || "Hello and welcome to Curiosity! I'm Curi-Assist. I can help you find the right course, browse courses by department, or answer questions about the website. What can I help you with today?",
    suggestions: (data.suggestions || 'Browse courses by department|Python courses|How do I create an account?|What can I learn here?')
      .split('|').map(function (s) { return s.trim(); }).filter(Boolean).slice(0, 5),
    left: data.position === 'left'
  };
  var TIMEOUT_MS = 30000;
  var MAX_STORED = 40;

  // Pick white or near-black text, whichever reads better on the accent color.
  function onAccent(hex) {
    var h = hex.slice(1);
    if (h.length === 3) h = h.replace(/./g, '$&$&');
    var lum = [0, 2, 4].map(function (i) {
      var c = parseInt(h.substr(i, 2), 16) / 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    var L = 0.2126 * lum[0] + 0.7152 * lum[1] + 0.0722 * lum[2];
    return 1.05 / (L + 0.05) >= (L + 0.05) / 0.058 ? '#ffffff' : '#10151c';
  }

  // ---- saved conversation (kept while the tab is open, so it survives page changes) ----
  var KEY = 'curiosity-chat:v1';
  var state = { sessionId: null, messages: [], open: false };
  try {
    var saved = JSON.parse(sessionStorage.getItem(KEY));
    if (saved && Array.isArray(saved.messages)) state = saved;
  } catch (e) { /* storage blocked: the chat still works, it just will not persist */ }
  function save() {
    state.messages = state.messages.slice(-MAX_STORED);
    try { sessionStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* ignore */ }
  }

  // ---- small DOM helpers --------------------------------------------------------
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }
  var SVG_NS = 'http://www.w3.org/2000/svg';
  function icon(paths) {
    var svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('width', '20');
    svg.setAttribute('height', '20');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    paths.forEach(function (d) {
      var p = document.createElementNS(SVG_NS, 'path');
      p.setAttribute('d', d);
      svg.appendChild(p);
    });
    return svg;
  }
  var ICONS = {
    chat: ['M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z'],
    close: ['M6 6l12 12', 'M18 6L6 18'],
    send: ['M22 2L11 13', 'M22 2l-7 20-4-9-9-4 20-7z'],
    external: ['M14 4h6v6', 'M20 4l-9 9', 'M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5']
  };
  // Only http(s) links are allowed; anything else (javascript:, data:) is dropped.
  function safeUrl(value) {
    try {
      var url = new URL(String(value), window.location.href);
      return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null;
    } catch (e) { return null; }
  }
  // Paragraphs and "- " bullet lines, built from text nodes only.
  function renderText(parent, text) {
    var list = null;
    String(text).split(/\r?\n/).forEach(function (line) {
      var bullet = line.match(/^\s*[-*•]\s+(.*)$/);
      if (bullet) {
        if (!list) { list = el('ul'); parent.appendChild(list); }
        list.appendChild(el('li', null, bullet[1]));
        return;
      }
      list = null;
      if (line.trim()) parent.appendChild(el('p', null, line));
    });
  }

  // ---- styles (inside a shadow root, so the LMS stylesheet cannot touch them) ---------
  var CSS = [
    ':host{all:initial}',
    '.root{--accent:' + accent + ';--on-accent:' + onAccent(accent) + ';--ink:#1b2430;--muted:#5b6674;--line:#d9e0e8;--tint:#eef1f5;',
    '--font:system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans",sans-serif;font:15px/1.45 var(--font);color:var(--ink)}',
    '.root *{box-sizing:border-box}',
    '[hidden]{display:none!important}',
    '.sr{position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}',
    'button,textarea{font:inherit;color:inherit}',
    'button:focus-visible,textarea:focus-visible,a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}',

    '.launcher{position:fixed;right:20px;bottom:20px;z-index:100000;display:flex;align-items:center;gap:8px;height:48px;padding:0 18px 0 14px;',
    'border:0;border-radius:24px;background:var(--accent);color:var(--on-accent);font:600 15px/1 var(--font);cursor:pointer;',
    'box-shadow:0 6px 20px rgba(16,21,28,.22)}',
    '.launcher:hover{filter:brightness(.94)}',
    '.left .launcher,.left .panel{right:auto;left:20px}',

    '.panel{position:fixed;right:20px;bottom:20px;z-index:100000;display:flex;flex-direction:column;width:min(380px,calc(100vw - 40px));',
    'height:min(580px,calc(100vh - 40px));background:#fff;border:1px solid var(--line);border-radius:14px;overflow:hidden;',
    'box-shadow:0 12px 40px rgba(16,21,28,.25);animation:rise .18s ease-out}',
    '@keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}',

    '.head{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:8px 8px 8px 16px;border-bottom:1px solid var(--line)}',
    '.title{margin:0;font:650 16px/1.3 var(--font)}',
    '.close{display:grid;place-items:center;width:40px;height:40px;border:0;border-radius:10px;background:transparent;cursor:pointer;color:var(--muted)}',
    '.close:hover{background:var(--tint);color:var(--ink)}',

    '.log{flex:1;min-height:0;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px;overscroll-behavior:contain}',
    '.turn{display:flex;flex-direction:column;gap:6px;max-width:90%}',
    '.turn.user{align-self:flex-end;align-items:flex-end}',
    '.turn.bot{align-self:flex-start}',
    '.msg{padding:9px 12px;border-radius:12px;overflow-wrap:anywhere}',
    '.msg p{margin:0}.msg p+p,.msg ul{margin-top:6px}.msg ul{margin-bottom:0;padding-left:18px}',
    '.user .msg{background:var(--accent);color:var(--on-accent);border-bottom-right-radius:4px}',
    '.bot .msg{background:var(--tint);border-bottom-left-radius:4px}',
    '.error .msg{background:#fdecea;color:#7a1c14}',
    '.retry{align-self:flex-start;margin-top:2px;padding:6px 12px;border:1px solid #e3b4af;border-radius:8px;background:#fff;color:#7a1c14;font-weight:600;cursor:pointer}',

    '.sources{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px}',
    '.course{display:flex;align-items:center;gap:10px;padding:9px 10px 9px 12px;border:1px solid var(--line);border-left:3px solid var(--accent);',
    'border-radius:8px;background:#fff;color:var(--ink);font-weight:600;font-size:14px;line-height:1.35;text-decoration:none}',
    '.course:hover{background:var(--tint)}',
    '.course span{flex:1;overflow-wrap:anywhere}.course svg{flex:none;width:16px;height:16px;color:var(--muted)}',

    '.chips{display:flex;flex-wrap:wrap;gap:8px}',
    '.chip{padding:7px 12px;border:1px solid var(--line);border-radius:999px;background:#fff;cursor:pointer}',
    '.chip:hover{border-color:var(--accent)}',

    '.typing .msg{display:flex;gap:4px;align-items:center;height:36px}',
    '.dot{width:7px;height:7px;border-radius:50%;background:var(--muted);animation:pulse 1.2s infinite ease-in-out}',
    '.dot:nth-child(2){animation-delay:.15s}.dot:nth-child(3){animation-delay:.3s}',
    '@keyframes pulse{0%,80%,100%{opacity:.25}40%{opacity:1}}',

    '.composer{display:flex;align-items:flex-end;gap:8px;padding:10px 12px;border-top:1px solid var(--line)}',
    '.input{flex:1;min-width:0;max-height:96px;resize:none;padding:9px 12px;border:1px solid var(--line);border-radius:10px;background:#fff;font-size:16px;line-height:1.35}',
    '.send{flex:none;display:grid;place-items:center;width:40px;height:40px;border:0;border-radius:10px;background:var(--accent);color:var(--on-accent);cursor:pointer}',
    '.input:focus-visible{outline-offset:-1px;border-color:var(--accent)}',
    '.send:disabled{opacity:.45;cursor:default}',
    '.note{margin:0;padding:0 14px 10px;font-size:12px;color:var(--muted)}',

    '@media (max-width:520px){',
    '.panel,.left .panel{inset:0;width:auto;height:100vh;height:100dvh;border:0;border-radius:0;box-shadow:none}',
    '.launcher{right:16px;bottom:16px}.left .launcher{left:16px}',
    '.close,.send{width:44px;height:44px}',
    '.composer{padding-bottom:max(10px,env(safe-area-inset-bottom))}}',
    '@media (prefers-reduced-motion:reduce){.panel,.dot{animation:none}.dot{opacity:.6}}',
    '@media print{:host{display:none}}'
  ].join('');

  // ---- build the widget -----------------------------------------------------------
  var host = document.createElement('div');
  host.setAttribute('data-curiosity-chat', '');
  var shadow = host.attachShadow({ mode: 'open' });
  // Styles go in as a constructable stylesheet where supported. Unlike an inline <style> tag,
  // that is not blocked by a strict Content-Security-Policy (no 'unsafe-inline' needed).
  var styled = false;
  try {
    if (typeof CSSStyleSheet === 'function' && 'adoptedStyleSheets' in shadow) {
      var sheet = new CSSStyleSheet();
      sheet.replaceSync(CSS);
      shadow.adoptedStyleSheets = [sheet];
      styled = true;
    }
  } catch (e) { /* older browser: use a style tag below */ }
  if (!styled) {
    var styleTag = el('style');
    styleTag.textContent = CSS;
    shadow.appendChild(styleTag);
  }

  var root = el('div', 'root' + (cfg.left ? ' left' : ''));

  var launcher = el('button', 'launcher');
  launcher.type = 'button';
  launcher.setAttribute('aria-haspopup', 'dialog');
  launcher.setAttribute('aria-expanded', 'false');
  launcher.setAttribute('aria-controls', 'cc-panel');
  launcher.appendChild(icon(ICONS.chat));
  launcher.appendChild(el('span', null, cfg.label));

  var panel = el('section', 'panel');
  panel.id = 'cc-panel';
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-label', cfg.title);
  panel.hidden = true;

  var head = el('div', 'head');
  head.appendChild(el('h2', 'title', cfg.title));
  var closeBtn = el('button', 'close');
  closeBtn.type = 'button';
  closeBtn.setAttribute('aria-label', 'Close chat');
  closeBtn.appendChild(icon(ICONS.close));
  head.appendChild(closeBtn);

  var log = el('div', 'log');
  log.setAttribute('role', 'log');
  log.setAttribute('aria-live', 'polite');
  log.setAttribute('aria-relevant', 'additions');

  var form = el('form', 'composer');
  var input = el('textarea', 'input');
  input.rows = 1;
  input.maxLength = 1000;
  input.placeholder = 'Ask about a course or topic';
  input.setAttribute('aria-label', 'Your message');
  var sendBtn = el('button', 'send');
  sendBtn.type = 'submit';
  sendBtn.setAttribute('aria-label', 'Send message');
  sendBtn.appendChild(icon(ICONS.send));
  form.appendChild(input);
  form.appendChild(sendBtn);

  var note = el('p', 'note', 'AI assistant. Check the course page for details.');

  panel.appendChild(head);
  panel.appendChild(log);
  panel.appendChild(form);
  panel.appendChild(note);
  root.appendChild(launcher);
  root.appendChild(panel);
  shadow.appendChild(root);

  // ---- messages -----------------------------------------------------------------------
  var greetingTurn = null;
  var pending = false;

  function scrollDown() { log.scrollTop = log.scrollHeight; }

  function sourceList(sources) {
    var items = (sources || []).map(function (s) {
      var href = s && safeUrl(s.url);
      return href ? { title: String(s.title || href), href: href } : null;
    }).filter(Boolean);
    if (!items.length) return null;
    var ul = el('ul', 'sources');
    ul.setAttribute('aria-label', 'Course links');
    items.forEach(function (item) {
      var li = el('li');
      var a = el('a', 'course');
      a.href = item.href;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.appendChild(el('span', null, item.title));
      a.appendChild(el('span', 'sr', '(opens in a new tab)'));
      a.appendChild(icon(ICONS.external));
      li.appendChild(a);
      ul.appendChild(li);
    });
    return ul;
  }

  // Buttons the service offers under an answer (for example the list of departments).
  function cleanChoices(choices) {
    return (Array.isArray(choices) ? choices : []).slice(0, 20).map(function (c) {
      if (!c || typeof c.label !== 'string' || !c.label.trim()) return null;
      return {
        label: c.label.slice(0, 60),
        category: typeof c.category === 'string' ? c.category.slice(0, 80) : '',
        offset: Math.max(0, parseInt(c.offset, 10) || 0)
      };
    }).filter(Boolean);
  }

  function choiceList(choices) {
    var items = cleanChoices(choices);
    if (!items.length) return null;
    var wrap = el('div', 'chips choices');
    items.forEach(function (c) {
      var btn = el('button', 'chip', c.label);
      btn.type = 'button';
      btn.addEventListener('click', function () {
        send(c.label, c.category ? { category: c.category, offset: c.offset } : null);
      });
      wrap.appendChild(btn);
    });
    return wrap;
  }

  function dropChoices() {
    var old = log.querySelectorAll('.choices');
    for (var i = 0; i < old.length; i++) old[i].remove();
  }

  function addTurn(role, text, sources, choices) {
    var turn = el('div', 'turn ' + role);
    var bubble = el('div', 'msg');
    renderText(bubble, text);
    turn.appendChild(bubble);
    if (role === 'bot') {
      var list = sourceList(sources);
      if (list) turn.appendChild(list);
      var buttons = choiceList(choices);
      if (buttons) turn.appendChild(buttons);
    }
    log.appendChild(turn);
    scrollDown();
    return turn;
  }

  function addTyping() {
    var turn = el('div', 'turn bot typing');
    var bubble = el('div', 'msg');
    bubble.appendChild(el('span', 'sr', 'Assistant is typing'));
    for (var i = 0; i < 3; i++) { var d = el('span', 'dot'); d.setAttribute('aria-hidden', 'true'); bubble.appendChild(d); }
    turn.appendChild(bubble);
    log.appendChild(turn);
    scrollDown();
    return turn;
  }

  function showGreeting() {
    greetingTurn = el('div', 'turn bot');
    var bubble = el('div', 'msg');
    renderText(bubble, cfg.greeting);
    greetingTurn.appendChild(bubble);
    if (cfg.suggestions.length) {
      var chips = el('div', 'chips');
      cfg.suggestions.forEach(function (text) {
        var chip = el('button', 'chip', text);
        chip.type = 'button';
        chip.addEventListener('click', function () { send(text); });
        chips.appendChild(chip);
      });
      greetingTurn.appendChild(chips);
    }
    log.appendChild(greetingTurn);
  }

  function dropSuggestions() {
    var chips = greetingTurn && greetingTurn.querySelector('.chips');
    if (chips) chips.remove();
  }

  function errorText(err) {
    var status = err && err.status;
    if (status === 429) return 'Too many questions right now. Wait a minute, then try again.';
    if (status === 422) return 'That message could not be sent. Try shorter wording.';
    if (status >= 500) return 'The assistant had a problem. Try again in a moment.';
    return 'Could not reach the assistant. Check your connection, then try again.';
  }

  function addError(question, err, extra) {
    var turn = el('div', 'turn bot error');
    var bubble = el('div', 'msg');
    renderText(bubble, errorText(err));
    turn.appendChild(bubble);
    var retry = el('button', 'retry', 'Try again');
    retry.type = 'button';
    retry.addEventListener('click', function () {
      turn.remove();
      ask(question, extra);
    });
    turn.appendChild(retry);
    log.appendChild(turn);
    scrollDown();
  }

  function setPending(on) {
    pending = on;
    sendBtn.disabled = on;
  }

  function ask(question, extra) {
    setPending(true);
    var typing = addTyping();
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, TIMEOUT_MS);
    fetch(apiBase + '/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: question,
        session_id: state.sessionId || undefined,
        category: extra && extra.category || undefined,
        offset: extra && extra.offset || undefined
      }),
      signal: controller.signal
    }).then(function (response) {
      if (!response.ok) throw { status: response.status };
      return response.json();
    }).then(function (reply) {
      state.sessionId = reply.session_id || state.sessionId;
      var sources = Array.isArray(reply.sources) ? reply.sources : [];
      var choices = cleanChoices(reply.choices);
      state.messages.push({ role: 'bot', text: String(reply.answer || ''), sources: sources, choices: choices });
      save();
      typing.remove();
      addTurn('bot', reply.answer, sources, choices);
    }).catch(function (err) {
      typing.remove();
      addError(question, err, extra);
    }).then(function () {
      clearTimeout(timer);
      setPending(false);
      if (!panel.hidden) input.focus();
    });
  }

  function send(text, extra) {
    text = String(text || '').trim();
    if (!text || pending) return;
    dropSuggestions();
    dropChoices();
    addTurn('user', text);
    state.messages.push({ role: 'user', text: text });
    save();
    input.value = '';
    resize();
    ask(text, extra);
  }

  // ---- open / close -------------------------------------------------------------------
  function open() {
    panel.hidden = false;
    launcher.hidden = true;
    launcher.setAttribute('aria-expanded', 'true');
    state.open = true;
    save();
    scrollDown();
    input.focus();
  }
  function close() {
    panel.hidden = true;
    launcher.hidden = false;
    launcher.setAttribute('aria-expanded', 'false');
    state.open = false;
    save();
    launcher.focus();
  }

  function resize() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 96) + 'px';
  }

  launcher.addEventListener('click', open);
  closeBtn.addEventListener('click', close);
  panel.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') { event.stopPropagation(); close(); }
  });
  form.addEventListener('submit', function (event) {
    event.preventDefault();
    send(input.value);
  });
  input.addEventListener('input', resize);
  input.addEventListener('keydown', function (event) {
    // Enter sends; Shift+Enter adds a line. Ignore Enter while an input method is composing text.
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      send(input.value);
    }
  });

  // ---- start ----------------------------------------------------------------------------
  if (state.messages.length) {
    state.messages.forEach(function (m, i) {
      var last = i === state.messages.length - 1;
      addTurn(m.role === 'user' ? 'user' : 'bot', m.text, m.sources, last ? m.choices : null);
    });
  } else {
    showGreeting();
  }

  function mount() {
    document.body.appendChild(host);
    if (state.open) open();
  }
  if (document.body) mount();
  else document.addEventListener('DOMContentLoaded', mount);

  window.CuriosityChat = { open: open, close: close };
})();
