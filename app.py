#!/usr/bin/env python3
import os

import aws_cdk as cdk

from cdk.cdk_stack import CdkStack


aws_env = cdk.Environment(
    account=os.environ["AWS_ACCOUNT_ID"], region=os.environ["REGION"]
)


app = cdk.App()
CdkStack(app, "CdkStack", env=aws_env)

app.synth()
