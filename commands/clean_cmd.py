"""clean - (stretch) bulk terminate resources matching a tag."""
import boto3

from commands._common import parse_kv

# States that mean the instance is already gone - skip them
_TERMINAL_STATES = {"shutting-down", "terminated"}


def _find_targets(tag_key, tag_val):
    """Return {"ec2": [...], "volume": [...]} matching tag in non-terminal state."""
    ec2 = boto3.client("ec2")
    targets = {"ec2": [], "volume": []}

    # --- EC2 instances ---
    paginator = ec2.get_paginator("describe_instances")
    for page in paginator.paginate(
        Filters=[{"Name": f"tag:{tag_key}", "Values": [tag_val]}]
    ):
        for reservation in page["Reservations"]:
            for inst in reservation["Instances"]:
                if inst["State"]["Name"] not in _TERMINAL_STATES:
                    targets["ec2"].append(inst["InstanceId"])

    # --- EBS volumes (available only - can't delete while attached) ---
    vol_paginator = ec2.get_paginator("describe_volumes")
    for page in vol_paginator.paginate(
        Filters=[
            {"Name": f"tag:{tag_key}", "Values": [tag_val]},
            {"Name": "status", "Values": ["available"]},
        ]
    ):
        for vol in page["Volumes"]:
            targets["volume"].append(vol["VolumeId"])

    return targets


def run(args):
    """Entry point.

    Args set by argparse:
        args.tag    - "key=value" string (REQUIRED)
        args.apply  - bool, must be True to actually delete (default False = dry-run)
    """
    tag_key, tag_val = parse_kv(args.tag)
    targets = _find_targets(tag_key, tag_val)

    ec2_ids = targets["ec2"]
    vol_ids = targets["volume"]
    total = len(ec2_ids) + len(vol_ids)

    if total == 0:
        print("Nothing to clean.")
        return

    # Print plan
    print(f"Resources matching {args.tag}:")
    for iid in ec2_ids:
        print(f"  EC2     {iid}")
    for vid in vol_ids:
        print(f"  volume  {vid}")

    if not args.apply:
        print(f"\n(dry-run - pass --apply to terminate {total} resource(s))")
        return

    # Apply: bulk terminate
    ec2 = boto3.client("ec2")

    if ec2_ids:
        ec2.terminate_instances(InstanceIds=ec2_ids)
        print(f"Terminated {len(ec2_ids)} EC2 instance(s): {ec2_ids}")

    for vid in vol_ids:
        ec2.delete_volume(VolumeId=vid)
        print(f"Deleted volume {vid}")
