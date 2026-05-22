"""tag - add or update tags on one resource."""
import boto3
from botocore.exceptions import ClientError

from commands._common import parse_kv


def _to_tags(set_args):
    """Convert ['k1=v1', 'k2=v2'] to [{'Key':'k1','Value':'v1'}, ...]."""
    return [{"Key": k, "Value": v} for k, v in (parse_kv(s) for s in set_args)]


def _tag_ec2(rid, tags):
    """Apply tags to an EC2 instance."""
    ec2 = boto3.client("ec2")
    ec2.create_tags(Resources=[rid], Tags=tags)


def _tag_rds(rid, tags):
    """Apply tags to an RDS instance - requires ARN lookup first."""
    rds = boto3.client("rds")
    arn = rds.describe_db_instances(DBInstanceIdentifier=rid)[
        "DBInstances"
    ][0]["DBInstanceArn"]
    rds.add_tags_to_resource(ResourceName=arn, Tags=tags)


def _tag_s3(rid, tags):
    """Apply tags to an S3 bucket, merging with existing tags."""
    s3 = boto3.client("s3")
    # Fetch existing tags; treat missing tagging config as empty
    try:
        existing = s3.get_bucket_tagging(Bucket=rid)["TagSet"]
    except ClientError:
        existing = []

    # Merge: existing tags overridden by new ones (new tags win on key conflict)
    merged = {t["Key"]: t["Value"] for t in existing}
    for t in tags:
        merged[t["Key"]] = t["Value"]

    tag_set = [{"Key": k, "Value": v} for k, v in merged.items()]
    s3.put_bucket_tagging(Bucket=rid, Tagging={"TagSet": tag_set})


def _tag_volume(rid, tags):
    """Apply tags to an EBS volume."""
    ec2 = boto3.client("ec2")
    ec2.create_tags(Resources=[rid], Tags=tags)


DISPATCH = {
    "ec2": _tag_ec2,
    "rds": _tag_rds,
    "s3": _tag_s3,
    "volume": _tag_volume,
}


def run(args):
    """Entry point called by costctl.py."""
    tags = _to_tags(args.set)
    DISPATCH[args.type](args.id, tags)
    tag_str = ", ".join(f"{t['Key']}={t['Value']}" for t in tags)
    print(f"Applied {len(tags)} tag(s) to {args.type} {args.id}: {tag_str}")
