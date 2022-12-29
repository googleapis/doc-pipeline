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


def build_local_doc(input_dir: pathlib.Path, output_dir: pathlib.Path):
    """Builds the YAML in input_path and stores the result in output_path."""

    log.info("Building docs locally...")
    log.info("Let's build some docs!")

    if not input_dir.exists():
        raise Exception(f"{input_dir} is not a valid directory path!")

    is_bucket = False
    tmp_path, metadata, site_path = generate.build_and_format(input_dir, is_bucket)

    if output_dir.exists():
        log.info(f"deleting existing directory: {output_dir}")
        shutil.rmtree(output_dir)
    shutil.copytree(site_path, output_dir, dirs_exist_ok=True)
    shutil.rmtree(tmp_path)

    log.success(f"Done with {metadata.name}!")
