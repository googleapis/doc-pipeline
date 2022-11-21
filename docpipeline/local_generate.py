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

import pathlib
import shutil

from docuploader import log
from docpipeline import generate


def process_local_blob(blob):
    is_bucket = False
    tmp_path, metadata, site_path = generate.build_and_format(blob, is_bucket)

    # For local generation
    output_path = blob.joinpath(metadata.name)
    if output_path.exists():
        log.info(f"deleting existing directory: {output_path}")
        shutil.rmtree(output_path)
    shutil.copytree(site_path, output_path, dirs_exist_ok=True)
    shutil.rmtree(tmp_path)

    log.success(f"Done with {metadata.name}!")


def build_local_doc(input_path):
    log.info("Building docs locally...")
    log.info("Let's build some docs!")

    input_path = pathlib.Path(input_path)
    if not input_path.exists():
        raise Exception(f"{input_path} is not a valid directory path!")

    process_local_blob(input_path)
