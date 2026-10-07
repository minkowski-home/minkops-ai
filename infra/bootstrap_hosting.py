"""Explicit operator setup for Firebase Hosting and pilot billing controls."""

from google_api import GoogleApi

PROJECT = "minkops-ai-prod"
BILLING = "01CA76-B60F26-EF46E3"


def hosting():
    api = GoogleApi(PROJECT)
    base = "https://firebase.googleapis.com/v1beta1"
    projects = api.request(f"{base}/projects").get("results", [])
    if not any(project.get("projectId") == PROJECT for project in projects):
        operation = api.request(f"{base}/projects/{PROJECT}:addFirebase", {})
        api.wait(f"{base}/{operation['name']}")
    hosting = f"https://firebasehosting.googleapis.com/v1beta1/projects/{PROJECT}/sites"
    sites = api.request(hosting).get("sites", [])
    for site in (PROJECT, "minkops-ai-console"):
        if not any(item["name"].endswith(f"/{site}") for item in sites):
            api.request(f"{hosting}?siteId={site}", {})
        print(f"Hosting site ready: {site}")


def budgets():
    api = GoogleApi(PROJECT)
    budgets_url = f"https://billingbudgets.googleapis.com/v1/billingAccounts/{BILLING}/budgets"
    budgets = api.request(budgets_url).get("budgets", [])
    for title, amount, capped in (("Minkops hosting monthly target CAD 15", "15", False),
                                  ("Minkops Cloud Run spend cap CAD 10", "10", True)):
        if any(item["displayName"] == title for item in budgets):
            continue
        filters = {"projects": [f"projects/{PROJECT}"], "calendarPeriod": "MONTH"}
        body = {"displayName": title, "budgetFilter": filters,
                "amount": {"specifiedAmount": {"units": amount, "currencyCode": "CAD"}},
                "thresholdRules": [{"thresholdPercent": value} for value in (0.5, 0.8, 1.0)],
                "notificationsRule": {"enableProjectLevelRecipients": True}}
        if capped:
            filters.update(services=["services/152E-C115-5142"],
                           creditTypesTreatment="EXCLUDE_ALL_CREDITS")
            body["spendCap"] = {"inputState": "CONFIGURED"}
        result = api.request(budgets_url, body)
        print(f"Budget ready: {result['displayName']}; cap={result.get('spendCap', {}).get('outputState', 'alerts only')}")


if __name__ == "__main__":
    budgets()
    hosting()
