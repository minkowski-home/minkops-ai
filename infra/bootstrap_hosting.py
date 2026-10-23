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
    # Reserve CAD8 for Minkops' shared SQL allocation and CAD2 for reporting/
    # enforcement lag. Alerts cannot impose a universal cloud hard stop.
    for title, previous_title, amount, capped in (
        ("Minkops exclusive resources target CAD 10", "Minkops hosting monthly target CAD 15", "10", False),
        ("Minkops Cloud Run spend cap CAD 6", "Minkops Cloud Run spend cap CAD 10", "6", True),
    ):
        matches = [item for item in budgets if item['displayName'] in (title, previous_title)]
        if len(matches) > 1:
            raise RuntimeError('Duplicate Minkops budgets require reconciliation before updating cost controls.')
        filters = {"projects": [f"projects/{PROJECT}"], "calendarPeriod": "MONTH"}
        body = {"displayName": title, "budgetFilter": filters,
                "amount": {"specifiedAmount": {"units": amount, "currencyCode": "CAD"}},
                "thresholdRules": [{"thresholdPercent": value} for value in (0.5, 0.8, 1.0)],
                "notificationsRule": {"enableProjectLevelRecipients": True}}
        if capped:
            filters.update(services=["services/152E-C115-5142"],
                           creditTypesTreatment="EXCLUDE_ALL_CREDITS")
            body["spendCap"] = {"inputState": "CONFIGURED"}
        if matches:
            existing = matches[0]
            body['name'] = existing['name']
            if existing.get('etag'):
                body['etag'] = existing['etag']
            fields = 'displayName,budgetFilter,amount,thresholdRules,notificationsRule'
            if capped:
                # An existing cap's scope stays unchanged. Google accepts the
                # amount/state update with its original normalized filters.
                body.update({key: existing[key] for key in
                    ('budgetFilter', 'thresholdRules', 'notificationsRule', 'ownershipScope') if key in existing})
                fields = 'displayName,amount,spendCap.inputState'
            result = api.request(f"https://billingbudgets.googleapis.com/v1/{existing['name']}?updateMask={fields}",
                                 body, method='PATCH')
        else:
            result = api.request(budgets_url, body)
        print(f"Budget ready: {result['displayName']}; cap={result.get('spendCap', {}).get('outputState', 'alerts only')}")


if __name__ == "__main__":
    budgets()
    hosting()
