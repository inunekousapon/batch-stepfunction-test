import os

from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecr_assets as ecr_assets,
    aws_batch_alpha as batch,
    aws_iam as iam,
    aws_stepfunctions_tasks as stepfunctions_tasks,
    aws_stepfunctions as stepfunctions,
    aws_sns as sns,
    aws_lambda_python_alpha as aws_lambda_python,
    aws_lambda,
    aws_lambda_event_sources,
)
from constructs import Construct
from .instance_profile import InstanceProfile


class CdkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc(
            self, "batch-job-vpc", nat_gateways=0, max_azs=1
        )
        sg = ec2.SecurityGroup(
            self,
            "test-security-group",
            vpc=vpc,
            security_group_name="batch-job-security-group",
        )
        docker_image_asset = ecr_assets.DockerImageAsset(
            self,
            "ecr-docker-image-asset",
            directory="./batch",
        )
        docker_container_image = ecs.ContainerImage.from_docker_image_asset(
            docker_image_asset
        )
        batch_job_definition = batch.JobDefinition(
            self,
            "job-definition",
            job_definition_name="batch-job-definition",
            container=batch.JobDefinitionContainer(
                image=docker_container_image,
                gpu_count=0,
                vcpus=2,
                memory_limit_mib=128,
                log_configuration=batch.LogConfiguration(
                    log_driver=batch.LogDriver.AWSLOGS,
                    options={"awslogs-region": "ap-northeast-1"},
                ),
            ),
            retry_attempts=1,
            timeout=Duration.minutes(1),
        )
        batch_instance_role = iam.Role(
            self,
            "batch-job-instance-role",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("ec2.amazonaws.com"),
                iam.ServicePrincipal("ecs.amazonaws.com"),
                iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            ),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonEC2ContainerServiceforEC2Role"
                ),
            ],
        )
        batch_instance_profile = InstanceProfile(
            self, "batch-job-instance-profile"
        )
        batch_instance_profile.attach_role(batch_instance_role)
        compute_environment = batch.ComputeEnvironment(
            self,
            "batch-compute-environment",
            compute_environment_name="batch-compute-environment",
            compute_resources=batch.ComputeResources(
                vpc=vpc,
                vpc_subnets=ec2.SubnetSelection(subnets=vpc.public_subnets),
                minv_cpus=0,
                desiredv_cpus=2,
                maxv_cpus=32,
                instance_role=batch_instance_profile.profile_arn,
                security_groups=[sg],
                type=batch.ComputeResourceType.ON_DEMAND,
                allocation_strategy=batch.AllocationStrategy.BEST_FIT_PROGRESSIVE,
            ),
        )
        job_queue = batch.JobQueue(
            self,
            "job-queue",
            job_queue_name="batch-job-queue",
            priority=1,
            compute_environments=[
                batch.JobQueueComputeEnvironment(
                    compute_environment=compute_environment, order=1
                )
            ],
        )
        # StepFunctions Definition
        submit_job = stepfunctions_tasks.BatchSubmitJob(
            self,
            "batch-submit-job",
            job_definition_arn=batch_job_definition.job_definition_arn,
            job_queue_arn=job_queue.job_queue_arn,
            array_size=5,
            job_name="Job",
        )
        topic = sns.Topic(
            self,
            "batch-notification-topic",
            display_name="chatbot-batch-notification-topic",
            topic_name="ChatbotBatchNotificationTopic",
        )
        sns_publish_task = stepfunctions_tasks.SnsPublish(
            self,
            "batch-fail-publish",
            topic=topic,
            message=stepfunctions.TaskInput.from_json_path_at("$.Cause"),
        )

        success_pass = stepfunctions.Pass(self, "Succeeded")        
        submit_job.add_catch(sns_publish_task, errors=["States.ALL"])

        # Create Chain
        stepfunction_definition = submit_job.next(success_pass)

        # Create State Machine
        stepfunction_state_machine = stepfunctions.StateMachine(
            self,
            "StateMachine",
            definition=stepfunction_definition,
            timeout=Duration.minutes(5),
        )
        CfnOutput(
            self,
            "stateMachineArnOutput",
            value=stepfunction_state_machine.state_machine_arn,
            export_name="stateMachineArn",
        )

        slack_notification_func = aws_lambda_python.PythonFunction(
            self,
            "slack-notification",
            entry="./slack_notification",
            runtime=aws_lambda.Runtime.PYTHON_3_8,
            environment={
                "SLACK_WEBHOOK_URL", os.environ["SLACK_WEBHOOK_URL"]
            }
        )
        slack_notification_func.add_event_source(
            aws_lambda_event_sources.SnsEventSource(topic)
        )
