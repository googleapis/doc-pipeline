#!/usr/bin/env bash
# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# TODO: Write a Python script to build the docs.
# * List all tarballs and find docfx-* ones.
# * If FORCE_GENERATE_ALL env var is set to true, regenerate all.
# * If SOURCE_FILE_GS_URI is set, force regeneration for that file.
# * For each relevant tarball:
#   1. Create a temp directory, and an obj directory inside.
#   2. Unpack the tarball inside the obj directory.
#   3. Create a docfx.json file (using title=package name and
#      _rootPath=serving path).
#   4. docfx build -t ...
#   5. Move to the output directory, copy in obj/docs.metadata, and call
#      docuploader upload.

set -e

# Now it's only making sure `docfx --help` works
docfx --help
