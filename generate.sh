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

set -e

if [ -z "$SOURCE_BUCKET" ]; then
    echo "Must set SOURCE_BUCKET"
    exit 1
fi

# Add the path where docuploader gets installed to PATH.
export PATH=$PATH:${HOME}/.local/bin

python3 -m pip install .

if [ "$FORCE_GENERATE_ALL" == "true" ]; then
    python3 docpipeline/__main__.py build-all-docs $SOURCE_BUCKET
elif [ -n "$SOURCE_BLOB" ]; then
    python3 docpipeline/__main__.py build-one-doc $SOURCE_BUCKET $SOURCE_BLOB
else
    python3 docpipeline/__main__.py build-new-docs $SOURCE_BUCKET
fi
