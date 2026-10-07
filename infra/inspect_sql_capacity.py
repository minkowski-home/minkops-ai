"""Read cloud resource metrics; emit summaries, never access tokens or DB data."""

import argparse
import json
import subprocess
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

parser = argparse.ArgumentParser()
parser.add_argument("--gcloud", default="gcloud")
parser.add_argument("--project", required=True)
parser.add_argument("--instance", required=True)
args = parser.parse_args()
token = subprocess.run(
    [args.gcloud, "auth", "print-access-token"], check=True, capture_output=True, text=True
).stdout.strip()
end = datetime.now(timezone.utc)
summary = {}
for metric in (
    "cpu/utilization",
    "memory/utilization",
    "postgresql/num_backends",
    "disk/bytes_used",
):
    query = urlencode(
        {
            "filter": f'metric.type="cloudsql.googleapis.com/database/{metric}" AND resource.type="cloudsql_database" AND resource.labels.database_id="{args.project}:{args.instance}"',
            "interval.endTime": end.isoformat(),
            "interval.startTime": (end - timedelta(days=7)).isoformat(),
            "aggregation.alignmentPeriod": "3600s",
            "aggregation.perSeriesAligner": "ALIGN_MAX",
            "view": "FULL",
        }
    )
    request = Request(
        f"https://monitoring.googleapis.com/v3/projects/{args.project}/timeSeries?{query}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            data = json.load(response)
        values = [
            float(next(iter(p["value"].values())))
            for series in data.get("timeSeries", [])
            for p in series.get("points", [])
        ]
        summary[metric] = {
            "samples": len(values),
            "maximum": max(values) if values else None,
            "mean_hourly_maximum": sum(values) / len(values) if values else None,
        }
    except HTTPError as error:
        summary[metric] = {"unavailable": error.code}
print(json.dumps(summary, indent=2))
