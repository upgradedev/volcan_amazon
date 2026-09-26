"""Structural, accessibility and honesty assertions over the companion document.

These are static DOM assertions parsed with the standard library. The separate
``test_browser_journey.py`` process drives Chromium; this file checks structural
contracts that are faster and clearer to diagnose without a browser.

Two things are being defended.

**Accessibility**, because Volcan's whole claim is that a blind or
mobility-impaired developer can drive it. A control that cannot be reached by
keyboard, a result that is never announced, or an animation that ignores a
reduced-motion preference is a product defect, and these tests fail on each.

**Honesty**, because the page is the first thing a judge sees. A result written
into the markup, a status not computed from a response, or a latency literal
typed by a developer would each be a lie told in the product's shop window.
These tests fail on those too.
"""
import os
import re
from html.parser import HTMLParser

INDEX_PATH = os.path.join(os.path.dirname(__file__), "../../docs/index.html")


def read_html() -> str:
    with open(INDEX_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def script_body() -> str:
    """Just the JavaScript, for assertions about behaviour rather than markup."""
    return "\n".join(re.findall(r"<script\b[^>]*>(.*?)</script>", read_html(), flags=re.S))


class TagCollector(HTMLParser):
    """Collects every start tag with its attributes, for structural assertions."""

    def __init__(self):
        super().__init__()
        self.tags: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, {key: (value or "") for key, value in attrs}))

    def of(self, name: str) -> list[dict[str, str]]:
        return [attrs for tag, attrs in self.tags if tag == name]


def parsed() -> TagCollector:
    collector = TagCollector()
    collector.feed(read_html())
    return collector


# --- structure --------------------------------------------------------------

def test_companion_document_exists_and_names_the_product():
    html = read_html()
    assert os.path.exists(INDEX_PATH)
    assert "Volcan" in html
    assert "Accessible AI agent forge" in html


def test_the_five_second_read_is_above_the_fold():
    """The first heading must state the persona's outcome, not the tech stack."""
    html = read_html()
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.S)
    assert h1, "the page has no h1"
    headline = re.sub(r"<[^>]+>", "", h1.group(1)).strip()
    assert "Hear your code review" in headline
    assert html.index("<h1") < html.index('id="runReview"'), "the sentence must precede the button"


def test_the_primary_action_precedes_secondary_navigation_and_proof_panels():
    """A first-time visitor should reach the product before the evidence console."""
    html = read_html()
    hero = html.index('id="runReview"')
    assert hero < html.index('class="jump"')
    assert hero < html.index('id="mcp"')
    assert hero < html.index('id="governance"')


def test_exactly_one_primary_action_is_marked_as_the_hero():
    html = read_html()
    assert html.count('data-testid="primary-hero-action"') == 1
    dom = parsed()
    heroes = [attrs for attrs in dom.of("button") if "cta" in attrs.get("class", "")]
    assert len(heroes) == 1, f"there must be exactly one visually primary button, found {len(heroes)}"
    assert heroes[0].get("id") == "runReview"


def test_core_controls_are_present():
    html = read_html()
    for hook in (
        "runReview", "diffInput", "earconWave", "brailleOutput", "auditVault",
        "runMcp", "endMcp", "stageBtn", "approveBtn", "rejectBtn",
        "speakAgain", "level1", "drillDown", "copyBraille", "retryHealth",
        "prUrl", "openReview", "micToggle", "stopSpeech", "commandInput", "sayCommand",
        "reviewComment", "cmdRequestChanges", "cmdConfirm", "cmdCancel",
        "dialogueLog", "dialogueState", "reviewPane", "fidelityCode", "fidelityLiterary",
    ):
        assert f'id="{hook}"' in html, f"missing control hook: {hook}"


def test_diff_presets_are_well_formed_patches():
    """Four presets, one per syntax-tree rule plus a control.

    What each one *produces* is asserted in
    ``tests/e2e/test_shipped_presets_reach_their_rule.py``, which runs them
    through the production parser. This only checks the page still carries four
    well-formed patches and four wired chips to load them with.
    """
    html = read_html()
    assert html.count("diff --git") >= 4
    for number in (1, 2, 3, 4):
        assert f'id="preset{number}"' in html, f"preset chip {number} is missing"
    assert "user.role" in html, "the inverted authorization patch is gone"
    assert "allow_origins" in html, "the widened cross-origin patch is gone"
    assert "verify_signature" in html, "the removed verification call patch is gone"
    assert "data.strip()" in html, "the benign control patch is gone"


