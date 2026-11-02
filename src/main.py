"""
Apify Store Actor: US Healthcare Clinic Contact, Schema & Chain Detector
Scrapes & enriches independent US medical, dental, audiology, chiropractic, optometry,
and veterinary clinic websites with DNS/MX-verified emails, phone numbers, social profiles
(FB, IG, LI, YT, X), Schema.org MedicalOrganization metadata, and automatic Corporate
Chain / DSO / Franchise Detection (Verified Independent vs Chain Excluded vs Needs Review).
"""
import asyncio
import json
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

FREE_TIER_MAX_ITEMS = 25
FREE_TIER_CAP_MSG = (
    "Free-tier run capped at 25 results. Upgrade Apify plan for unlimited scale "
    "or contact Trung Thanh Tran on Upwork for custom pipelines."
)


def is_free_tier_at_home() -> bool:
    is_at_home = os.getenv("APIFY_IS_AT_HOME", "").strip().lower() in ("1", "true", "yes")
    user_is_paying = os.getenv("APIFY_USER_IS_PAYING", "").strip().lower() in ("1", "true", "yes")
    return is_at_home and not user_is_paying

import httpx
from bs4 import BeautifulSoup

try:
    import dns.asyncresolver  # type: ignore
    HAS_DNSPYTHON = True
except ImportError:
    HAS_DNSPYTHON = False

try:
    from apify import Actor
    HAS_APIFY = True
except ImportError:
    HAS_APIFY = False

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,12}")
US_PHONE_REGEX = re.compile(
    r"(?:\+?1[\s.-]?)?\(?([2-9]\d{2})\)?[\s.-](\d{3})[\s.-](\d{4})\b"
)

JUNK_EMAIL_DOMAINS = {
    "sentry.io", "sentry.wixpress.com", "sentry-next.wixpress.com",
    "example.com", "domain.com", "email.com", "yoursite.com", "wix.com",
    "wordpress.org", "w3.org", "schema.org", "googleapis.com", "cloudflare.com",
}
JUNK_EMAIL_EXTS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js", ".woff", ".woff2", ".ttf", ".ico"
)

SOCIAL_PATTERNS = {
    "facebook": re.compile(r"https?://(?:[\w]+\.)?facebook\.com/(?!sharer|share|dialog|tr\?)[^\s\"'<>?]+", re.I),
    "instagram": re.compile(r"https?://(?:[\w]+\.)?instagram\.com/(?!p/|reel/)[^\s\"'<>?]+", re.I),
    "linkedin": re.compile(r"https?://(?:[\w]+\.)?linkedin\.com/(?:company|in)/[^\s\"'<>?]+", re.I),
    "youtube": re.compile(r"https?://(?:[\w]+\.)?youtube\.com/(?:@|channel/|c/|user/)[^\s\"'<>?]+", re.I),
    "twitter_x": re.compile(r"https?://(?:[\w]+\.)?(?:twitter\.com|x\.com)/(?!intent|share)[^\s\"'<>?]+", re.I),
}

