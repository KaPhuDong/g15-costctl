# REFLECTIONS - costctl W6 Side Challenge
**Group 15 - BuildForce** | pvkhanhtruong1810@gmail.com

---

## 1. `clean --apply` blast radius: Lessons from the BuildForce architecture

**Specific scenario:** BuildForce runs on a shared workshop account. If someone accidentally runs:

```bash
./costctl.py clean --tag Environment=dev --apply
```

All EC2 instances in the `W6-prod-ASG` ASG, EBS volumes in `available` state, and any resource tagged `Environment=dev` will be deleted immediately - including resources belonging to other groups in the same account.

**What G15 already had (from MH-COST-A) and the lessons learned:**

1. **Lambda cost-guard scales the ASG to 0 instead of terminating directly** - This was the right call. If Lambda called `ec2:StopInstances` directly, the ASG would detect the instance as unhealthy and launch a new one immediately, so cost would not decrease. Setting `MinSize=0, DesiredCapacity=0` is the correct way to let the ASG drain and terminate on its own. `costctl clean` should follow this pattern: for EC2 instances inside an ASG, scale the ASG to 0 rather than terminating instances directly.

2. **The `keep=true` tag is a critical safety valve** - The group's Lambda cost-guard already implements logic to skip resources tagged `keep=true`. `costctl clean` should respect the same convention: never terminate a resource with `keep=true`, even if the tag filter matches.

3. **IAM Least-Privilege is the last line of defense** - The Lambda IAM Role only has `autoscaling:UpdateAutoScalingGroup` and `rds:StopDBInstance`, not `ec2:TerminateInstances`. If someone tries to run `costctl clean --apply` using that Lambda role's credentials, the command will fail at the IAM layer - that is real blast radius containment.

4. **Dry-run + interactive confirmation** - `clean` already defaults to dry-run. An explicit `confirm(f"About to terminate {total} resource(s). Proceed?")` prompt should be added even when `--apply` is passed, to prevent automation scripts from triggering it accidentally.

5. **CloudTrail is an indispensable audit trail** - The group had CloudTrail enabled. When an incident occurs, the `TerminateInstances` event in CloudTrail shows exactly who ran what command, when, and from which IP.

**Conclusion:** The blast radius of `clean --apply` in BuildForce can affect the DocumentDB cluster (if tagged `Environment=dev`) and ASG instances. The most effective protection layers are IAM boundary + `keep=true` tag + CloudTrail - not just dry-run.

---

## 2. `costctl` vs Lambda cost-guard (MH-COST-A): Two complementary tools

G15 built both: `costctl` (CLI tool) and Lambda `w6-cost-guard` (automated action). Here is a practical comparison:

| Criteria | `costctl` (CLI) | Lambda `w6-cost-guard` |
|----------|-----------------|------------------------|
| **Trigger** | Manual, run by a person | Automatic: EventBridge daily 20:00 ICT + AWS Budgets $70/$150 |
| **Scope** | EC2, RDS, S3, Volume - by tag filter | ASG scale-down + DocumentDB stop |
| **Safety** | Dry-run by default, confirm y/N | No prompt - acts immediately on trigger |
| **Audit** | Output to stdout | CloudWatch Logs + CloudTrail |
| **DocumentDB** | `terminate rds` calls `stop_db_instance` | Skips cluster (engine=docdb does not support stop), only stops instances |
| **Best for** | Ad-hoc cleanup, investigation, tagging | Automated nightly cleanup, budget enforcement |

**Important lesson about DocumentDB:** `costctl terminate rds` calls `stop_db_instance` - this works for a DocumentDB *instance* but **does not work for a DocumentDB *cluster***. The group's Lambda cost-guard handled this correctly: it skips clusters with `engine=docdb` because AWS does not support `stop_db_cluster` for DocumentDB. `costctl` should have the same logic.

**When to use which:**
- Use `costctl list` + `costctl cost` to **investigate** before taking action.
- Use `costctl tag` to **fix tagging** for resources with missing tags.
- Use `costctl clean --apply` for **controlled one-off cleanup**.
- Use Lambda cost-guard for **automated nightly enforcement** - no one needs to sit and wait.

