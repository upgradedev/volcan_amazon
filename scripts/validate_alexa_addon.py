"""Check alexa_plus/addon-package/addon.json against Amazon's documented schema.

Built and tested locally, not certified or deployed; needs the owner's Amazon
developer account. Amazon's page also says the MCP Toolkit is available to
select partners only, so an account alone may not be enough.

The constraints are the ones in the "addon.json schema reference" of Amazon's
Alexa+ MCP QuickStart Guide,
https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html
(page dated Jul 10, 2026, fetched 2026-09-27). The Alexa AI CLI that would
really validate and deploy the package (``alexa-ai deploy``) is behind the
developer console and a private npm registry, so it was not run. This script
is a local stand-in that checks only what the page documents.

Two kinds of result are printed and kept apart:

* schema: a documented constraint is broken (a missing field, a name over 30
  characters, a non-HTTPS URI, a missing icon size). Exit code 1.
* owner to fill: a value that is schema-valid but deliberately a placeholder on
  the reserved ``.invalid`` domain (privacy policy, terms, icons, carousel),
  because those must be the owner's own hosted pages and images. Reported, and
  exit code 0 unless ``--strict`` is given.

Run command:
    python scripts/validate_alexa_addon.py
    python scripts/validate_alexa_addon.py --strict
"""
import argparse
import json
import os
import sys
from urllib.parse import urlparse

DEFAULT_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "alexa_plus", "addon-package", "addon.json"))

ICON_SIZES = ("72x72", "64x64", "88x88", "126x126", "180x180", "241x241")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
PLACEHOLDER_SUFFIX = ".invalid"


def _https(uri: object) -> bool:
    if not isinstance(uri, str):
        return False
    parsed = urlparse(uri)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _placeholder(uri: str) -> bool:
    return (urlparse(uri).hostname or "").endswith(PLACEHOLDER_SUFFIX)


def validate(manifest: dict) -> tuple[list[str], list[str]]:
    """(schema problems, owner-to-fill placeholders) for one manifest."""
    problems: list[str] = []
    placeholders: list[str] = []

    def need(condition: bool, message: str) -> bool:
        if not condition:
            problems.append(message)
        return condition

    def uri_field(label: str, uri: object, image: bool = False) -> None:
        if not need(_https(uri), f"{label} must be an HTTPS URL, got {uri!r}"):
            return
        if image:
            need(urlparse(uri).path.lower().endswith(IMAGE_SUFFIXES),
                 f"{label} must be PNG, JPG, JPEG or WEBP, got {uri!r}")
        if _placeholder(uri):
            placeholders.append(f"{label}: {uri}")

    need(manifest.get("manifestVersion") == "1.0", "manifestVersion must be \"1.0\"")
    listing = manifest.get("storeListing") or {}
    countries = listing.get("distributionCountries")
    need(isinstance(countries, list) and bool(countries)
         and all(isinstance(c, str) and len(c) == 2 and c.isupper() for c in countries),
         "storeListing.distributionCountries must be a non-empty list of ISO country codes")

    locales = listing.get("locales") or {}
    if need(isinstance(locales, dict) and bool(locales), "storeListing.locales must name at least one locale"):
        for code, locale in locales.items():
            prefix = f"locales.{code}"
            name = (locale.get("name") or {}).get("value")
            need(isinstance(name, str) and 0 < len(name) <= 30, f"{prefix}.name.value is required, at most 30 characters")
            short = locale.get("shortDescription")
            need(isinstance(short, str) and 0 < len(short) <= 123,
                 f"{prefix}.shortDescription is required, at most 123 characters (has {len(short or '')})")
            full = locale.get("fullDescription")
            need(isinstance(full, str) and 0 < len(full) <= 4000,
                 f"{prefix}.fullDescription is required, at most 4000 characters")
            phrases = locale.get("examplePhrases")
            need(isinstance(phrases, list) and 3 <= len(phrases) <= 4
                 and all(isinstance(p, str) and 0 < len(p) <= 200 for p in phrases),
                 f"{prefix}.examplePhrases needs 3 to 4 phrases of at most 200 characters")

            privacy = locale.get("privacyAndCompliance") or {}
            uri_field(f"{prefix}.privacyPolicyUrl", privacy.get("privacyPolicyUrl"))
            uri_field(f"{prefix}.termsOfUseUrl", privacy.get("termsOfUseUrl"))

            media = locale.get("mediaAssets") or {}
            icons = media.get("icons") or {}
            light = icons.get("light") or []
            sizes = [icon.get("size") for icon in light]
            need(sorted(sizes) == sorted(ICON_SIZES),
                 f"{prefix}.mediaAssets.icons.light needs exactly the six sizes {', '.join(ICON_SIZES)}")
            for icon in light:
                uri_field(f"{prefix}.icon {icon.get('size')}", icon.get("uri"), image=True)
            dark = icons.get("dark") or []
            if dark:
                need(sorted(icon.get("size") for icon in dark) == sorted(ICON_SIZES),
                     f"{prefix}.mediaAssets.icons.dark, when given, needs the same six sizes")
                for icon in dark:
                    uri_field(f"{prefix}.dark icon {icon.get('size')}", icon.get("uri"), image=True)
            carousel = media.get("carouselImages") or []
            need(len(carousel) >= 1, f"{prefix}.mediaAssets.carouselImages needs at least one image")
            for index, image in enumerate(carousel):
                need(image.get("size") == "600x900", f"{prefix}.carousel {index} must be 600x900")
                alt = image.get("altText")
                need(isinstance(alt, str) and 0 < len(alt) <= 250, f"{prefix}.carousel {index} altText, at most 250 characters")
                uri_field(f"{prefix}.carousel {index}", image.get("uri"), image=True)
            for index, image in enumerate(media.get("bannerImages") or []):
                need(image.get("size") == "1200x600", f"{prefix}.banner {index} must be 1200x600")
                uri_field(f"{prefix}.banner {index}", image.get("uri"), image=True)

    integrations = manifest.get("integrations")
    if need(isinstance(integrations, list) and bool(integrations), "integrations must list the MCP endpoint"):
        for index, integration in enumerate(integrations):
            need(integration.get("type") == "MCP", f"integrations[{index}].type must be \"MCP\"")
            endpoint = (((integration.get("config") or {}).get("endpoints") or {}).get("default") or {})
            need(endpoint.get("type") == "HTTPS", f"integrations[{index}] endpoint type must be \"HTTPS\"")
            uri_field(f"integrations[{index}] endpoint", endpoint.get("uri"))
    return problems, placeholders


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("path", nargs="?", default=DEFAULT_PATH)
    parser.add_argument("--strict", action="store_true", help="also fail on owner-to-fill placeholders")
    args = parser.parse_args(argv)
    with open(args.path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    problems, placeholders = validate(manifest)
    print("Alexa+ MCP add-on package: built and tested locally, not certified or deployed; "
          "needs the owner's Amazon developer account.")
    print(f"Checked {os.path.relpath(args.path)} against the documented addon.json schema.")
    for problem in problems:
        print(f"  [schema] {problem}")
    print(f"  schema: {'pass' if not problems else f'{len(problems)} problem(s)'}")
    for item in placeholders:
        print(f"  [owner to fill] {item}")
    print(f"  owner to fill: {len(placeholders)} placeholder value(s)")
    if problems or (args.strict and placeholders):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