def test_lease_countdown_contract():
    html = read_html()
    assert "setInterval" in html
    assert "LEASE ACTIVE" in html
    assert "LEASE EXPIRED" in html
    assert "300" in html


# --- every result comes from a real request ---------------------------------

REAL_ENDPOINTS = (
    "/health",
    "/api/digest_semantic_diff",
    "/api/braille/diff_digest",
    "/api/drill_down_section",
    "/api/stage_governed_action",
    "/api/confirm_action",
    "/api/audit_log",
    "/api/review/turn",
    "/mcp",
)


def test_every_panel_is_driven_by_a_real_endpoint():
    script = script_body()
    assert "fetch(" in script
    for endpoint in REAL_ENDPOINTS:
        assert endpoint in script, f"the page never calls {endpoint}"


def test_the_mcp_panel_performs_a_real_handshake():
    """The strongest answer to the track question is a live protocol handshake."""
    script = script_body()
    assert '"initialize"' in script
    assert '"tools/list"' in script
    assert '"notifications/initialized"' in script
    assert "Mcp-Session-Id" in script, "the session id must be read from the response headers"
    assert "MCP-Protocol-Version" in script, "requests after initialize must declare the version"
    assert "inputSchema" in script, "the published tool schemas must be rendered"


def test_latency_is_measured_and_never_typed():
    script = script_body()
    assert script.count("performance.now()") >= 2, "durations must be measured, not written"
    # A latency literal such as "16.4ms" or "Latency: 24 ms" is a fabricated number.
    fabricated = re.findall(r"\d+(?:\.\d+)?\s*(?:ms|milliseconds)\b", script, flags=re.I)
    assert fabricated == [], f"hardcoded latency literals in the page: {fabricated}"


def test_the_synthesis_engine_is_read_from_the_response():
    script = script_body()
    assert "synthesis_mode" in script
    assert 'data.synthesis_mode === "bedrock"' in script, (
        "which engine ran must be decided by the response, not by the page"
    )


def test_the_first_screen_says_a_model_can_answer_and_who_reports_it():
    """A judge must not have to scroll to learn the product has an AI path.

    Until 2026-09-26 this sentence sat in the header as "Bedrock attempt through
    anthropic[bedrock]" and "Synthesis engine names who answered". A design
    review called the package name in the header jargon, and the header's
    words were needed for the finding the preview now leads with. The same
    facts moved into the engine disclosure beside the answer drawn on load:
    one press from the first screen, never scrolled to, and still naming the
    package and the meter. They must not hide in a title attribute.
    """
    html = read_html()
    first_screen = html.split('id="patchEditor"', 1)[0]
    why = first_screen.split('id="previewEngineWhy"', 1)[1].split("</div>", 1)[0]
    assert "Amazon Bedrock" in why, (
        "the first screen must state that a Bedrock model can synthesize the digest"
    )
    assert "anthropic[bedrock]" in why, (
        "the first screen must name the package that enables the model path"
    )
    assert "Synthesis engine" in why and "meter" in why, (
        "the first screen must point at the meter that reports which engine answered"
    )
    assert 'aria-controls="previewEngineWhy"' in first_screen, (
        "the disclosure must be opened by a button on the first screen"
    )
    assert "title=" not in why
    assert "will be answered by Amazon Bedrock" not in first_screen, (
        "the page may say a model can answer, never that one did"
    )


def test_the_first_screen_says_this_is_not_an_alexa_skill_and_names_the_simulation():
    """A review round found zero occurrences of 'simulat', 'alexa' or 'skill' in
    this file while the README claimed the page said so on screen. The label
    now has to sit in the header, which is read before any button is pressed,
    and it has to name both halves: what is simulated and what is live."""
    header = read_html().split("<main", 1)[0].lower()
    for word in ("alexa", "skill", "simulat"):
        assert word in header, f"the first screen never says '{word}'"
    assert "not an alexa skill" in header
    assert "live" in header and "dry-run" in header, (
        "the label must say what is live and what is dry-run in the same breath"
    )


