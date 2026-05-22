"""idle - (stretch) find idle EC2 instances by N-hour CPU average."""
import boto3
from datetime import datetime, timedelta, timezone
from statistics import mean


def _avg_cpu(cw, instance_id, hours):
    """Return average CPU% over last N hours, or None if no datapoints."""
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(hours=hours)
    resp = cw.get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName="CPUUtilization",
        Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
        StartTime=start,
        EndTime=end,
        Period=3600,
        Statistics=["Average"],
    )
    datapoints = resp.get("Datapoints", [])
    if not datapoints:
        return None
    return mean(dp["Average"] for dp in datapoints)


def run(args):
    """Entry point.

    Args set by argparse:
        args.threshold  - float, default 5.0 (% CPU)
        args.hours      - int, default 24
    """
    ec2 = boto3.client("ec2")
    cw = boto3.client("cloudwatch")

    # Collect all running instances, skip keep=true
    running = []
    paginator = ec2.get_paginator("describe_instances")
    for page in paginator.paginate(
        Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
    ):
        for reservation in page["Reservations"]:
            for inst in reservation["Instances"]:
                tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
                if tags.get("keep", "").lower() == "true":
                    continue
                running.append((inst["InstanceId"], inst["InstanceType"]))

    print(
        f"Scanning running EC2 (excluding keep=true) - "
        f"threshold {args.threshold}% over {args.hours}h:"
    )
    print("-" * 78)

    idle_ids = []
    for iid, itype in running:
        avg = _avg_cpu(cw, iid, args.hours)
        if avg is None:
            cpu_label = "NO DATA"
            marker = ""
        elif avg < args.threshold:
            cpu_label = f"{avg:.2f}%"
            marker = "  <- IDLE"
            idle_ids.append(iid)
        else:
            cpu_label = f"{avg:.2f}%"
            marker = ""
        print(f"  {iid:<24} {itype:<12} cpu_{args.hours}h={cpu_label}{marker}")

    print("-" * 78)
    print()
    print(f"Idle: {len(idle_ids)} instance(s): {idle_ids}")
    print("Tip: combo with terminate →  ./costctl.py terminate ec2 --id <id>")
