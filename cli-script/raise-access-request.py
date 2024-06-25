#!/usr/bin/env python3
# Simple script to raise AWS IAM Identity Center JIT with SSM request
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import sys
import argparse
import re
import boto3
from botocore.config import Config
import json

boto3_config = Config(retries={'max_attempts': 10, 'mode': 'standard'})
ssm = boto3.client('ssm', config=boto3_config)

# Constants:
TAG_VALUE_CHANGEMANAGER_TEMPLATE="IAMIdentityCenterJITwithSSMChangeManagerTemplate"
MAXIMUM_DURATION_HOURS_REQUESTABLE=12

def get_change_manager_template_document_name():
    '''
    Return the relevant change manager template document name.
    ''' 
    try:
        documents = []
        paginator = ssm.get_paginator('list_documents')
        for page in paginator.paginate(
            Filters = [
                {
                    'Key': 'DocumentType',
                    'Values': [ 'Automation.ChangeTemplate' ]
                },
                {
                    'Key': 'tag:Component',
                    'Values': [ TAG_VALUE_CHANGEMANAGER_TEMPLATE ]
                },
            ]
        ):
            documents.extend(page['DocumentIdentifiers'])

        return documents[0]['Name']
    except:
        sys.exit(f'Could not find change template with the tag key Component and value: {TAG_VALUE_CHANGEMANAGER_TEMPLATE}')


def get_runbook_from_change_manager_template(template):
    '''
    Get the SSM runbook associated with the given change manager template name
    '''
    try:
        content_string = ssm.get_document(Name=template)['Content']
        content_json = json.loads(content_string)
        return content_json['executableRunBooks'][0]['name']
    except:
        sys.exit(f'Could not find runbook associated with the change manager template: {template}')


def get_allowed_values(runbook, parameter):
    '''
    Get list of allowed values for the parameter for the given SSM document runbook
    '''
    try:
        content_string = ssm.get_document(Name=runbook)['Content']
        content_json = json.loads(content_string)
        return content_json['parameters'][parameter]['allowedValues']
    except:
        sys.exit(f'Could not get allowed values for : {runbook} for parameter {parameter}')


# main()

# Take arguments:
parser = argparse.ArgumentParser()
parser.add_argument('--name', default=None)
parser.add_argument('--description', default=None)
parser.add_argument('--hours', default=None)
parser.add_argument('--username', default=None)
parser.add_argument('--accountid', default=None)
parser.add_argument('--permissionset', default=None)
parser.add_argument('--autoapprove', default=False)
parser.add_argument('--skip-validation', action='store_true')
args = parser.parse_args()

name = args.name if args.name else input('Request name (no spaces): ')
description = args.description if args.description else input('Request description/justification: ')
username = args.username if args.username else input('Username (login used to acess AWS): ')
accountid = args.accountid if args.accountid else input('AWS Account ID: ')
hours = args.hours if args.hours else input('Duration of access (hours): ')
permissionset = args.permissionset if args.permissionset else input('Permission set: ')

change_manager_template = get_change_manager_template_document_name()
runbook = get_runbook_from_change_manager_template(change_manager_template)

# Validation:
if not args.skip_validation:
    # Title:
    if re.search('[^a-zA-Z0-9_.-]', name) or len(name) < 3 or len(name) > 128:
        sys.exit(f'Error: The name must have 3-128 characters. Valid characters: a-z, A-Z, 0-9, - (hyphen), _ (underscore), and . (dot).')
    # AWS Account ID
    if re.search('[^0-9]', accountid) or len(accountid) != 12:
        sys.exit(f'Error: Invalid AWS account ID, expected a 12 digit number')
    # Duration
    allowed_duration_values = get_allowed_values(runbook, 'DurationHours')
    if not hours in allowed_duration_values:
        sys.exit(f'Error: Invalid duration hours, expected a value in {allowed_duration_values}')
    # Permission set
    allowed_permission_set_values = get_allowed_values(runbook, 'PermissionSet')
    if not permissionset in allowed_permission_set_values:
        sys.exit(f'Error: Invalid permission set, expected a value in {allowed_permission_set_values}')

# Raise request:

response = ssm.start_change_request_execution(
    ChangeRequestName = name,
    DocumentName = change_manager_template,
    AutoApprove = args.autoapprove,
    ChangeDetails = description,
    Runbooks = [
        {
            "DocumentName": runbook,
            "DocumentVersion": "$DEFAULT",
            "MaxConcurrency": "1",
            "MaxErrors": "1",
            "Parameters": {
                "DurationHours": [ hours ],
                "RequestingUsername": [ username ],
                "AccountID": [ accountid ],
                "PermissionSet": [ permissionset ]
            }
        }
    ]
)

print(f"Execution ID is {response['AutomationExecutionId']}")