# Known US Corporate Healthcare Chains, Dental DSOs, Audiology Retailers, Vet Consolidators & Franchises
CORPORATE_CHAIN_SIGNATURES: Dict[str, List[str]] = {
    # Dental DSOs
    "Aspen Dental": ["aspendental.com", "aspen dental management"],
    "Heartland Dental": ["heartland.com", "heartland dental"],
    "Pacific Dental Services": ["pacificdentalservices.com", "pds health"],
    "Smile Brands": ["smilebrands.com", "bright now! dental", "monarch dental"],
    "Affordable Dentures & Implants": ["affordabledentures.com"],
    "Western Dental / Sonrava Health": ["westerndental.com", "sonrava health"],
    "Great Expressions Dental Centers": ["greatexpressions.com"],
    "Dental Care Alliance": ["dentalcarealliance.com"],
    "ClearChoice Dental Implant Centers": ["clearchoice.com"],
    "MB2 Dental": ["mb2dental.com"],
    # Audiology & Hearing Aid Chains
    "Miracle-Ear": ["miracle-ear.com", "miracle-ear franchise"],
    "Beltone": ["beltone.com", "beltone hearing"],
    "HearingLife (Demant)": ["hearinglife.com"],
    "Connect Hearing (Sonova)": ["connecthearing.com"],
    "HearUSA / Widex Retail": ["hearusa.com", "hear.com"],
    "Amplifon": ["amplifon.com"],
    "Audibel": ["audibel.com"],
    "Lucid Hearing": ["lucidhearing.com"],
    # Veterinary Corporate Consolidators (Mars, NVA, Thrive, Petco)
    "Banfield Pet Hospital (Mars Veterinary Health)": ["banfield.com", "banfield pet hospital", "mars veterinary"],
    "VCA Animal Hospitals": ["vcahospitals.com", "vca animal hospitals"],
    "BluePearl Pet Hospital": ["bluepearlvet.com", "bluepearl pet hospital"],
    "Vetco / Petco Love": ["petco.com/shop/en/petcostore/c/vetco", "vetcoclinics.com"],
    "Thrive Pet Healthcare": ["thrivepetcare.com", "thrive pet healthcare"],
    "National Veterinary Associates (NVA)": ["nva.com", "national veterinary associates"],
    "Mission Veterinary Partners": ["missionvetpartners.com"],
    # Chiropractic, Physical Therapy, Optical & Urgent Care Chains
    "The Joint Chiropractic": ["thejoint.com", "the joint corp"],
    "HealthSource Chiropractic": ["healthsourcechiro.com"],
    "ATI Physical Therapy": ["atipt.com", "ati physical therapy"],
    "Concentra Urgent Care": ["concentra.com"],
    "MinuteClinic (CVS Health)": ["cvs.com/minuteclinic", "minuteclinic"],
    "One Medical (Amazon)": ["onemedical.com"],
    "CityMD / Summit Health": ["citymd.com"],
    "AFC Urgent Care": ["afcurgentcare.com", "american family care"],
    "Carbon Health": ["carbonhealth.com"],
    "MyEyeDr.": ["myeyedr.com"],
    "Pearle Vision": ["pearlevision.com"],
    "LensCrafters": ["lenscrafters.com"],
    "America's Best Contacts & Eyeglasses": ["americasbest.com"],
}

FRANCHISE_FOOTER_PATTERNS = [
    re.compile(r"each\s+(?:office|clinic|location)\s+is\s+independently\s+owned\s+and\s+operated", re.I),
    re.compile(r"franchis(?:e|or|ee)\s+of\s+[a-z0-9\s,&.-]{3,40}", re.I),
    re.compile(r"a\s+proud\s+member\s+of\s+the\s+[a-z0-9\s,&.-]{3,35}\s+network", re.I),
    re.compile(r"backed\s+by\s+[a-z0-9\s,&.-]{3,35}\s+(?:partners|capital|health|dental\s+partners)", re.I),
    re.compile(r"all\s+practices\s+are\s+owned\s+and\s+operated\s+by\s+licensed", re.I),
]

SPECIALTY_KEYWORDS: List[Tuple[str, List[str]]] = [
    ("Audiology & Hearing Care", ["audiolog", "hearing aid", "tinnitus", "ear & hearing", "cochlear"]),
    ("Dental & Orthodontics", ["dental", "dentist", "orthodont", "endodont", "periodont", "oral surgery", "dds", "dmd"]),
    ("Veterinary & Animal Care", ["veterinar", "animal hospital", "pet hospital", "vet clinic", "dvm", "spay", "neuter"]),
    ("Chiropractic & Spine Rehab", ["chiropract", "spinal decompression", "subluxation", "physical therapy", "rehab"]),
    ("Optometry & Ophthalmology", ["optometr", "ophthalmolog", "eye care", "vision center", "lasik"]),
    ("Dermatology & Medical Aesthetics", ["dermatolog", "medspa", "mohs", "skin clinic"]),
]

MEDICAL_SCHEMA_KEYWORDS = (
    "Medical", "Physician", "Dentist", "Veterinary", "Hospital", "Pharmacy",
    "Optician", "Diagnostic", "HealthAndBeautyBusiness", "LocalBusiness", "Organization"
)

DEFAULT_CLINIC_URLS = [
    {"url": "https://pacificaudiology.com/"},
    {"url": "https://brooklyndentalstudio.com/"},
    {"url": "https://www.banfield.com/"},
]


