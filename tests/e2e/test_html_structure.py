"""Structural, accessibility and honesty assertions over the companion document.

These are static DOM assertions parsed with the standard library, not a browser
journey: no browser driver runs here, and gate C5 records that honestly.

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
    ):
        assert f'id="{hook}"' in html, f"missing control hook: {hook}"


def test_diff_presets_are_well_formed_patches():
    html = read_html()
    assert "KMS_KEY_ID" in html and "AuthService" in html
    assert "router.get" in html and "health" in html
    assert "strip" in html
    assert html.count("diff --git") >= 3


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

    The header is read before any button is pressed. If it never mentions
    Amazon Bedrock, a reviewer whose install lacked the SDK concludes the AI is
    absent rather than uninstalled. The sentence also has to point at the meter,
    so the page keeps promising a report rather than a result.
    """
    html = read_html()
    header = html.split("<main", 1)[0]
    assert "Bedrock" in header, (
        "the first screen must state that a Bedrock model can synthesize the digest"
    )
    assert "anthropic[bedrock]" in header, (
        "the first screen must name the package that enables the model path"
    )
    assert "Synthesis engine" in header, (
        "the first screen must point at the meter that reports which engine answered"
    )
    assert "will be answered by Amazon Bedrock" not in header, (
        "the header may say a model can answer, never that one did"
    )


def test_the_earcon_empty_state_names_both_cues():
    """The pre-verbal triage layer is only real if the page can be checked.

    Naming both cue types lets a reviewer press two presets and confirm the
    audio differs, which is the claim four documents make.
    """
    html = read_html()
    caption = html.split('id="earconCaption"', 1)[1].split("</p>", 1)[0]
    assert "DIFF_READY" in caption and "SECURITY_FINDING" in caption
    assert "rising" in caption and "falling" in caption


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
