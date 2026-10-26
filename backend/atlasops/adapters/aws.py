from datetime import timedelta

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from atlasops.adapters.contracts import AdapterError, Capabilities
from atlasops.models import now


class AWS:
    capabilities = Capabilities(frozenset({"ec2.inventory", "cloudwatch.cpu", "cloudwatch.alarms"}))

    def __init__(self, config: dict):
        sdk_config = Config(
            connect_timeout=5, read_timeout=10, retries={"max_attempts": 3, "mode": "standard"}
        )
        try:
            self.ec2 = boto3.client("ec2", region_name=config["region"], config=sdk_config)
            self.cloudwatch = boto3.client("cloudwatch", region_name=config["region"], config=sdk_config)
        except BotoCoreError:
            raise AdapterError("aws_credential_configuration_unavailable")

    def inventory(self, resource_scope: list[str]) -> list[dict]:
        if not resource_scope or len(resource_scope) > 100:
            raise AdapterError("explicit_aws_resource_scope_required")
        try:
            records = []
            pages = self.ec2.get_paginator("describe_instances").paginate(
                Filters=[{"Name": "instance-id", "Values": resource_scope}],
                PaginationConfig={"MaxItems": 1000, "PageSize": 100},
            )
            for page in pages:
                for reservation in page.get("Reservations", []):
                    for item in reservation.get("Instances", []):
                        records.append(
                            {
                                "resource": item["InstanceId"],
                                "state": item["State"]["Name"],
                                "instance_type": item["InstanceType"],
                                "tags": item.get("Tags", []),
                            }
                        )
            return records
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "")
            raise AdapterError(
                "permission_denied"
                if code in ("UnauthorizedOperation", "AccessDenied", "AccessDeniedException")
                else "aws_request_failed"
            )
        except BotoCoreError:
            raise AdapterError("aws_unavailable", retryable=True)

    def cpu(self, resource_id: str) -> dict:
        try:
            result = self.cloudwatch.get_metric_statistics(
                Namespace="AWS/EC2",
                MetricName="CPUUtilization",
                Dimensions=[{"Name": "InstanceId", "Value": resource_id}],
                StartTime=now() - timedelta(minutes=15),
                EndTime=now(),
                Period=300,
                Statistics=["Average"],
            )
            return {
                "resource": resource_id,
                "metric": "CPUUtilization",
                "unit": "Percent",
                "datapoints": [
                    {"observed_at": p["Timestamp"].isoformat(), "value": p["Average"]}
                    for p in result["Datapoints"]
                ],
            }
        except (ClientError, BotoCoreError):
            raise AdapterError("cloudwatch_unavailable")

    def alarms(self, resource_scope: list[str]) -> list[dict]:
        try:
            result = []
            for page in self.cloudwatch.get_paginator("describe_alarms").paginate(
                AlarmTypes=["MetricAlarm"], PaginationConfig={"MaxItems": 1000}
            ):
                for alarm in page.get("MetricAlarms", []):
                    if any(
                        d.get("Name") == "InstanceId" and d.get("Value") in resource_scope
                        for d in alarm.get("Dimensions", [])
                    ):
                        result.append(
                            {
                                "name": alarm["AlarmName"],
                                "state": alarm["StateValue"],
                                "observed_at": alarm["StateUpdatedTimestamp"].isoformat(),
                            }
                        )
            return result
        except (ClientError, BotoCoreError):
            raise AdapterError("cloudwatch_unavailable")
