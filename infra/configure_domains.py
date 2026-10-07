"""Request managed custom domains and print Google's required DNS updates."""

import json
from google_api import GoogleApi

BASE = "https://firebasehosting.googleapis.com/v1beta1"
PROJECT = "minkops-ai-prod"


def main():
    api = GoogleApi(PROJECT)
    for site, domains in ((PROJECT, (("minkops.com", {}), ("www.minkops.com", {"redirectTarget": "minkops.com"}))),
                          ("minkops-ai-console", (("app.minkops.com", {}),))):
        parent = f"projects/{PROJECT}/sites/{site}/customDomains"
        existing = api.request(f"{BASE}/{parent}").get("customDomains", [])
        for domain, body in domains:
            if not any(item["name"].endswith("/" + domain) for item in existing):
                api.request(f"{BASE}/{parent}?customDomainId={domain}", body)
            result = api.request(f"{BASE}/{parent}/{domain}")
            updates = [record for section in result.get("requiredDnsUpdates", {}).values() if isinstance(section, list)
                       for domain_update in section for record in domain_update.get("records", []) if record.get("requiredAction")]
            print(json.dumps({"domain": domain, "host": result.get("hostState"),
                              "ownership": result.get("ownershipState"), "dns": updates,
                              "certificate": result.get("cert", {}).get("state")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
