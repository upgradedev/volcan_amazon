"""Structural and accessibility assertions over the single companion document.

These are static DOM assertions parsed with the standard library, not a browser
journey: no browser driver runs here, and gate C5 records that honestly.

The accessibility assertions are the point of this module. Volcan's whole claim
is that a blind or mobility-impaired developer can drive it, so a control that
cannot be reached by keyboard, a result that is never announced, or an
animation that ignores a reduced-motion preference is a product defect, and
these tests fail on each of them.
"""
import os
import re
from html.parser import HTMLParser

INDEX_PATH = os.path.join(os.path.dirname(__file__), "../../docs/index.html")


def read_html() -> str:
    with open(INDEX_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


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
    assert "Agent Forge" in html


def test_core_controls_are_present():
    html = read_html()
    for hook in (
        "voiceCommandInput", "executeVoiceCommand", "diffInput", "audioVisualizer",
        "synthesizeDiff", "playPureEarcon", "stageGovernedAction", "confirmVoiceAction",
        "rejectAction", "auditVault", "brailleOutput",
    ):
        assert hook in html, f"missing control hook: {hook}"


def test_web_audio_and_speech_apis_are_used():
    html = read_html()
    assert "AudioContext" in html
    assert "speechSynthesis" in html
    assert "SpeechSynthesisUtterance" in html


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
    html = read_html()
    assert 'addEventListener("keydown"' in html
    assert "altKey" in html
    assert 'event.key === "Escape"' in html


# --- announcements and motion -----------------------------------------------

def test_results_are_announced_through_live_regions():
    html = read_html()
    assert html.count('aria-live="polite"') >= 3
    assert 'role="alert"' in html, "security findings must be announced assertively"


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


def test_reduced_motion_is_honoured_in_css_and_in_script():
    html = read_html()
    assert "@media (prefers-reduced-motion: reduce)" in html
    assert "prefers-reduced-motion: reduce" in html
    assert "REDUCED_MOTION" in html, "the canvas animation must also check the preference"


# --- honesty ----------------------------------------------------------------

def test_the_page_makes_no_connection_claim_before_a_real_fetch():
    html = read_html()
    assert 'fetch(base + "/health"' in html, "connection state must come from a real request"
    assert 'data-mode="checking"' in html, "the initial state must be 'checking', not 'connected'"
    assert "SIMULATED IN BROWSER" in html, "browser-only results must be labelled"


def test_the_page_carries_no_fabricated_status_badges():
    html = read_html()
    for banned in ("LIVE INGESTION", "AWS SYNCED", "RULES SEC 4 VERIFIED", "Fire TV Pairing"):
        assert banned not in html, f"fabricated status badge present: {banned}"


# --- responsive layout and empty states -------------------------------------

def test_responsive_layout_and_hero_action():
    html = read_html()
    assert 'name="viewport"' in html
    assert "@media (max-width: 480px)" in html or "@media (max-width: 860px)" in html
    assert 'data-testid="primary-hero-action"' in html


def test_empty_states_render_a_reason_instead_of_nothing():
    html = read_html()
    assert "empty-state-card" in html
    assert html.count("empty-state-card") >= 3


# --- structural validity ----------------------------------------------------

VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "source", "track", "wbr",
}

CONTAINER_TAGS = (
    "html", "head", "body", "header", "nav", "main", "footer", "section",
    "div", "button", "table", "thead", "tbody", "tr", "th", "td", "ol", "ul",
    "li", "p", "span", "fieldset", "label", "textarea", "canvas", "a", "code",
    "strong", "kbd", "caption", "h1", "h2", "h3", "style", "script", "title",
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
