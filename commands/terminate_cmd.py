"""terminate - terminate or delete one resource, with safety confirmation."""
import boto3
from botocore.exceptions import ClientError

from commands._common import confirm


def _terminate_ec2(rid, force):
    """Terminate one EC2 instance after confirmation."""
    if not confirm(f"Terminate EC2 {rid}?", force=force):
        print("Aborted.")
        return
    ec2 = boto3.client("ec2")
    ec2.terminate_instances(InstanceIds=[rid])
    print(f"Terminated EC2 {rid}")


def _terminate_rds(rid, force):
    """Stop one RDS instance after confirmation."""
    if not confirm(f"Stop RDS {rid}?", force=force):
        print("Aborted.")
        return
    rds = boto3.client("rds")
    rds.stop_db_instance(DBInstanceIdentifier=rid)
    print(f"Stopped RDS {rid}")


def _terminate_s3(rid, force):
    """Delete one S3 bucket - refuse if it has any objects."""
    s3 = boto3.client("s3")
    resp = s3.list_objects_v2(Bucket=rid)
    count = resp.get("KeyCount", 0)
    if count > 0:
        print(f"Refusing - bucket {rid} has {count} object(s). Empty it first.")
        return
    if not confirm(f"Delete S3 bucket {rid}?", force=force):
        print("Aborted.")
        return
    s3.delete_bucket(Bucket=rid)
    print(f"Deleted S3 bucket {rid}")


def _terminate_volume(rid, force):
    """Delete one EBS volume after confirmation."""
    if not confirm(f"Delete volume {rid}?", force=force):
        print("Aborted.")
        return
    ec2 = boto3.client("ec2")
    ec2.delete_volume(VolumeId=rid)
    print(f"Deleted volume {rid}")


DISPATCH = {
    "ec2": _terminate_ec2,
    "rds": _terminate_rds,
    "s3": _terminate_s3,
    "volume": _terminate_volume,
}


def run(args):
    """Entry point called by costctl.py."""
    try:
        DISPATCH[args.type](args.id, args.force)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        msg = e.response["Error"]["Message"]
        print(f"AWS error [{code}]: {msg}")
