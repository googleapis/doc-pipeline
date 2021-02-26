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


def build_local_doc(input_path):
    log.info("Building docs locally...")
    log.info("Let's build some docs!")

    # Clone doc-templates
    templates_dir, devsite_template = generate.setup_templates()

    input_path = pathlib.Path(input_path)
    if not input_path.exists():
        raise Exception(f"{input_path} is not a valid directory path!")

    generate.process_blob(input_path, "", devsite_template)

    shutil.rmtree(templates_dir)
