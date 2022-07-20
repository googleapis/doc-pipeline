# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import shutil
import sys

import click
import docuploader.credentials
from docuploader import log
from google.cloud import storage

from docpipeline import generate, local_generate


# The docuploader logger is initialized as "docuploader"; change it to docpipeline.
log.logger = logging.getLogger("docpipeline")

REQUIRED_CMDS = ["docfx", "docuploader"]

VERSION = "0.0.0-dev"


def verify():
    for cmd in REQUIRED_CMDS:
        if shutil.which(cmd) is None:
            log.error(f"Could not find {cmd} command!")
            return sys.exit(1)


@click.group()
@click.version_option(message="%(version)s", version=VERSION)
def main():
    pass


@main.command()
@click.argument("bucket_name")
def build_new_docs(bucket_name: str) -> None:
    verify()
    credentials, project_id = docuploader.credentials.find(credentials_file="")
    storage_client = storage.Client(project=project_id, credentials=credentials)

    try:
        generate.build_new_docs(bucket_name, storage_client)
    except Exception as e:
        log.error(e)
        sys.exit(1)


@main.command()
@click.argument("bucket_name")
def build_all_docs(bucket_name: str) -> None:
    verify()
    credentials, project_id = docuploader.credentials.find(credentials_file="")
    storage_client = storage.Client(project=project_id, credentials=credentials)

    try:
        generate.build_all_docs(bucket_name, storage_client)
    except Exception as e:
        log.error(e)
        sys.exit(1)


@main.command()
@click.argument("bucket_name")
def build_latest_docs(bucket_name: str) -> None:
    verify()
    credentials, project_id = docuploader.credentials.find(credentials_file="")
    storage_client = storage.Client(project=project_id, credentials=credentials)
    only_latest = True

    try:
        generate.build_all_docs(bucket_name, storage_client, only_latest)
    except Exception as e:
        log.error(e)
        sys.exit(1)


@main.command()
@click.argument("bucket_name")
@click.argument("object_name")
def build_one_doc(bucket_name: str, object_name: str) -> None:
    verify()
    credentials, project_id = docuploader.credentials.find(credentials_file="")
    storage_client = storage.Client(project=project_id, credentials=credentials)

    try:
        generate.build_one_doc(bucket_name, object_name, storage_client)
    except Exception as e:
        log.error(e)
        sys.exit(1)


@main.command()
@click.argument("bucket_name")
@click.argument("language")
def build_language_docs(bucket_name: str, language: str) -> None:
    verify()
    credentials, project_id = docuploader.credentials.find(credentials_file="")
    storage_client = storage.Client(project=project_id, credentials=credentials)

    try:
        generate.build_language_docs(bucket_name, language, storage_client)
    except Exception as e:
        log.error(e)
        sys.exit(1)


@main.command()
@click.argument("bucket_name")
@click.argument("language")
def build_latest_language_docs(bucket_name: str, language: str) -> None:
    verify()
    credentials, project_id = docuploader.credentials.find(credentials_file="")
    storage_client = storage.Client(project=project_id, credentials=credentials)
    only_latest = True

    try:
        generate.build_language_docs(bucket_name, language, storage_client, only_latest)
    except Exception as e:
        log.error(e)
        sys.exit(1)


@main.command()
@click.argument("input_path")
def build_local_doc(input_path: str) -> None:
    try:
        local_generate.build_local_doc(input_path)
    except Exception as e:
        log.error(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