---

## 3. `idle` vs AWS Trusted Advisor: Perspective from the BuildForce ASG

BuildForce uses ASG `W6-prod-ASG` with `MinSize=2, DesiredCapacity=2`. Here is the real-world context for comparison:

**`costctl idle` (24-hour window):**
- Good for detecting **forgotten instances** after working hours - for example, a dev spins up a test instance and forgets to terminate it.
- With the BuildForce ASG: if traffic is low at night, CPU on the 2 ASG instances may drop below 5% → `idle` will flag them as IDLE. But this is a **false positive** - the instances are waiting for traffic, not being wasted.
- Solution: add the `keep=true` tag to instances in the production ASG; `idle` will skip them.

**AWS Trusted Advisor (14-day window):**
- Better suited for BuildForce because the workload follows a weekly pattern (low traffic on weekends, high traffic early in the week when recruiters post jobs).
- Trusted Advisor also considers network I/O - an instance acting as an API gateway for Bedrock with low CPU but high network will not be flagged as underutilized.
- Downside: 14-day lag - it will not catch a dev instance forgotten since yesterday.

**Practical conclusion for G15:**
- `idle --hours 168` (7 days) + filter out instances with `keep=true` → better fit for BuildForce than 24 hours.
- Use Trusted Advisor for monthly rightsizing reviews (t3.micro → t3.nano if CPU p99 < 10%).
- Lambda cost-guard (scale ASG to 0 at 20:00) is the most practical solution for a 48-hour workshop.

---

## 4. Tagging Strategy: From theory to BuildForce practice

G15 enforces 4 mandatory tags on **every** billable resource:

| Tag Key | Value | Reason |
|---------|-------|--------|
| `Owner` | `pvkhanhtruong1810@gmail.com` | Trace the responsible person |
| `Environment` | `dev` | Distinguish environments, used as a filter in cost-guard |
| `CostCenter` | `G15` | Group billing by team within the workshop account |
| `Application` | `BuildForce` | Filter Cost Explorer by workload |

**Real issues encountered:**
- AWS Cost Explorer is case-sensitive: `dev` ≠ `Dev`. A single typo of `Dev` on one resource creates a separate line in Cost Explorer and breaks filters.
- The workshop account does not grant Billing console access → cost allocation tags cannot be activated → `Application=BuildForce` does not appear as a filter dimension in Cost Explorer. This is a sandbox limitation, not an implementation bug.
- `costctl tag` solves the typo problem: `./costctl.py list ec2 --missing-tag Application` finds resources missing the tag, then `./costctl.py tag ec2 --id <id> --set Application=BuildForce` fixes it immediately.

---

## 5. AI Assistance

The implementation in this project was carried out with AI assistance (Claude/Kiro). Percentage of AI-generated code without manual edits: ~85%.

Areas where the group made active decisions and intervened:
- **`stop_db_instance` instead of `delete_db_instance`** in `terminate_cmd.py` - consistent with the group's Lambda cost-guard, avoids losing DocumentDB data.
- **Skip DocumentDB cluster** in `terminate rds` - AWS does not support `stop_db_cluster` for the `docdb` engine, so it needs separate handling.
- **`keep=true` tag convention** - aligned with the existing Lambda cost-guard, not a new convention.
- **Filter `available` for volumes** in `clean_cmd.py` - volumes in `in-use` state cannot be deleted; the API call would fail.
- **Merge tags for S3** in `tag_cmd.py` - `put_bucket_tagging` replaces all tags entirely, so existing tags must be fetched and merged first.

---

*G15 - BuildForce - XBrain W6 Side Challenge - 2026-05-22*
*Members: Phạm Vũ Khánh Trường, Phan Anh Duy, Ka Phu Đông, Võ Lê Trường Huy, Hà Tây Nguyên, Nguyễn Thị Tiểu Phương, Nguyễn Đình Thi, Văn Phú Tín, Châu Thành Trung*