class AsyncDomainMXChecker:
    """Validates email syntax + domain DNS MX (with A/AAAA fallback) and caches per domain."""

    def __init__(self) -> None:
        self._cache: Dict[str, bool] = {}

    async def is_domain_deliverable(self, domain: str) -> bool:
        d = domain.strip().lower().rstrip(".")
        if not d or "." not in d or d in JUNK_EMAIL_DOMAINS:
            return False
        if d in self._cache:
            return self._cache[d]

        deliverable = False
        if HAS_DNSPYTHON:
            resolver = dns.asyncresolver.Resolver()
            resolver.lifetime = 3.5
            try:
                mx_records = await resolver.resolve(d, "MX")
                deliverable = len(mx_records) > 0
            except Exception:
                try:
                    a_records = await resolver.resolve(d, "A")
                    deliverable = len(a_records) > 0
                except Exception:
                    deliverable = False
        else:
            loop = asyncio.get_running_loop()
            try:
                infos = await asyncio.wait_for(loop.getaddrinfo(d, None), timeout=3.5)
                deliverable = len(infos) > 0
            except Exception:
                deliverable = False

        self._cache[d] = deliverable
        return deliverable


def extract_clean_emails(raw_candidates: List[str]) -> List[str]:
    cleaned: Set[str] = set()
    for raw in raw_candidates:
        email = raw.strip().lower().rstrip(".,;:")
        if any(email.endswith(ext) for ext in JUNK_EMAIL_EXTS):
            continue
        parts = email.split("@")
        if len(parts) != 2 or not parts[0] or "." not in parts[1]:
            continue
        local, domain = parts
        if len(local) > 64 or domain in JUNK_EMAIL_DOMAINS or "sentry" in domain or "wixpress" in domain:
            continue
        cleaned.add(email)
    return sorted(cleaned)


def extract_normalized_us_phones(text: str, soup: BeautifulSoup) -> List[str]:
    phones: Set[str] = set()
    for a in soup.select("a[href^='tel:']"):
        digits = re.sub(r"\D", "", a.get("href", ""))
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        if len(digits) == 10 and digits[0] not in ("0", "1"):
            phones.add(f"+1-{digits[:3]}-{digits[3:6]}-{digits[6:]}")

    for area, exch, line in US_PHONE_REGEX.findall(text):
        if exch != "555":
            phones.add(f"+1-{area}-{exch}-{line}")

    return sorted(phones)[:8]


def parse_medical_json_ld(soup: BeautifulSoup) -> Dict[str, Any]:
    types: Set[str] = set()
    meta: Dict[str, Any] = {
        "name": None,
        "street_address": None,
        "city": None,
        "state": None,
        "postal_code": None,
        "telephone": None,
        "medical_specialty": None,
        "aggregate_rating": None,
        "review_count": None,
        "parent_organization": None,
    }

    def _walk_node(node: Any) -> None:
        if isinstance(node, list):
            for child in node:
                _walk_node(child)
            return
        if not isinstance(node, dict):
            return
        if "@graph" in node:
            _walk_node(node["@graph"])

        raw_type = node.get("@type")
        node_types = [raw_type] if isinstance(raw_type, str) else (raw_type if isinstance(raw_type, list) else [])
        for t in node_types:
            t_str = str(t)
            types.add(t_str)
            if any(k.lower() in t_str.lower() for k in MEDICAL_SCHEMA_KEYWORDS):
                if not meta["name"] and isinstance(node.get("name"), str):
                    meta["name"] = node["name"].strip()
                if not meta["telephone"] and isinstance(node.get("telephone"), str):
                    meta["telephone"] = node["telephone"].strip()
                if not meta["medical_specialty"] and node.get("medicalSpecialty"):
                    spec = node["medicalSpecialty"]
                    meta["medical_specialty"] = spec if isinstance(spec, str) else json.dumps(spec)

                parent = node.get("parentOrganization") or node.get("brand")
                if isinstance(parent, dict) and parent.get("name"):
                    meta["parent_organization"] = str(parent["name"]).strip()

                addr = node.get("address")
                if isinstance(addr, dict):
                    meta["street_address"] = meta["street_address"] or addr.get("streetAddress")
                    meta["city"] = meta["city"] or addr.get("addressLocality")
                    meta["state"] = meta["state"] or addr.get("addressRegion")
                    meta["postal_code"] = meta["postal_code"] or addr.get("postalCode")

                rating = node.get("aggregateRating")
                if isinstance(rating, dict):
                    meta["aggregate_rating"] = meta["aggregate_rating"] or rating.get("ratingValue")
                    meta["review_count"] = meta["review_count"] or rating.get("reviewCount")

    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw_json = (tag.string or tag.get_text() or "").strip()
        if not raw_json:
            continue
        try:
            _walk_node(json.loads(raw_json))
        except Exception:
            continue

    return {"schema_types": sorted(types), "metadata": meta}


