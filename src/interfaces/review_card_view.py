"""Interfaces Layer: the review card, an MCP Apps view served as a ui:// resource.

MCP Apps (SEP-1865, stable 2026-01-26) lets a server ship an HTML view that a
host renders in a sandboxed iframe beside a tool's result. This module holds
the one view Volcan ships and its resource entry:

* ``uri`` is ``ui://volcan/review-card`` and ``mimeType`` is
  ``text/html;profile=mcp-app``, as the extension's "UI Resource Format"
  requires.
* ``review_dialogue_turn`` links it through ``_meta.ui.resourceUri`` (see
  ``mcp_tools.py``), which is where the extension puts the link: on the tool,
  not inside each result.
* The view speaks JSON-RPC 2.0 over ``postMessage``: it sends
  ``ui/initialize``, then ``ui/notifications/initialized``; it reads
  ``ui/notifications/tool-input`` for the call's arguments and
  ``ui/notifications/tool-result`` for its ``structuredContent``; it reports
  its height with ``ui/notifications/size-changed``.
* Confirm and Cancel send ``tools/call`` for ``review_dialogue_turn`` with the
  transcript ``confirm`` or ``cancel``, only when a person presses them. The
  server then runs the same confirm path every other surface uses: the
  single-use grant, the custody check, the live head re-read and, in live
  mode, the reviewer credential. The view adds no path around any of them.

The view loads nothing from the network, writes every server string with
``textContent``, and declares no ``csp`` domains, so a host applies the
extension's restrictive default policy. It holds no product logic: every word
and cell it shows comes from the tool result.
"""
from src.application.review_card import REVIEW_CARD_URI
from src.interfaces.mcp_protocol import ResourceDefinition

MCP_APP_MIME_TYPE = "text/html;profile=mcp-app"
MCP_APPS_PROTOCOL_VERSION = "2026-01-26"