def test_the_earcon_empty_state_names_both_cues():
    """The pre-verbal triage layer is only real if the page can be checked.

    Naming both cue types lets a reviewer press two presets and confirm the
    audio differs, which is the claim four documents make.
    """
    html = read_html()
    caption = html.split('id="earconCaption"', 1)[1].split("</p>", 1)[0]
    # Plain words since 2026-09-26: a design review flagged the raw enum names
    # SECURITY_FINDING and DIFF_READY on the first screen. The server's type
    # name still reaches the caption after a press, from the response.
    assert "finding" in caption and "clean" in caption
    assert "Rising cue" in caption and "Falling cue" in caption


def test_an_unanswered_model_call_prints_its_reason_beside_the_engine():
    """A fallback with no reason is indistinguishable from a design decision."""
    script = script_body()
    assert "synthesis_fallback_reason" in script, (
        "the page must render why no model answered, not only that none did"
    )
    assert "meterEngineNote" in script


def test_the_health_line_does_not_promise_a_model_answer():
    """Credentials resolving says nothing about whether Bedrock replies."""
    script = script_body()
    assert "may be answered by Amazon Bedrock" not in script, (
        "the page must not predict a model answer from the presence of credentials"
    )


def test_the_connection_line_reads_the_resolved_capability_not_a_half_fact():
    """Credentials alone cannot say whether a call can even be attempted.

    Without the SDK nothing leaves the server process, so a page that decides
    from ``bedrock_credentials_present`` tells a reviewer the model path is
    available on a machine where it cannot run. The server resolves both facts
    into one field, and the page has to print that one.
    """
    script = script_body()
    assert "bedrock_model_path" in script, (
        "the connection line must read the resolved capability the server computed"
    )
    assert "resolved_capability" in script
    assert "bedrock_credentials_present" not in script, (
        "the page still decides from the credential boolean alone"
    )


def test_the_earcon_played_is_the_wav_the_server_returned():
    """No browser oscillator. The judge hears the product's own audio."""
    script = script_body()
    assert "wav_base64" in script
    assert "atob" in script and "Uint8Array" in script
    assert 'type: "audio/wav"' in script
    assert "createObjectURL" in script
    assert "OscillatorNode" not in script and "createOscillator" not in script, (
        "the page must not synthesize its own substitute for the product's audio"
    )


def test_the_page_holds_no_second_implementation_of_the_product():
    """A browser reimplementation is a simulation wearing the product's clothes."""
    script = script_body()
    for banned in ("localDigest", "jsTextToBraille", "BRAILLE_MAP", "simulatedNotice"):
        assert banned not in script, f"in-browser reimplementation still present: {banned}"


def test_no_result_is_written_with_inner_html():
    script = script_body()
    assignments = re.findall(r"\.(?:inner|outer)HTML\s*[=+]|insertAdjacentHTML", script)
    assert assignments == [], (
        f"server strings must be inserted with textContent, found: {assignments}"
    )


def test_the_page_makes_no_connection_claim_before_a_real_fetch():
    html = read_html()
    script = script_body()
    assert 'data-state="checking"' in html, "the initial state must be 'checking', not 'connected'"
    assert 'fetch(base + "/health"' in script, "connection state must come from a real request"
    assert 'setConnection("live"' in script and 'setConnection("offline"' in script


def test_the_page_carries_no_fabricated_status_badges():
    html = read_html()
    for banned in (
        "LIVE INGESTION", "AWS SYNCED", "RULES SEC 4 VERIFIED", "Fire TV Pairing",
        "100% PASS", "ZERO DETECTED", "Tamper Resistance",
    ):
        assert banned not in html, f"fabricated status badge present: {banned}"


def test_the_offline_state_explains_itself_and_names_the_command():
    html = read_html()
    script = script_body()
    assert "offlineCard" in script
    assert "python -m src.interfaces.mcp_server" in html, (
        "an unreachable server must be answered with the command that starts one"
    )


# --- the voice loop: listen, read back, act ---------------------------------
#
# What these can and cannot prove, stated plainly. The browser's
# SpeechRecognition API cannot be driven headlessly and no browser runs in this
# suite, so nothing here proves that a microphone heard anything. The state
# machine the page drives lives on the server and is proven with injected
# transcripts in tests/unit/test_review_dialogue.py and over HTTP in
# tests/integration/test_review_dialogue_api.py. These assertions pin the
# page's half of the contract: it listens where it can, it always keeps a typed
# path, it interrupts itself, it reads back before it acts, and it announces
# every state change.