def classify_specialty(clinic_name: str, text_lower: str, schema_types: List[str]) -> str:
    header_context = f"{clinic_name} {' '.join(schema_types)}".lower()
    body_sample = text_lower[:12000]
    best_label = "Primary & Specialty Medical Clinic"
    best_score = 0
    for label, keywords in SPECIALTY_KEYWORDS:
        score = sum(5 for kw in keywords if kw in header_context) + sum(1 for kw in keywords if kw in body_sample)
        if score > best_score:
            best_score = score
            best_label = label
    return best_label


def evaluate_corporate_chain_ownership(
    url: str,
    html_lower: str,
    text_lower: str,
    soup: BeautifulSoup,
    parent_org: Optional[str],
    custom_keywords: List[str],
) -> Tuple[str, float, List[str]]:
    """
    Classifies clinic ownership into:
      - 'Chain Excluded' (Confirmed corporate DSO / MSO / retail healthcare chain or franchise)
      - 'Needs Review' (Regional multi-office group with >= 6 location subpages or ambiguous signals)
      - 'Verified Independent' (Single-practice or local independent clinic with zero DSO/chain footprints)
    """
    signals: List[str] = []
    score = 0.0
    host = urlparse(url).netloc.lower()

    # 1. Check built-in corporate healthcare / DSO / retail brand signatures
    for brand_name, indicators in CORPORATE_CHAIN_SIGNATURES.items():
        for ind in indicators:
            ind_l = ind.lower()
            if ind_l in host or ind_l in html_lower:
                signals.append(f"Matched corporate healthcare/DSO brand: {brand_name} ('{ind}')")
                score = max(score, 0.96)
                break

    # 2. Check custom user-supplied excluded DSO/MSO keywords
    for kw in custom_keywords:
        kw_l = kw.strip().lower()
        if len(kw_l) >= 3 and (kw_l in host or kw_l in text_lower):
            signals.append(f"Matched custom excluded keyword: '{kw.strip()}'")
            score = max(score, 0.92)

    # 3. Check Schema.org parentOrganization
    if parent_org:
        signals.append(f"Schema.org parentOrganization declared: '{parent_org}'")
        score = max(score, 0.75)

    # 4. Check franchise / MSO legal footer disclosures
    for pat in FRANCHISE_FOOTER_PATTERNS:
        m = pat.search(text_lower)
        if m:
            snippet = " ".join(m.group(0).split())[:90]
            signals.append(f"Corporate/franchise legal disclosure: \"{snippet}\"")
            score = max(score, 0.90)

    # 5. Count distinct internal /locations/ or /clinics/ store-locator paths
    loc_paths: Set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip().lower()
        if any(seg in href for seg in ("/locations/", "/our-locations/", "/clinics/", "/offices/", "/find-a-location")):
            parsed_h = urlparse(urljoin(url, href))
            if parsed_h.netloc.lower() == host:
                clean_p = parsed_h.path.rstrip("/")
                if clean_p.count("/") >= 2:
                    loc_paths.add(clean_p)

    if len(loc_paths) >= 15:
        signals.append(f"Enterprise multi-location store locator detected ({len(loc_paths)} location URLs)")
        score = max(score, 0.88)
    elif len(loc_paths) >= 5:
        signals.append(f"Regional multi-office footprint ({len(loc_paths)} location subpages)")
        score = max(score, 0.55)

    if score >= 0.80:
        return ("Chain Excluded", round(score, 2), signals)
    if score >= 0.45:
        return ("Needs Review", round(score, 2), signals)
    return ("Verified Independent", 0.05, [])


def discover_clinic_subpages(soup: BeautifulSoup, base_url: str) -> List[str]:
    base_host = urlparse(base_url).netloc.lower()
    found: List[str] = []
    target_terms = ("contact", "about", "location", "our-practice", "meet-the", "team", "doctors")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        label = (a.get_text(" ", strip=True) or "").lower()
        if any(t in href.lower() or t in label for t in target_terms):
            full = urljoin(base_url, href).split("#")[0]
            parsed = urlparse(full)
            if parsed.netloc.lower() == base_host and parsed.scheme in ("http", "https"):
                if full != base_url and full not in found:
                    found.append(full)
        if len(found) >= 2:
            break
    return found