REVIEW_CARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Volcan review card</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: var(--color-background-primary, #0f1720);
    --panel: var(--color-background-secondary, #18232f);
    --ink: var(--color-text-primary, #f3f6f9);
    --muted: var(--color-text-secondary, #b9c4cf);
    --line: var(--color-border-primary, #3a4a5a);
    --alert-bg: #3b1519;
    --alert-ink: #ffd7d9;
    --ok-bg: #12301f;
    --ok-ink: #c9f2d7;
    --focus: #ffd166;
    --add: #8fe3a8;
    --remove: #ff9aa2;
  }
  :root[data-theme="light"] {
    --bg: var(--color-background-primary, #ffffff);
    --panel: var(--color-background-secondary, #f2f5f8);
    --ink: var(--color-text-primary, #101820);
    --muted: var(--color-text-secondary, #3d4a57);
    --line: var(--color-border-primary, #9aa8b6);
    --alert-bg: #fde8ea;
    --alert-ink: #6b0f1a;
    --ok-bg: #e5f6ec;
    --ok-ink: #0d4423;
    --focus: #1d4ed8;
    --add: #0a6b2e;
    --remove: #a1121f;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; background: var(--bg); color: var(--ink); }
  body {
    font: 18px/1.45 var(--font-sans, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif);
    padding: 16px;
  }
  h1 { font-size: 1.1rem; margin: 0 0 4px; }
  .file { margin: 0 0 12px; color: var(--muted); overflow-wrap: anywhere; }
  .finding { border-radius: 10px; padding: 10px 12px; margin: 0 0 12px; font-weight: 600; }
  .finding[data-kind="match"] { background: var(--alert-bg); color: var(--alert-ink); }
  .finding[data-kind="none"] { background: var(--panel); color: var(--ink); font-weight: 400; }
  ol.lines { list-style: none; margin: 0 0 8px; padding: 0; }
  ol.lines li { border-left: 4px solid var(--line); padding: 4px 0 6px 10px; margin: 0 0 6px; }
  ol.lines li[data-kind="added"] { border-left-color: var(--add); }
  ol.lines li[data-kind="removed"] { border-left-color: var(--remove); }
  .where { display: block; font-size: 0.85rem; color: var(--muted); }
  code {
    display: block; white-space: pre-wrap; overflow-wrap: anywhere;
    font: 0.95rem/1.4 var(--font-mono, ui-monospace, "Cascadia Mono", Consolas, monospace);
  }
  .cells { display: block; font-size: 1.35rem; letter-spacing: 0.05em; overflow-wrap: anywhere; }
  .count, .note { font-size: 0.9rem; color: var(--muted); margin: 0 0 10px; }
  .action { background: var(--panel); border-radius: 10px; padding: 10px 12px; }
  .action p { margin: 0 0 8px; }
  .row { display: flex; gap: 10px; flex-wrap: wrap; }
  button {
    font: inherit; font-weight: 700; min-height: 48px; min-width: 120px; padding: 8px 18px;
    border-radius: 999px; border: 2px solid var(--ink); background: var(--bg); color: var(--ink);
    cursor: pointer;
  }
  button.primary { background: var(--ink); color: var(--bg); }
  button:focus-visible { outline: 4px solid var(--focus); outline-offset: 3px; }
  button[aria-disabled="true"] { opacity: 0.6; cursor: progress; }
  .outcome { border-radius: 10px; padding: 10px 12px; margin: 0; }
  .outcome[data-kind="sent"], .outcome[data-kind="recorded"] { background: var(--ok-bg); color: var(--ok-ink); }
  .outcome[data-kind="refused"] { background: var(--alert-bg); color: var(--alert-ink); }
  .visually-hidden {
    position: absolute; width: 1px; height: 1px; overflow: hidden;
    clip: rect(0 0 0 0); clip-path: inset(50%); white-space: nowrap;
  }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { transition: none !important; animation: none !important; scroll-behavior: auto !important; }
  }
  @media (forced-colors: active) {
    .finding, .action, .outcome { border: 2px solid CanvasText; }
    button { border-color: ButtonText; }
  }
</style>
</head>
<body>
<main id="card" aria-labelledby="cardTitle">
  <h1 id="cardTitle">Review card</h1>
  <p class="file" id="cardFile">Waiting for a review turn.</p>
  <div id="cardBody"></div>
</main>
<script>
(function () {
  "use strict";
  var PROTOCOL = "2026-01-26";
  var nextId = 1;
  var pending = {};
  var toolArguments = {};
  var latest = null;
  var busy = false;
  var refocus = false;

  function $(id) { return document.getElementById(id); }
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined && text !== null) { node.textContent = String(text); }
    return node;
  }
  function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } return node; }

  function post(message) { window.parent.postMessage(message, "*"); }
  function request(method, params) {
    var id = nextId++;
    post({ jsonrpc: "2.0", id: id, method: method, params: params });
    return new Promise(function (resolve, reject) { pending[id] = { resolve: resolve, reject: reject }; });
  }
  function notify(method, params) { post({ jsonrpc: "2.0", method: method, params: params || {} }); }

  function applyContext(context) {
    if (!context) { return; }
    if (context.theme === "light" || context.theme === "dark") {
      document.documentElement.setAttribute("data-theme", context.theme);
    }
    var vars = context.styles && context.styles.variables;
    if (vars) {
      Object.keys(vars).forEach(function (key) {
        if (/^--[a-z0-9-]+$/.test(key) && typeof vars[key] === "string") {
          document.documentElement.style.setProperty(key, vars[key]);
        }
      });
    }
  }

  function outcomeKind(outcome) {
    if (outcome.submitted) { return "sent"; }
    if (outcome.dry_run) { return "recorded"; }
    return "refused";
  }

  function textOf(result) {
    var blocks = (result && result.content) || [];
    for (var i = 0; i < blocks.length; i++) {
      if (blocks[i] && blocks[i].type === "text") { return blocks[i].text; }
    }
    return "";
  }

  function choose(transcript) {
    if (busy || !latest) { return; }
    busy = true;
    refocus = true;
    Array.prototype.forEach.call(document.querySelectorAll("#cardBody button"), function (button) {
      button.setAttribute("aria-disabled", "true");
    });
    request("tools/call", {
      name: "review_dialogue_turn",
      arguments: {
        session_id: toolArguments.session_id,
        user_id: toolArguments.user_id,
        transcript: transcript,
        approval_grant: transcript === "confirm" ? latest.approval_grant : null
      }
    }).then(function (result) {
      busy = false;
      render(result);
    }, function (error) {
      busy = false;
      render({ content: [{ type: "text", text: "The host did not run " + transcript + ": " + (error && error.message ? error.message : String(error)) }] });
    });
  }

  function renderAction(body, data) {
    var box = el("section", "action");
    box.setAttribute("aria-labelledby", "actionHeading");
    var heading = el("h2", "visually-hidden", "Review action");
    heading.id = "actionHeading";
    box.appendChild(heading);
    var outcome = data.review_outcome;
    var card = data.review_card;
    if (outcome) {
      var verdict = el("p", "outcome", outcome.spoken || "The server answered the confirmation.");
      verdict.id = "cardOutcome";
      verdict.setAttribute("data-kind", outcomeKind(outcome));
      box.appendChild(verdict);
    } else if (card.awaiting_confirmation && data.approval_grant && data.pending_review) {
      box.appendChild(el("p", null, "Request changes on " + data.pending_review.pull_request
        + " at " + String(data.pending_review.head_sha).slice(0, 7) + ": " + data.pending_review.body));
      box.appendChild(el("p", "note", "Confirm presents the single-use grant. The server re-reads the head commit before anything is recorded or sent."));
      var row = el("div", "row");
      row.setAttribute("role", "group");
      row.setAttribute("aria-label", "Confirm or cancel the staged review");
      var confirm = el("button", "primary", "Confirm");
      confirm.type = "button";
      confirm.id = "cardConfirm";
      confirm.setAttribute("aria-label", "Confirm the request changes review");
      confirm.addEventListener("click", function () { choose("confirm"); });
      var cancel = el("button", null, "Cancel");
      cancel.type = "button";
      cancel.id = "cardCancel";
      cancel.setAttribute("aria-label", "Cancel the staged review");
      cancel.addEventListener("click", function () { choose("cancel"); });
      row.appendChild(confirm);
      row.appendChild(cancel);
      box.appendChild(row);
    } else if (!card.can_submit) {
      box.appendChild(el("p", null, "A pasted patch has no pull request behind it, so a review cannot be staged from it."));
    } else {
      box.appendChild(el("p", null, "No review staged. Say request changes followed by your comment."));
    }
    body.appendChild(box);
  }

  function render(result) {
    // A result can arrive twice for one press (the host's notification and
    // the tools/call answer). Focus that was inside the card stays on the
    // element with the same id, so a redraw never drops it to the top.
    var kept = document.activeElement && document.activeElement !== document.body
      ? document.activeElement.id : "";
    var body = clear($("cardBody"));
    var data = result && result.structuredContent;
    if (!data || !data.review_card) {
      $("cardFile").textContent = textOf(result) || "This result carries no card data.";
      refocus = false;
      return;
    }
    latest = data;
    var card = data.review_card;
    $("cardTitle").textContent = data.pull_request
      ? "Review of " + data.pull_request.owner + "/" + data.pull_request.repo + " #" + data.pull_request.number
      : "Review of the pasted patch";
    $("cardFile").textContent = "File " + (card.file_index + 1) + " of " + card.total_files + ": " + card.file_path;

    var finding = el("p", "finding", card.finding
      ? card.finding
      : "No rule matched in this file. That means no rule matched, not that the change is safe.");
    finding.id = "cardFinding";
    finding.setAttribute("data-kind", card.finding ? "match" : "none");
    body.appendChild(finding);

    var linesHeading = el("h2", "visually-hidden", "Changed lines");
    linesHeading.id = "linesHeading";
    body.appendChild(linesHeading);
    var list = el("ol", "lines");
    list.setAttribute("aria-labelledby", "linesHeading");
    card.changed_lines.forEach(function (line) {
      var item = el("li");
      item.setAttribute("data-kind", line.kind);
      item.appendChild(el("span", "where",
        (line.kind === "added" ? "Added, new line " : "Removed, old line ") + line.number));
      item.appendChild(el("code", null, line.text));
      var cells = el("span", "cells", line.braille);
      cells.setAttribute("role", "img");
      cells.setAttribute("aria-label", "The same line in eight-dot code Braille, " + line.braille.length + " cells");
      item.appendChild(cells);
      list.appendChild(item);
    });
    body.appendChild(list);
    var count = "Showing " + card.changed_lines_shown + " of " + card.changed_lines_total + " changed lines in this hunk.";
    if (card.changed_lines_shown < card.changed_lines_total) { count += " Say read the lines for the rest."; }
    if (!card.braille_lossless) { count += " Braille is not lossless here. Tabs become blank cells; unsupported characters become full cells."; }
    body.appendChild(el("p", "count", count));
    renderAction(body, data);
    // A press replaces the buttons with the answer, so focus follows the
    // answer instead of falling back to the top of the frame.
    var target = refocus ? ($("cardOutcome") || $("cardFinding")) : (kept ? $(kept) : null);
    refocus = false;
    if (target) {
      if (target.tagName !== "BUTTON") { target.setAttribute("tabindex", "-1"); }
      target.focus();
    }
  }

  window.addEventListener("message", function (event) {
    if (event.source !== window.parent) { return; }
    var message = event.data;
    if (!message || message.jsonrpc !== "2.0") { return; }
    if (message.method === undefined && message.id !== undefined && pending[message.id]) {
      var waiter = pending[message.id];
      delete pending[message.id];
      if (message.error) { waiter.reject(new Error(message.error.message || "error " + message.error.code)); }
      else { waiter.resolve(message.result); }
      return;
    }
    if (message.method === "ui/notifications/tool-input") {
      toolArguments = (message.params && message.params.arguments) || {};
    } else if (message.method === "ui/notifications/tool-result") {
      render(message.params || {});
    } else if (message.method === "ui/notifications/host-context-changed") {
      applyContext(message.params);
    } else if (message.method === "ui/resource-teardown" && message.id !== undefined) {
      post({ jsonrpc: "2.0", id: message.id, result: {} });
    }
  });

  // Escape interrupts speech everywhere on the Volcan page, but a key pressed
  // inside this frame never reaches the page. This notification asks the host
  // to do what Escape does there. It is Volcan's own, not part of MCP Apps; a
  // host that does not know it ignores it.
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") { notify("notifications/volcan/interrupt", {}); }
  });

  var lastHeight = 0;
  function reportSize() {
    var height = Math.ceil(document.documentElement.getBoundingClientRect().height);
    if (height !== lastHeight) {
      lastHeight = height;
      notify("ui/notifications/size-changed", { width: Math.ceil(document.documentElement.getBoundingClientRect().width), height: height });
    }
  }
  if (window.ResizeObserver) { new ResizeObserver(reportSize).observe(document.documentElement); }

  request("ui/initialize", {
    appInfo: { name: "volcan-review-card", version: "0.1.0" },
    appCapabilities: { availableDisplayModes: ["inline"] },
    protocolVersion: PROTOCOL
  }).then(function (result) {
    applyContext(result && result.hostContext);
    notify("ui/notifications/initialized", {});
    reportSize();
  }, function () {
    $("cardFile").textContent = "The host refused ui/initialize, so no review can be shown here.";
  });
}());
</script>
</body>
</html>
"""


def review_card_resource() -> ResourceDefinition:
    return ResourceDefinition(
        uri=REVIEW_CARD_URI,
        name="review_card",
        title="Volcan review card",
        description=(
            "The file in focus, the first finding a rule matched in it, its changed lines with "
            "each line in eight-dot code Braille, and Confirm or Cancel while a request changes "
            "review is staged. Rendered from review_dialogue_turn's structuredContent."
        ),
        mime_type=MCP_APP_MIME_TYPE,
        read_text=lambda: REVIEW_CARD_HTML,
        # No csp domains: the view makes no network request, so the host's
        # restrictive default applies. prefersBorder asks for a visible edge.
        contents_meta={"ui": {"prefersBorder": True}},
    )
