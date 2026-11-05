# US Healthcare Clinic Contact and Chain Detector (Apify Actor)

**Try it on Apify Store:** https://apify.com/thanh81646/apify-us-healthcare-clinic-contact-enricher

An Apify actor written in async Python (`httpx` + `BeautifulSoup4` + `dnspython`). You give it a list of US clinic websites (dental, audiology, veterinary, chiropractic, optometry and similar). For each site it fetches the homepage and up to two internal "contact/about/locations/team" pages, then returns:

- email addresses found in the HTML and `mailto:` links, with obvious junk filtered out (asset filenames, `sentry.io`, `wixpress.com`, placeholder domains);
- `mx_dns_valid_emails`: the subset whose domain has an MX record (or an A record if there is no MX). This is a DNS check on the domain only. It does not check that a mailbox exists;
- US phone numbers from `tel:` links and visible text, normalized to `+1-XXX-XXX-XXXX`;
- social links for Facebook, Instagram, LinkedIn, YouTube and X/Twitter (up to 3 each);
- Schema.org JSON-LD data for medical/local-business types (name, address, specialty, rating, `parentOrganization`);
- a rough specialty category based on keywords;
- an ownership guess: `Chain Excluded`, `Needs Review` or `Likely Independent`.

## How the ownership guess works

It is a keyword heuristic, not a lookup in any registry:

1. The domain and HTML are matched against a built-in list of 38 US chains: dental DSOs, hearing-aid retailers, veterinary groups, and chiropractic, PT, urgent-care and optical chains (for example Aspen Dental, Heartland Dental, Miracle-Ear, Beltone, Banfield, VCA, The Joint Chiropractic, ATI PT, One Medical, MyEyeDr). You can add your own keywords with `customChainKeywords`.
2. A Schema.org `parentOrganization` raises the score.
3. Franchise wording in the page text (for example "each office is independently owned and operated") raises the score.
4. Internal store-locator links are counted: 5 or more location paths raise the score, 15 or more push it to "chain".

A score of 0.80 or higher gives `Chain Excluded`, 0.45 to 0.80 gives `Needs Review`, and anything lower gives `Likely Independent`. "Likely Independent" only means that none of these signals matched. If a site cannot be fetched or answers with an HTTP error (4xx/5xx), the record comes back as `Needs Review` with the error message (or `HTTP <code>`) in `error`.

## Input

```json
{
  "startUrls": [
    { "url": "https://pacificaudiology.com/" },
    { "url": "https://brooklyndentalstudio.com/" },
    { "url": "https://www.banfield.com/" }
  ],
  "followContactPages": true,
  "excludeChainsFromOutput": false,
  "customChainKeywords": "",
  "maxConcurrency": 5,
  "maxItems": 25
}
```

Runs on the Apify free tier are capped at 25 URLs.

## Output record (example shape)

```json
{
  "url": "https://pacificaudiology.com/",
  "input_url": "https://pacificaudiology.com/",
  "clinic_name": "Pacific Audiology Clinic",
  "specialty_category": "Audiology & Hearing Care",
  "ownership_status": "Likely Independent",
  "chain_confidence_score": 0.05,
  "chain_signals": [],
  "emails": ["info@pacificaudiology.com"],
  "mx_dns_valid_emails": ["info@pacificaudiology.com"],
  "phones": ["+1-503-292-8700"],
  "social_profiles": { "facebook": ["https://www.facebook.com/..."] },
  "medical_schema_types": ["LocalBusiness", "MedicalOrganization"],
  "medical_organization_metadata": {},
  "pages_crawled": 3,
  "status_code": 200,
  "error": null
}
```

## Calling it from Python

```python
from apify_client import ApifyClient

client = ApifyClient("YOUR_APIFY_TOKEN")
run = client.actor("thanh81646/apify-us-healthcare-clinic-contact-enricher").call(
    run_input={
        "startUrls": [
            {"url": "https://pacificaudiology.com/"},
            {"url": "https://brooklyndentalstudio.com/"},
        ],
        "excludeChainsFromOutput": True,
    }
)

for clinic in client.dataset(run["defaultDatasetId"]).iterate_items():
    print(clinic["clinic_name"], clinic["ownership_status"], clinic["mx_dns_valid_emails"])
```

The same actor ID works from the Apify node in n8n or the "Run an Actor" module in Make.com.

## Limitations

- Static HTML only (no headless browser), so sites that render contacts with JavaScript return fewer results.
- The chain list is hand-written and US-focused. It will miss chains that are not on it.
- There is no NPI/NPPES lookup and no detection of booking widgets.

## Need a custom version?

If you need extra fields, another website, scheduled runs into Google Sheets, Airtable or a webhook, or an n8n / Make workflow around this actor, email **ttrungthanh90@gmail.com** with the target site and the fields you need, and I will reply with a fixed quote. You can also message me through my [Apify profile](https://apify.com/thanh81646).

## Author

Trung Thanh Tran: [Upwork](https://www.upwork.com/freelancers/trungthanhtrandev) · [GitHub](https://github.com/Tthanh2k6) · [Apify](https://apify.com/thanh81646) · [Contra](https://contra.com/trung_thanh_tran_7tjnw73h)

## Legal note

The actor only reads public, non-authenticated web pages at the user's direction. It does not access patient portals or any protected health information. Brand names in the chain list are trademarks of their owners and are used only to identify them. You are responsible for making sure your use, including any outreach, complies with applicable law (CAN-SPAM, TCPA, GDPR, CCPA).