async def enrich_clinic_url(
    client: httpx.AsyncClient,
    mx_checker: AsyncDomainMXChecker,
    url: str,
    follow_contact_pages: bool,
    custom_keywords: List[str],
) -> Dict[str, Any]:
    emails: Set[str] = set()
    phones: Set[str] = set()
    socials: Dict[str, List[str]] = {}
    pages_crawled = 0
    status_code = 0

    try:
        resp = await client.get(url)
        status_code = resp.status_code
        pages_crawled += 1
        final_url = str(resp.url)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        visible_text = soup.get_text(" ", strip=True)

        ld_info = parse_medical_json_ld(soup)
        schema_types = ld_info["schema_types"]
        schema_meta = ld_info["metadata"]

        clinic_name = schema_meta.get("name") or ""
        if not clinic_name:
            og_site = soup.find("meta", attrs={"property": "og:site_name"})
            if og_site and og_site.get("content"):
                clinic_name = og_site["content"].strip()
        if not clinic_name and soup.title and soup.title.string:
            clinic_name = soup.title.string.strip().split("|")[0].split("–")[0].strip()

        emails.update(extract_clean_emails(EMAIL_REGEX.findall(html)))
        for a in soup.select("a[href^='mailto:']"):
            addr = a["href"].replace("mailto:", "").split("?")[0]
            emails.update(extract_clean_emails([addr]))

        phones.update(extract_normalized_us_phones(visible_text, soup))
        if schema_meta.get("telephone"):
            phones.update(extract_normalized_us_phones(str(schema_meta["telephone"]), BeautifulSoup("", "html.parser")))

        for platform, rx in SOCIAL_PATTERNS.items():
            matches = sorted(set(rx.findall(html)))
            if matches:
                socials[platform] = matches[:3]

        combined_html_lower = html.lower()
        combined_text_lower = visible_text.lower()

        if follow_contact_pages and status_code == 200:
            subpages = discover_clinic_subpages(soup, final_url)
            for sub_url in subpages:
                try:
                    sub_resp = await client.get(sub_url)
                    if sub_resp.status_code == 200:
                        pages_crawled += 1
                        sub_html = sub_resp.text
                        sub_soup = BeautifulSoup(sub_html, "html.parser")
                        sub_text = sub_soup.get_text(" ", strip=True)
                        emails.update(extract_clean_emails(EMAIL_REGEX.findall(sub_html)))
                        for a in sub_soup.select("a[href^='mailto:']"):
                            addr = a["href"].replace("mailto:", "").split("?")[0]
                            emails.update(extract_clean_emails([addr]))
                        phones.update(extract_normalized_us_phones(sub_text, sub_soup))
                        for platform, rx in SOCIAL_PATTERNS.items():
                            matches = sorted(set(rx.findall(sub_html)))
                            if matches:
                                merged = set(socials.get(platform, []))
                                merged.update(matches)
                                socials[platform] = sorted(merged)[:3]
                        combined_html_lower += "\n" + sub_html.lower()
                        combined_text_lower += "\n" + sub_text.lower()
                except Exception:
                    continue

        mx_valid_emails: List[str] = []
        for em in sorted(emails):
            domain_part = em.split("@")[1]
            if await mx_checker.is_domain_deliverable(domain_part):
                mx_valid_emails.append(em)

        specialty = classify_specialty(clinic_name, combined_text_lower, schema_types)
        ownership_status, chain_score, chain_signals = evaluate_corporate_chain_ownership(
            url=final_url,
            html_lower=combined_html_lower,
            text_lower=combined_text_lower,
            soup=soup,
            parent_org=schema_meta.get("parent_organization"),
            custom_keywords=custom_keywords,
        )
        # A 4xx/5xx page (blocked, missing, server error) says nothing about ownership
        http_error = f"HTTP {status_code}" if status_code >= 400 else None
        if http_error:
            ownership_status = "Needs Review"

        return {
            "url": final_url,
            "input_url": url,
            "clinic_name": clinic_name or urlparse(final_url).netloc,
            "specialty_category": specialty,
            "ownership_status": ownership_status,
            "chain_confidence_score": chain_score,
            "chain_signals": chain_signals,
            "emails": sorted(emails),
            "mx_dns_valid_emails": mx_valid_emails,
            "phones": sorted(phones)[:6],
            "social_profiles": socials,
            "medical_schema_types": schema_types,
            "medical_organization_metadata": schema_meta,
            "pages_crawled": pages_crawled,
            "status_code": status_code,
            "error": http_error,
        }
    except Exception as exc:
        return {
            "url": url,
            "input_url": url,
            "clinic_name": urlparse(url).netloc,
            "specialty_category": "Unknown",
            "ownership_status": "Needs Review",
            "chain_confidence_score": 0.0,
            "chain_signals": [],
            "emails": [],
            "mx_dns_valid_emails": [],
            "phones": [],
            "social_profiles": {},
            "medical_schema_types": [],
            "medical_organization_metadata": {},
            "pages_crawled": pages_crawled,
            "status_code": status_code,
            "error": str(exc),
        }


