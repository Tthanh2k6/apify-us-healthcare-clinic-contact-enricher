# US Healthcare Clinic Contact, Schema & Chain Detector (Apify Actor)

High-speed **Python Async (`httpx` + `BeautifulSoup4` + `DNS/MX Verification`) Apify Actor** purpose-built for healthcare B2B sales teams, medical device manufacturers, dental/audiology wholesalers, SaaS SDRs, and healthcare recruiting agencies targeting **genuinely independent US private practices**.

Given any list of clinic URLs (from Google Maps scrapers, NPI registries, or CRM exports), this Actor extracts **DNS/MX-verified emails, E.164 US phone numbers, 5-platform social links (`FB, IG, LI, YT, X`), `Schema.org` `MedicalOrganization` metadata**, and automatically classifies every domain into **`Verified Independent`**, **`Chain Excluded`**, or **`Needs Review`** by screening against **38+ major US Dental DSOs, Audiology retail chains, Veterinary consolidators, and Private-Equity MSOs**.

---

## ✨ Key Engineering Capabilities

- **Automatic Corporate Chain / DSO / Franchise Screening:** Identifies national DSOs, retail franchises, and private-equity MSOs (*Aspen Dental, Heartland Dental, Pacific Dental Services, Miracle-Ear, Beltone, HearingLife, Banfield, VCA, BluePearl, The Joint Chiropractic, ATI PT, One Medical, MyEyeDr*, franchise legal disclosures, and `15+` store-locator footprints).
- **DNS / MX Deliverability Check:** Strips telemetry/asset false positives (`sentry.io`, `wixpress.com`, `.png`, `.webp`) and performs async DNS `MX` + `A` resolution on every discovered email domain (`mx_dns_valid_emails`).
- **Smart Internal Subpage Crawling:** Automatically inspects `/contact`, `/about`, `/our-practice`, and `/locations` pages (up to 2 internal subpages per clinic) to maximize front-desk/owner contact capture.
- **Schema.org Healthcare Entity Extraction:** Parses `MedicalOrganization`, `Dentist`, `Physician`, `VeterinaryCare`, `MedicalClinic`, and `LocalBusiness` JSON-LD `@graph` blocks (`address`, `medicalSpecialty`, `aggregateRating`, `parentOrganization`).
- **256 MB Lightweight Execution:** Pure async `httpx` architecture — zero headless Chromium bloat, enriching hundreds of clinics per minute for pennies.

---

## 📥 Input Configuration

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
  "maxConcurrency": 5
}
```

---

## 📤 Sample Output Record

```json
{
  "url": "https://pacificaudiology.com/",
  "clinic_name": "Pacific Audiology Clinic",
  "specialty_category": "Audiology & Hearing Care",
  "ownership_status": "Verified Independent",
  "chain_confidence_score": 0.05,
  "chain_signals": [],
  "emails": ["info@pacificaudiology.com"],
  "mx_dns_valid_emails": ["info@pacificaudiology.com"],
  "phones": ["+1-503-292-8700"],
  "social_profiles": {
    "facebook": ["https://www.facebook.com/..."]
  },
  "medical_schema_types": ["LocalBusiness", "MedicalOrganization"],
  "pages_crawled": 3,
  "status_code": 200,
  "error": null
}
```

---

## 🛠️ Integration with n8n, Make.com & Python

### 1. Python (`apify-client`)
```python
from apify_client import ApifyClient

client = ApifyClient("YOUR_APIFY_TOKEN")
run = client.actor("thanh81646/us-healthcare-clinic-contact-enricher").call(
    run_input={
        "startUrls": [
            {"url": "https://pacificaudiology.com/"},
            {"url": "https://brooklyndentalstudio.com/"},
        ],
        "excludeChainsFromOutput": True,
    }
)

for clinic in client.dataset(run["defaultDatasetId"]).iterate_items():
    print(clinic["clinic_name"], "->", clinic["ownership_status"], clinic["mx_dns_valid_emails"])
```

### 2. n8n Workflow (`Google Maps Scraper -> Clinic Chain Filter -> HubSpot / Lemlist`)
1. Trigger a Google Maps or NPI directory scrape in **n8n**.
2. Pass extracted clinic `website` URLs to the **Apify** node running `us-healthcare-clinic-contact-enricher` with `excludeChainsFromOutput: true`.
3. Route only **`Verified Independent`** practices with `mx_dns_valid_emails` directly into **HubSpot**, **Instantly**, **Smartlead**, or **Google Sheets**!

### 3. Make.com Scenario
1. Watch new healthcare leads in **Airtable / Google Sheets**.
2. Call **Apify -> Run an Actor** (`us-healthcare-clinic-contact-enricher`) synchronously.
3. Update the lead status column with `ownership_status`, `specialty_category`, and `mx_dns_valid_emails`.

---

## 💼 Need Custom Healthcare Lead Scrapers, NPI Enrichers, or AI Automations?

Built and maintained by **Trung Thanh Tran** (*Python, Playwright, n8n & AI Automation Engineer*):

- 🟢 **Hire me on Upwork (Custom Healthcare Lead Lists, Scrapers & AI Pipelines):** [upwork.com/freelancers/trungthanhtrandev](https://www.upwork.com/freelancers/trungthanhtrandev)
- ⚡ **Order Fast-Turnaround Data & Scraping Gigs on Fiverr:** [fiverr.com/trungthnhtrn244](https://www.fiverr.com/trungthnhtrn244)
- 📦 **Download the Complete Python, AI & n8n Scraper Toolkit Pro (6 CLI Engines + 3 Blueprints):** [trungthanh16.gumroad.com/l/python-ai-automation-n8n-scraper-toolkit-pro](https://trungthanh16.gumroad.com/l/python-ai-automation-n8n-scraper-toolkit-pro)
- 💻 **GitHub Portfolio:** [github.com/Tthanh2k6](https://github.com/Tthanh2k6)
