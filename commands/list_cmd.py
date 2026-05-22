"""list - list AWS resources by type, filter by tag / missing-tag."""
import boto3
from botocore.exceptions import ClientError

from commands._common import parse_kv, tags_to_dict, tags_match


def _list_ec2(want, missing):
    """List EC2 instances matching tag filters.

    Returns:
        list of (instance_id, instance_type, state, tags_dict) tuples
    """
    ec2 = boto3.client("ec2")
    results = []
    paginator = ec2.get_paginator("describe_instances")
    for page in paginator.paginate():
        for reservation in page["Reservations"]:
            for inst in reservation["Instances"]:
                tags = tags_to_dict(inst.get("Tags", []))
                if tags_match(tags, want, missing):
                    results.append((
                        inst["InstanceId"],
                        inst["InstanceType"],
                        inst["State"]["Name"],
                        tags,
                    ))
    return results


def _list_rds(want, missing):
    """List RDS DB instances matching tag filters.

    Returns:
        list of (db_id, db_class, db_status, tags_dict) tuples
    """
    rds = boto3.client("rds")
    results = []
    paginator = rds.get_paginator("describe_db_instances")
    for page in paginator.paginate():
        for db in page["DBInstances"]:
            arn = db["DBInstanceArn"]
            tag_list = rds.list_tags_for_resource(ResourceName=arn)["TagList"]
            tags = tags_to_dict(tag_list)
            if tags_match(tags, want, missing):
                results.append((
                    db["DBInstanceIdentifier"],
                    db["DBInstanceClass"],
                    db["DBInstanceStatus"],
                    tags,
                ))
    return results


def _list_s3(want, missing):
    """List S3 buckets matching tag filters.

    Returns:
        list of (bucket_name, "bucket", "active", tags_dict) tuples
    """
    s3 = boto3.client("s3")
    results = []
    buckets = s3.list_buckets().get("Buckets", [])
    for bucket in buckets:
        name = bucket["Name"]
        try:
            tag_set = s3.get_bucket_tagging(Bucket=name)["TagSet"]
            tags = tags_to_dict(tag_set)
        except ClientError:
            tags = {}
        if tags_match(tags, want, missing):
            results.append((name, "bucket", "active", tags))
    return results


def _list_volume(want, missing):
    """List EBS volumes matching tag filters.

    Returns:
        list of (volume_id, "<type>-<size>GB", state, tags_dict) tuples
    """
    ec2 = boto3.client("ec2")
    results = []
    paginator = ec2.get_paginator("describe_volumes")
    for page in paginator.paginate():
        for vol in page["Volumes"]:
            tags = tags_to_dict(vol.get("Tags", []))
            if tags_match(tags, want, missing):
                size_label = f"{vol['VolumeType']}-{vol['Size']}GB"
                results.append((
                    vol["VolumeId"],
                    size_label,
                    vol["State"],
                    tags,
                ))
    return results


DISPATCH = {
    "ec2": _list_ec2,
    "rds": _list_rds,
    "s3": _list_s3,
    "volume": _list_volume,
}


def run(args):
    """Entry point called by costctl.py."""
    want = [parse_kv(t) for t in args.tag]
    missing = args.missing_tag

    rows = DISPATCH[args.type](want, missing)

    # Build header label
    tag_label = " ".join(args.tag) if args.tag else ""
    missing_label = " ".join(f"!{k}" for k in missing) if missing else ""
    filter_label = " ".join(filter(None, [tag_label, missing_label]))
    header = f"{args.type.upper()}"
    if filter_label:
        header += f" {filter_label}"
    header += f" - {len(rows)} found:"

    print(header)
    print("-" * 78)
    for row in rows:
        # row = (id, type_or_class, state, tags_dict)
        rid, rtype, rstate, tags = row
        tags_str = " ".join(f"{k}={v}" for k, v in tags.items())
        print(f"  {rid:<40} {rtype:<14} {rstate:<14} {tags_str}")