async def safe_charge_event(event_name: str, count: int = 1) -> None:
    if not HAS_APIFY or count <= 0:
        return
    charge_fn = getattr(Actor, "charge", None)
    if callable(charge_fn):
        try:
            await charge_fn(event_name=event_name, count=count)
        except Exception:
            pass


async def run_clinic_enrichment(
    urls: List[str],
    follow_contact_pages: bool = True,
    exclude_chains: bool = False,
    custom_chain_keywords: str = "",
    max_concurrency: int = 5,
) -> List[Dict[str, Any]]:
    sem = asyncio.Semaphore(max(1, max_concurrency))
    mx_checker = AsyncDomainMXChecker()
    custom_kw_list = [k.strip() for k in (custom_chain_keywords or "").split(",") if k.strip()]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async with httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=True) as client:
        async def _worker(target_url: str) -> Dict[str, Any]:
            async with sem:
                return await enrich_clinic_url(
                    client=client,
                    mx_checker=mx_checker,
                    url=target_url,
                    follow_contact_pages=follow_contact_pages,
                    custom_keywords=custom_kw_list,
                )

        enriched = await asyncio.gather(*[_worker(u) for u in urls])

    if exclude_chains:
        return [r for r in enriched if r.get("ownership_status") != "Chain Excluded"]
    return list(enriched)


async def main() -> None:
    if HAS_APIFY:
        async with Actor:
            actor_input = await Actor.get_input() or {}
            raw_urls = actor_input.get("startUrls") or DEFAULT_CLINIC_URLS
            follow_contact = bool(actor_input.get("followContactPages", True))
            exclude_chains = bool(actor_input.get("excludeChainsFromOutput", False))
            custom_keywords = str(actor_input.get("customChainKeywords", ""))
            concurrency = int(actor_input.get("maxConcurrency", 5))
            max_items = int(actor_input.get("maxItems", 25))

            urls = [
                item["url"] if isinstance(item, dict) else str(item)
                for item in raw_urls
                if item and (isinstance(item, str) or item.get("url"))
            ]
            if not urls:
                urls = [u["url"] for u in DEFAULT_CLINIC_URLS]

            was_capped = False
            if is_free_tier_at_home() and (len(urls) > FREE_TIER_MAX_ITEMS or max_items > FREE_TIER_MAX_ITEMS):
                max_items = min(max_items, FREE_TIER_MAX_ITEMS)
                if len(urls) > FREE_TIER_MAX_ITEMS:
                    urls = urls[:FREE_TIER_MAX_ITEMS]
                was_capped = True
                Actor.log.warning(FREE_TIER_CAP_MSG)
                await Actor.set_status_message(FREE_TIER_CAP_MSG)
            else:
                urls = urls[:max_items]

            Actor.log.info(
                f"Enriching {len(urls)} US healthcare clinics (followContactPages={follow_contact}, "
                f"excludeChains={exclude_chains})..."
            )
            results = await run_clinic_enrichment(
                urls=urls,
                follow_contact_pages=follow_contact,
                exclude_chains=exclude_chains,
                custom_chain_keywords=custom_keywords,
                max_concurrency=concurrency,
            )
            results = results[:max_items]
            await Actor.push_data(results)
            await safe_charge_event("clinic-enriched", count=len(results))
            if was_capped:
                await Actor.set_status_message(FREE_TIER_CAP_MSG)
            else:
                await Actor.set_status_message(
                    f"Successfully enriched {len(results)} US healthcare clinic records."
                )
            Actor.log.info(f"Successfully enriched and pushed {len(results)} healthcare clinic records.")
    else:
        sample_urls = [u["url"] for u in DEFAULT_CLINIC_URLS]
        results = await run_clinic_enrichment(sample_urls, follow_contact_pages=True)
        print(json.dumps(results, indent=2))
