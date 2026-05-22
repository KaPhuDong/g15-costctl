"""migrate-gp3 - (stretch) plan or apply gp2 → gp3 EBS migration."""
import boto3

# us-east-1 on-demand pricing per GB-month
GP2_PRICE = 0.10
GP3_PRICE = 0.08
SAVINGS_PER_GB = GP2_PRICE - GP3_PRICE  # $0.02


def run(args):
    """Entry point.

    Args set by argparse:
        args.apply       - bool, default False (dry-run)
        args.volume_id   - optional str, only migrate this volume when --apply
    """
    ec2 = boto3.client("ec2")

    # Fetch gp2 volumes (optionally restricted to one volume)
    filters = [{"Name": "volume-type", "Values": ["gp2"]}]
    if args.volume_id:
        filters.append({"Name": "volume-id", "Values": [args.volume_id]})

    paginator = ec2.get_paginator("describe_volumes")
    volumes = []
    for page in paginator.paginate(Filters=filters):
        volumes.extend(page["Volumes"])

    if not volumes:
        print("No gp2 volumes found.")
        return

    # --- Dry-run: print plan ---
    print(f"gp2 volumes (price delta ${SAVINGS_PER_GB:.3f}/GB-month):")
    print("-" * 78)
    total_savings = 0.0
    for vol in volumes:
        vid = vol["VolumeId"]
        size = vol["Size"]
        savings = size * SAVINGS_PER_GB
        total_savings += savings
        attachments = vol.get("Attachments", [])
        attached = attachments[0]["InstanceId"] if attachments else "(none)"
        print(f"  {vid}  {size:>6}GB  attached={attached:<20}  ${savings:.2f}/mo savings")
    print("-" * 78)
    print(f"\n  Total potential savings: ${total_savings:.2f}/mo")

    if not args.apply:
        print(
            "\n(dry-run - pass --apply --volume-id <id> to migrate one, "
            "or --apply to migrate ALL)"
        )
        return

    # --- Apply: migrate ---
    print()
    for vol in volumes:
        vid = vol["VolumeId"]
        ec2.modify_volume(
            VolumeId=vid,
            VolumeType="gp3",
            Iops=3000,
            Throughput=125,
        )
        print(f"  → modify_volume issued for {vid} (gp3, 3000 IOPS, 125 MiB/s)")

    print(
        "\nVolume(s) entering 'modifying' → 'optimizing' state. App stays online."
    )
    print(
        "Use `costctl list volume` after ~30 minutes to confirm 'in-use' + gp3."
    )