def function_body(name: str) -> str:
    """The source of one top-level function in the page script."""
    script = script_body()
    start = script.index(f"function {name}(")
    rest = script[start:]
    following = re.search(r"\n    (?:async )?function ", rest[1:])
    return rest if following is None else rest[: following.start() + 1]


def test_the_page_listens_where_it_can_and_always_keeps_a_typed_path():
    html = read_html()
    script = script_body()
    assert "window.SpeechRecognition || window.webkitSpeechRecognition" in script
    assert 'id="commandInput"' in html and 'id="sayCommand"' in html, "the typed path must always exist"
    assert 'event.key === "Enter"' in script, "Enter in the command box must send the command"
    body = function_body("toggleListening")
    assert "no SpeechRecognition" in body, "a browser without a recogniser must be told so"
    assert '$("commandInput").focus()' in body, "and be sent to the typed path"
    assert "onresult" in body and "sendTranscript(transcript" in body


def test_every_command_travels_to_the_server_and_a_new_one_interrupts_speech():
    body = function_body("sendTranscript")
    assert '"/api/review/turn"' in body
    assert body.index("stopAudio()") < body.index('postJson("/api/review/turn"'), (
        "a new command must silence the current speech before the server is asked"
    )
    assert "approval_grant: Review.grant" in body, "a confirm must present the grant the server issued"
    assert 'event.key === "Escape") { stopAudio(); stopListening();' in script_body()


def test_the_readback_precedes_the_answer_and_both_are_spoken_at_the_returned_rate():
    body = function_body("sendTranscript")
    assert body.index("data.readback") < body.index("data.spoken"), "readback first"
    speak = function_body("speakTurn")
    assert "[data.readback, data.spoken]" in speak
    assert "utterance.rate = data.speech_rate" in speak, "slower and faster are the server's numbers"
    assert "data.silent" in speak, "a stop turn must not be spoken over"


def test_every_dialogue_state_change_is_announced_through_a_live_region():
    html = read_html()
    script = script_body()
    assert re.search(r'id="reviewStatus"[^>]*role="status"[^>]*aria-live="polite"', html)
    assert re.search(r'id="dialogueLog"[^>]*aria-live="polite"', html)
    assert re.search(r'id="reviewPane"[^>]*role="status"[^>]*aria-live="polite"', html)
    assert 'announce("reviewStatus"' in script
    assert "setDialogueState(data)" in function_body("sendTranscript")
    for state in ("IDLE", "OVERVIEW", "FILE", "LINES", "CONFIRM_REVIEW", "SUBMITTED", "RECORDED", "REFUSED"):
        assert f"{state}:" in script, f"the page has no label for dialogue state {state}"


def test_the_review_outcome_is_the_servers_and_a_dry_run_is_never_dressed_as_a_send():
    script = script_body()
    pane = function_body("renderReviewPane")
    assert "outcome.submitted" in pane and "outcome.dry_run" in pane and "outcome.refusal_code" in pane
    assert "recorded and not sent" in pane
    assert "VOLCAN_GITHUB_WRITE" in pane, "the dry-run row must name the switch that changes it"
    assert "github_review_path" in script, "the review path comes from GET /health"
    assert "GITHUB_TOKEN" not in script and "token_present" not in script, (
        "the page never handles or displays a token fact of its own"
    )
    assert "DRY_RUN_RECORDED" not in script or "renderEarcon(data.earcon)" in script


def test_the_keyboard_map_covers_the_dialogue():
    html = read_html()
    script = script_body()
    for key in ("4", "5", "6"):
        assert f"<kbd>Alt</kbd>+<kbd>{key}</kbd>" in html, f"Alt+{key} is not documented"
    assert '"4": "commandInput"' in script and '"6": "prUrl"' in script
    assert 'event.key === "5") { event.preventDefault(); toggleListening();' in script
    assert "stop listening" in html.lower(), "Escape must be documented as stopping the microphone too"


def test_the_braille_panel_prints_the_fidelity_and_the_loss_beside_the_cells():
    html = read_html()
    script = script_body()
    assert "fidelity: State.brailleFidelity" in script, "the page must ask for a fidelity, not assume one"
    body = function_body("renderBraille")
    for field in ("data.fidelity", "data.lossless", "data.disclosure"):
        assert field in body, f"the Braille caption never prints {field}"
    assert "six-dot Unicode" not in html, "the panel must not hardcode the six-dot table any more"
    assert 'id="fidelityCode"' in html and 'id="fidelityLiterary"' in html


# --- semantic landmarks and roles -------------------------------------------

