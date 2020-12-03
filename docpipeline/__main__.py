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
from docuploader import credentials, log

from docpipeline import generate


# The docuploader logger is initialized as "docuploader"; change it to docpipeline.
log.logger = logging.getLogger("docpipeline")

REQUIRED_CMDS = ["docfx", "docuploader"]

VERSION = "0.0.0-dev"


def verify(credentials):
    if not credentials:
        log.error(
            (
                "You need credentials to run this! Specify --credentials on",
                "the command line.",
            )
        )
        return sys.exit(1)

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
@click.option(
    "--credentials",
    default=credentials.find(),
    help="Path to the credentials file to use for Google Cloud Storage.",
)
def build_new_docs(bucket_name, credentials):
    verify(credentials)

    try:
        generate.build_new_docs(bucket_name, credentials)
    except Exception as e:
        log.error(e)
        sys.exit(1)


@main.command()
@click.argument("bucket_name")
@click.option(
    "--credentials",
    default=credentials.find(),
    help="Path to the credentials file to use for Google Cloud Storage.",
)
def build_all_docs(bucket_name, credentials):
    verify(credentials)

    try:
        generate.build_all_docs(bucket_name, credentials)
    except Exception as e:
        log.error(e)
        sys.exit(1)


@main.command()
@click.argument("bucket_name")
@click.argument("object_name")
@click.option(
    "--credentials",
    default=credentials.find(),
    help="Path to the credentials file to use for Google Cloud Storage.",
)
def build_one_doc(bucket_name, object_name, credentials):
    verify(credentials)

    try:
        generate.build_one_doc(bucket_name, object_name, credentials)
    except Exception as e:
        log.error(e)
        sys.exit(1)


@main.command()
@click.argument("bucket_name")
@click.argument("language")
@click.option(
    "--credentials",
    default=credentials.find(),
    help="Path to the credentials file to use for Google Cloud Storage.",
)
def build_language_docs(bucket_name, language, credentials):
    verify(credentials)

    try:
        generate.build_language_docs(bucket_name, language, credentials)
    except Exception as e:
        log.error(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
