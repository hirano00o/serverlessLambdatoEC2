"""This module is test."""

import json
import logging
import os
import urllib
import urllib.request
from base64 import b64decode

import boto3
from botocore.exceptions import ClientError

ENCRYPTED_WEBHOOK = os.environ["WEBHOOK_TOKEN"]
ENCRYPTED_TTOKEN = os.environ["T_TOKEN"]
ENCRYPTED_BTOKEN = os.environ["B_TOKEN"]
DECRYPTED_WEBHOOK = (
    boto3.client("kms")
    .decrypt(CiphertextBlob=b64decode(ENCRYPTED_WEBHOOK))["Plaintext"]
    .decode("utf-8")
)
DECRYPTED_TTOKEN = (
    boto3.client("kms")
    .decrypt(CiphertextBlob=b64decode(ENCRYPTED_TTOKEN))["Plaintext"]
    .decode("utf-8")
)
DECRYPTED_BTOKEN = (
    boto3.client("kms")
    .decrypt(CiphertextBlob=b64decode(ENCRYPTED_BTOKEN))["Plaintext"]
    .decode("utf-8")
)
WEBHOOK_URL = (
    "https://hooks.slack.com/services/"
    + DECRYPTED_TTOKEN
    + "/"
    + DECRYPTED_BTOKEN
    + "/"
    + DECRYPTED_WEBHOOK
)
HISTRY_URL = "https://slack.com/api/channels.history"
DELETE_URL = "https://slack.com/api/chat.delete"
ENCRYPTED_LEGACY_TOKEN = os.environ["LEGACY_TOKEN"]
DECRYPTED_LEGACY_TOKEN = boto3.client("kms").decrypt(
    CiphertextBlob=b64decode(ENCRYPTED_LEGACY_TOKEN)
)["Plaintext"]

logger = logging.getLogger()
logger.setLevel(logging.INFO)

commandList = ["help", "stop", "start", "list"]


class Command:
    """Command is command class."""

    def __init__(self, text):
        """__init__ is initialise this class."""
        textList = text.split(" ")
        self.command = textList[0]
        if len(textList) > 1:
            self.param = textList[1]
        else:
            self.param = ""

    def ok_command(self):
        """Set command list."""
        return self.command in commandList

    def help_command(self):
        """Set help command."""
        postSlack(
            "This command gives\n"
            "\thelp : show command list\n"
            "\tlist : show ec2 instances\n"
            "\tstop : stop selected ec2 instance\n"
            "\tstart : start selected ec2 instance"
        )

    def stop_command(self, ec2):
        """Stop command."""
        if self.param == "":
            return "put instance id. ex stop i-xxxxxxxxx."
        try:
            status = ec2.stop_instances(InstanceIds=[self.param])
        except ClientError as e:
            logger.error(e.response["Error"])
            return postSlack(e.response["Error"]["Message"])
        else:
            return postSlack(
                self.param
                + " is stopped.\nstatus is "
                + str(status["ResponseMetadata"]["HTTPStatusCode"])
            )

    def start_command(self, ec2):
        """Start command."""
        if self.param == "":
            return "put instance id. ex start i-xxxxxxxxx."
        try:
            status = ec2.start_instances(InstanceIds=[self.param])
        except ClientError as e:
            logger.error(e.response["Error"])
            return postSlack(e.response["Error"]["Message"])
        else:
            return postSlack(
                self.param
                + " is started.\nstatus is "
                + str(status["ResponseMetadata"]["HTTPStatusCode"])
            )

    def list_command(self, instances):
        """List command."""
        instanceList = []
        for reservation in instances["Reservations"]:
            for instance in reservation["Instances"]:
                instanceList.append(
                    instance["Tags"][0]["Value"]
                    + " is "
                    + instance["State"]["Name"]
                    + ". "
                    + instance["InstanceId"]
                    + "\n"
                )
        instanceList.sort()
        filtered = [str for str in instanceList if self.param in str]
        list = ""
        for instance in filtered:
            list += instance
        return postSlack(list)


def postSlack(text):
    """Post to slack."""
    request = urllib.request.Request(
        WEBHOOK_URL,
        json.dumps({"text": text}).encode(),
        {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        returnData = response.read()
        logger.info(returnData)


def deletePrePost(channel, process, startUnixTime):
    """Delete before post message."""
    logger.info("process id: " + process)
    params = {
        "channel": channel,
        "token": DECRYPTED_LEGACY_TOKEN,
        "oldest": startUnixTime,
    }

    request = urllib.request.Request(HISTRY_URL)
    historyParams = urllib.parse.urlencode(params).encode("ascii")
    request.data = historyParams
    with urllib.request.urlopen(request) as response:
        returnData = response.read()
        logger.info(returnData)
    data = json.loads(returnData)
    for message in data["messages"]:
        if process in message["text"]:
            params = {
                "channel": channel,
                "token": DECRYPTED_LEGACY_TOKEN,
                "ts": message["ts"],
            }
            request = urllib.request.Request(DELETE_URL)
            deleteParams = urllib.parse.urlencode(params).encode("ascii")
            request.data = deleteParams
            with urllib.request.urlopen(request) as response:
                returnData = response.read()
                logger.info(returnData)


def lambda_handler(event, context):
    """Lambda handler."""
    command_text = event["text"]
    channelId = event["channel_id"]
    processId = event["process_id"]
    startUnixTime = event["start_unix_time"]

    commandProcess = Command(command_text)
    if commandProcess.ok_command() == False:
        commandProcess.help_command()
    else:
        ec2 = boto3.client("ec2")
        if commandProcess.command == "help":
            commandProcess.help_command()
        elif commandProcess.command == "stop":
            commandProcess.stop_command(ec2)
        elif commandProcess.command == "start":
            commandProcess.start_command(ec2)
        elif commandProcess.command == "list":
            commandProcess.list_command(ec2.describe_instances())

    deletePrePost(channelId, processId, startUnixTime)

    return {"statusCode": 200}