def test_page_uses_semantic_landmarks():
    html = read_html()
    for landmark in ("<header", "<nav", "<main", "<footer", "<section"):
        assert landmark in html, f"missing landmark: {landmark}"
    assert 'role="banner"' in html
    assert 'role="contentinfo"' in html
    assert 'id="main"' in html


def test_every_section_is_labelled_by_a_heading():
    dom = parsed()
    sections = dom.of("section")
    assert len(sections) >= 4
    html = read_html()
    for section in sections:
        labelled_by = section.get("aria-labelledby")
        assert labelled_by, f"section without aria-labelledby: {section}"
        assert f'id="{labelled_by}"' in html, f"aria-labelledby points at a missing id: {labelled_by}"


def test_every_rendering_panel_is_labelled_by_a_heading():
    dom = parsed()
    articles = dom.of("article")
    assert len(articles) == 3, "the transformation shows exactly three renderings"
    html = read_html()
    for article in articles:
        labelled_by = article.get("aria-labelledby")
        assert labelled_by and f'id="{labelled_by}"' in html


def test_the_page_declares_meaningful_roles():
    html = read_html()
    for role in ('role="status"', 'role="alert"', 'role="group"', 'role="region"', 'role="img"'):
        assert role in html, f"missing role: {role}"


def test_navigation_and_button_groups_are_named():
    dom = parsed()
    navs = dom.of("nav")
    assert navs and all(nav.get("aria-label") for nav in navs)
    groups = [attrs for tag, attrs in dom.tags if attrs.get("role") == "group"]
    assert groups and all(group.get("aria-label") for group in groups)


def test_the_scrollable_braille_region_is_named_and_focusable():
    dom = parsed()
    regions = [attrs for tag, attrs in dom.tags if attrs.get("role") == "region"]
    assert regions, "the Braille stream must be an addressable region"
    braille = [attrs for attrs in regions if attrs.get("id") == "brailleOutput"]
    assert braille, "the Braille region must carry the id the keyboard map points at"
    assert braille[0].get("tabindex") == "0", "a scrollable region must be reachable by keyboard"
    assert braille[0].get("aria-label")


# --- keyboard reachability --------------------------------------------------

def test_there_are_no_click_handlers_on_non_interactive_elements():
    """A span or div with onclick is unreachable by keyboard. There must be none."""
    dom = parsed()
    offenders = [
        (tag, attrs) for tag, attrs in dom.tags
        if "onclick" in attrs and tag not in {"button", "a", "input"}
    ]
    assert offenders == [], f"keyboard-unreachable click handlers: {offenders}"


def test_every_action_is_a_real_button_with_an_explicit_type():
    dom = parsed()
    buttons = dom.of("button")
    assert len(buttons) >= 12
    for button in buttons:
        assert button.get("type") == "button", f"button without an explicit type: {button}"


def test_every_button_carries_a_visible_reason_or_title():
    """Gate H2: no control is presented without an explanation beside it."""
    dom = parsed()
    for button in dom.of("button"):
        assert button.get("title") or button.get("aria-label"), f"unexplained control: {button}"


def test_no_control_ships_disabled():
    """A disabled control with no stated reason is a dead end for a keyboard user."""
    dom = parsed()
    for tag, attrs in dom.tags:
        if tag in {"button", "input", "textarea", "select"}:
            assert "disabled" not in attrs, f"control disabled in markup: {tag} {attrs}"


def test_every_button_is_wired_to_a_handler():
    """A control that looks pressable and does nothing is worse than no control."""
    html = read_html()
    script = script_body()
    ids = re.findall(r"<button\b[^>]*\bid=\"([^\"]+)\"", html)
    assert ids
    for button_id in ids:
        assert f'$("{button_id}").addEventListener' in script, f"unwired button: {button_id}"


def test_a_skip_link_precedes_the_header():
    html = read_html()
    assert 'class="skip-link"' in html
    assert 'href="#main"' in html
    assert html.index("skip-link") < html.index('role="banner"')


def test_focus_is_visible_and_not_suppressed():
    html = read_html()
    assert ":focus-visible" in html
    assert re.search(r":focus-visible\s*\{[^}]*outline:\s*3px", html), "focus ring must be a visible outline"
    assert "outline: none" not in html and "outline:none" not in html


def test_a_keyboard_map_is_documented_on_the_page():
    html = read_html()
    assert "Keyboard map" in html
    assert html.count("<kbd>") >= 6
    assert "Alt" in html and "Escape" in html


