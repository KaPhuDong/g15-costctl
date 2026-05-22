"""cost - show cost of resources matching a tag, over the last N days."""
import boto3
from collections import defaultdict
from datetime import date, timedelta

from commands._common import parse_kv


def run(args):
    """Entry point.

    Args set by argparse:
        args.tag   - "key=value" string (REQUIRED)
        args.days  - int, default 7
    """
    tag_key, tag_value = parse_kv(args.tag)

    end_date = date.today()
    start_date = end_date - timedelta(days=args.days)
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    ce = boto3.client("ce")
    response = ce.get_cost_and_usage(
        TimePeriod={"Start": start_str, "End": end_str},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
        Filter={"Tags": {"Key": tag_key, "Values": [tag_value]}},
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )

    # Accumulate cost per service across all days
    totals = defaultdict(float)
    for day in response.get("ResultsByTime", []):
        for group in day.get("Groups", []):
            service = group["Keys"][0]
            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
            totals[service] += amount

    # Sort descending by cost, drop zero-cost services
    rows = sorted(
        ((svc, amt) for svc, amt in totals.items() if amt > 0),
        key=lambda x: x[1],
        reverse=True,
    )
    grand_total = sum(amt for _, amt in rows)

    # Output
    print(f"Cost for {args.tag} over last {args.days} days ({start_str} → {end_str}):")
    print("-" * 60)
    for svc, amt in rows:
        print(f"  {svc:<45}  ${amt:>8.2f}")
    print("-" * 60)
    print(f"  {'TOTAL':<45}  ${grand_total:>8.2f}")
