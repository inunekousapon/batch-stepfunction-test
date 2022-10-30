import json
import urllib3
import pprint
import os

http = urllib3.PoolManager()



def handler(event, context):
    url = os.environ["SLACK_WEBHOOK_URL"]
    rec = json.loads(event["Records"][0]["Sns"]["Message"])

    region = "us-east-1"
    job_id = None
    if "Container" in rec and "Environment" in rec["Container"]:
        for env in rec["Container"]["Environment"]:
            if "Name" in env and "Value" in env and env["Name"] == "AWS_REGION":
                region = env["Value"]
    if "JobId" in rec:
        job_id = rec["JobId"]
        batch_url = f'https://{region}.console.aws.amazon.com/batch/home?region={region}#jobs/array-job/{job_id}'
        output_message = f"""*AWS Batch failed to execute*
```
        {pprint.pformat(rec)}
```
Link: <{batch_url}>
"""
    else:
        output_message = f"""*AWS Batch failed to execute*
```
{pprint.pformat(rec)}
```
"""
    message_blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": output_message,
            },
        },
    ]

    msg = {
        "blocks": message_blocks,
    }

    encoded_msg = json.dumps(msg).encode("utf-8")
    resp = http.request("POST", url, body=encoded_msg)

    print(
        {
            "message": event["Records"][0]["Sns"]["Message"],
            "status_code": resp.status,
            "response": resp.data,
        }
    )