def test_keyboard_shortcuts_are_wired_in_script():
    script = script_body()
    assert 'addEventListener("keydown"' in script
    assert "altKey" in script
    assert 'event.key === "Escape"' in script
    assert "stopAudio" in script, "Escape must stop audio that is already playing"


# --- announcements, alternatives and motion ---------------------------------

def test_results_are_announced_through_live_regions():
    html = read_html()
    assert html.count('aria-live="polite"') >= 3
    assert 'role="alert"' in html, "security findings must be announced assertively"


def test_every_audio_cue_carries_a_text_alternative():
    """The product is for people who may not hear or may not see. Both get words."""
    html = read_html()
    script = script_body()
    assert 'id="earconCaption"' in html
    assert re.search(r'id="earconCaption"[^>]*aria-live="polite"', html), (
        "the cue description must be announced when it changes"
    )
    assert "spoken_fallback" in script, "the description must come from the server, not the page"
    assert "Written description:" in script
    assert 'setAttribute("aria-label"' in script, "the waveform image needs a described label"


def test_the_hero_reports_a_loading_and_an_error_state():
    html = read_html()
    script = script_body()
    assert 'id="runProgress"' in html and "hidden" in html
    assert 'setBusy(button, true' in script and 'aria-busy' in script
    assert "catch (error)" in script, "a failed request must be reported, not swallowed"


def test_every_text_input_has_a_label_or_an_accessible_name():
    dom = parsed()
    html = read_html()
    for tag in ("input", "textarea"):
        for element in dom.of(tag):
            if element.get("type") in {"hidden"}:
                continue
            element_id = element.get("id")
            has_label = element_id and f'for="{element_id}"' in html
            assert has_label or element.get("aria-label"), f"unlabelled field: {element}"


def test_reduced_motion_is_honoured():
    html = read_html()
    assert "@media (prefers-reduced-motion: reduce)" in html
    assert re.search(
        r"@media \(prefers-reduced-motion: reduce\)\s*\{[^@]*animation-duration:\s*0\.001ms",
        html, flags=re.S,
    ), "reduced motion must actually stop the animations"
    assert re.search(
        r"@media \(prefers-reduced-motion: reduce\)\s*\{[^@]*scroll-behavior:\s*auto",
        html, flags=re.S,
    ), "reduced motion must also stop smooth scrolling"


def test_both_colour_schemes_are_designed():
    html = read_html()
    assert "@media (prefers-color-scheme: dark)" in html
    assert "color-scheme: light dark" in html
    dark_block = re.search(
        r"@media \(prefers-color-scheme: dark\)\s*\{(.*?)\n    \}\n", html, flags=re.S
    )
    assert dark_block and dark_block.group(1).count("--") >= 15, (
        "the dark scheme must redefine the palette, not tint one value"
    )


def test_the_layout_is_responsive_at_phone_and_desktop_widths():
    html = read_html()
    assert 'name="viewport"' in html
    assert "@media (max-width: 620px)" in html, "the 375px case needs its own rules"
    assert "@media (max-width: 1000px)" in html, "the split view needs to stack"


def test_empty_states_render_a_reason_instead_of_nothing():
    html = read_html()
    assert html.count('class="empty-state-card"') >= 4
    for pane in ("spokenPane", "earconCaption", "brailleOutput", "mcpPane", "govPane"):
        assert f'id="{pane}"' in html


def test_the_audit_row_never_reads_as_a_command_that_ran():
    """The server's terminal state string is EXECUTED and nothing executes.

    The page must not print that word on its own beside a command, because the
    product's whole claim is that it plans and refuses. It renders a plain
    label and keeps the server's raw value beside it, so the honest reading and
    the unedited server value are both on screen.
    """
    html = read_html()
    assert 'EXECUTED: "plan released, not run"' in html, "no plain-language label for the terminal state"
    assert '[server state " + record.state + "]' in html, "the server's own raw state is no longer shown"
    assert 'record.state + "   " + record.action' not in html, "the bare state is printed with no label"


# --- self-containment -------------------------------------------------------

def test_the_page_loads_nothing_from_the_network():
    """A locked-down or offline machine must still get the whole page."""
    html = read_html()
    external = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
    assert external == [], f"external asset references: {external}"
    assert "cdn." not in html and "googleapis" not in html


