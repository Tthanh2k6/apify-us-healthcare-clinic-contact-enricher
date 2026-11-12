"""Offline tests for pure functions only (no network, no DNS, no Apify platform)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bs4 import BeautifulSoup  # noqa: E402

from src.main import (  # noqa: E402
    EMAIL_REGEX,
    SOCIAL_PATTERNS,
    classify_specialty,
    coerce_int,
    discover_clinic_subpages,
    evaluate_corporate_chain_ownership,
    extract_clean_emails,
    extract_normalized_us_phones,
    extract_start_urls,
    normalize_input_url,
    parse_medical_json_ld,
)


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_emails_filtered_and_deduped():
    raw = ["Info@Clinic.com", "info@clinic.com.", "logo@2x.png", "a@sentry.io",
           "x@sentry.wixpress.com", "bad@@x.com", "user@example.com", "no-dot@localhost"]
    assert extract_clean_emails(raw) == ["info@clinic.com"]


def test_email_regex_finds_in_html():
    found = EMAIL_REGEX.findall('<a href="mailto:front.desk@smile-dental.org">x</a>')
    assert "front.desk@smile-dental.org" in found


def test_phone_normalisation_and_dedup():
    html = '<a href="tel:+15032928700">Call</a> Office: (503) 292-8700 or 503.292.8701'
    s = soup(html)
    phones = extract_normalized_us_phones(s.get_text(" "), s)
    assert phones == ["+1-503-292-8700", "+1-503-292-8701"]


def test_phone_rejects_555_and_bad_area_code():
    s = soup("")
    assert extract_normalized_us_phones("call 212-555-0100 or 123-456-7890", s) == []


def test_json_ld_parsing_graph_and_bad_json():
    html = """
    <script type="application/ld+json">{"@graph":[{"@type":["Dentist","LocalBusiness"],
      "name":"Bright Smile","telephone":"503-292-8700",
      "address":{"streetAddress":"1 Main St","addressLocality":"Portland","addressRegion":"OR","postalCode":"97201"},
      "parentOrganization":{"name":"MegaDental"}}]}</script>
    <script type="application/ld+json">{not json</script>
    """
    out = parse_medical_json_ld(soup(html))
    assert "Dentist" in out["schema_types"]
    assert out["metadata"]["name"] == "Bright Smile"
    assert out["metadata"]["city"] == "Portland"
    assert out["metadata"]["parent_organization"] == "MegaDental"


def test_specialty_classification():
    assert classify_specialty("Pacific Audiology", "hearing aid fitting", []) == "Audiology & Hearing Care"
    assert classify_specialty("Happy Paws", "veterinarian spay neuter", []) == "Veterinary & Animal Care"
    assert classify_specialty("Clinic", "nothing relevant", []) == "Primary & Specialty Medical Clinic"


def test_chain_known_brand_is_excluded():
    status, score, signals = evaluate_corporate_chain_ownership(
        "https://www.banfield.com/", "<html></html>", "text", soup("<html></html>"), None, [])
    assert status == "Chain Excluded" and score >= 0.9 and signals


def test_chain_independent_and_custom_keyword_and_parent_org():
    s = soup("<html></html>")
    assert evaluate_corporate_chain_ownership(
        "https://tiny-clinic.com/", "", "welcome", s, None, [])[0] == "Likely Independent"
    assert evaluate_corporate_chain_ownership(
        "https://tiny-clinic.com/", "", "part of acme group", s, None, ["Acme Group"])[0] == "Chain Excluded"
    assert evaluate_corporate_chain_ownership(
        "https://tiny-clinic.com/", "", "welcome", s, "Some Parent", [])[0] == "Needs Review"


def test_chain_location_count_thresholds():
    links = "".join(f'<a href="/locations/city-{i}">x</a>' for i in range(5))
    status, _, _ = evaluate_corporate_chain_ownership(
        "https://x-clinic.com/", "", "", soup(links), None, [])
    assert status == "Needs Review"
    links = "".join(f'<a href="/locations/city-{i}">x</a>' for i in range(15))
    status, _, _ = evaluate_corporate_chain_ownership(
        "https://x-clinic.com/", "", "", soup(links), None, [])
    assert status == "Chain Excluded"


def test_discover_subpages_same_host_only_max_two():
    html = ('<a href="/contact">Contact</a><a href="https://other.com/contact">c</a>'
            '<a href="/about#x">About</a><a href="/team">Team</a>')
    assert discover_clinic_subpages(soup(html), "https://clinic.com/") == [
        "https://clinic.com/contact", "https://clinic.com/about"]


def test_social_patterns():
    html = ('https://www.facebook.com/myclinic" https://www.facebook.com/sharer/x '
            'https://instagram.com/myclinic" https://x.com/myclinic"')
    assert SOCIAL_PATTERNS["facebook"].findall(html) == ["https://www.facebook.com/myclinic"]
    assert SOCIAL_PATTERNS["instagram"].findall(html) == ["https://instagram.com/myclinic"]
    assert SOCIAL_PATTERNS["twitter_x"].findall(html) == ["https://x.com/myclinic"]


def test_normalize_input_url():
    assert normalize_input_url("clinic.com/contact") == "https://clinic.com/contact"
    assert normalize_input_url("  http://clinic.com ") == "http://clinic.com"
    for bad in (None, "", "   ", 5, "ftp://clinic.com", "not a url", "localhost", "https://"):
        assert normalize_input_url(bad) is None


def test_extract_start_urls_tolerates_junk():
    raw = [{"url": "a-clinic.com"}, "https://b-clinic.com", {"requestsFromUrl": "https://x"},
           None, 7, {"url": ""}]
    assert extract_start_urls(raw) == ["https://a-clinic.com", "https://b-clinic.com"]
    assert extract_start_urls(None) == []


def test_coerce_int():
    assert coerce_int(None, 5) == 5
    assert coerce_int("abc", 5) == 5
    assert coerce_int("7", 5) == 7
    assert coerce_int(0, 5) == 1


def test_contains_term_respects_word_edges():
    from src.main import contains_term
    assert contains_term("www.nva.com", "nva.com")
    assert not contains_term("www.canva.com", "nva.com")
    assert not contains_term("visit shear.com today", "hear.com")
    assert contains_term("part of aspen dental group", "aspen dental")