FONT_DIR = os.path.join(os.path.dirname(__file__), "../../docs/fonts")


def test_the_typefaces_are_the_committed_files_inlined_with_their_licences():
    """The typefaces ship inside the page, byte for byte the files in docs/fonts.

    Every url() in the page is a data: URI, each one decodes to a committed
    woff2 file, every face keeps font-display: swap, both font stacks still end
    in a local generic family, and each family's SIL Open Font License sits
    beside its files.
    """
    import base64

    html = read_html()
    urls = re.findall(r"url\(\s*['\"]?([^'\")]+)", html)
    assert urls and all(url.startswith("data:") for url in urls), (
        f"every url() must be inline: {[u[:60] for u in urls if not u.startswith('data:')]}"
    )
    faces = re.findall(r"@font-face\s*\{(.*?)\}", html, flags=re.S)
    assert len(faces) == 3, f"expected three latin faces, found {len(faces)}"
    committed = {
        name: open(os.path.join(FONT_DIR, name), "rb").read()
        for name in os.listdir(FONT_DIR) if name.endswith(".woff2")
    }
    inlined = []
    for face in faces:
        assert "font-display: swap" in face
        payload = re.search(r"data:font/woff2;base64,([A-Za-z0-9+/=]+)", face)
        assert payload, "each face must be a woff2 data: URI"
        inlined.append(base64.b64decode(payload.group(1)))
    assert sorted(inlined) == sorted(committed.values()), (
        "the inlined faces must be exactly the committed files; run python scripts/embed_fonts.py"
    )
    for licence in ("OFL-AtkinsonHyperlegible.txt", "OFL-JetBrainsMono.txt"):
        text = open(os.path.join(FONT_DIR, licence), encoding="utf-8").read()
        assert "SIL Open Font License" in text
    for stack in re.findall(r"--(?:sans|mono):\s*([^;]+);", html):
        assert re.search(r"(?:sans-serif|monospace)\s*$", stack.strip()), (
            f"a font stack must end in a local generic family: {stack}"
        )


# --- structural validity ----------------------------------------------------

VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "source", "track", "wbr",
}

CONTAINER_TAGS = (
    "html", "head", "body", "header", "nav", "main", "footer", "section",
    "article", "div", "button", "table", "thead", "tbody", "tr", "th", "td",
    "ol", "ul", "li", "p", "span", "label", "textarea", "canvas", "a", "code",
    "strong", "kbd", "caption", "dl", "dt", "dd", "svg", "path",
    "h1", "h2", "h3", "style", "script", "title",
)


def markup_without_scripts() -> str:
    """Strips script and style bodies so JS comparison operators are not read as tags."""
    html = read_html()
    html = re.sub(r"<script\b[^>]*>.*?</script>", "<script></script>", html, flags=re.S)
    return re.sub(r"<style\b[^>]*>.*?</style>", "<style></style>", html, flags=re.S)


def test_every_container_element_is_balanced():
    """html.parser tolerates broken markup, so count the tags directly.

    An unclosed landmark changes the accessibility tree a screen reader builds,
    which would make every role assertion above true of a document no browser
    actually produces.
    """
    markup = markup_without_scripts()
    mismatched = []
    for tag in CONTAINER_TAGS:
        opened = len(re.findall(rf"<{tag}\b", markup))
        closed = len(re.findall(rf"</{tag}>", markup))
        if opened != closed:
            mismatched.append(f"{tag}: {opened} opened, {closed} closed")
    assert mismatched == [], "unbalanced elements in docs/index.html: " + "; ".join(mismatched)


def test_no_element_is_left_open_and_nesting_never_crosses():
    markup = markup_without_scripts()
    stack: list[str] = []
    errors: list[str] = []
    for match in re.finditer(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?(/?)>", markup):
        closing, name, self_closing = match.group(1), match.group(2).lower(), match.group(3)
        if name in VOID_ELEMENTS or self_closing:
            continue
        if not closing:
            stack.append(name)
        elif not stack:
            errors.append(f"</{name}> closes nothing")
        elif stack[-1] != name:
            errors.append(f"</{name}> closes while <{stack[-1]}> is still open")
            if name in stack:
                while stack and stack.pop() != name:
                    pass
        else:
            stack.pop()
    assert errors == [], "crossed nesting in docs/index.html: " + "; ".join(errors)
    assert stack == [], f"elements left open at end of docs/index.html: {stack}"
