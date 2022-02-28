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
set -x

# Add the path where docuploader gets installed to PATH.
export PATH=$PATH:${HOME}/.local/bin

python3 -m pip install .

if [ -n "$INPUT" ]; then
  python3 docpipeline/__main__.py build-local-doc $INPUT
  exit
fi

if [ -z "$SOURCE_BUCKET" ]; then
  echo "Must set SOURCE_BUCKET"
  exit 1
fi

# Don't exit immediately so we can send logs to flakybot.
set +e
exit_code=0

if [ "$FORCE_GENERATE_ALL" == "true" ]; then
    if [ -n "$LANGUAGE" ]; then
        python3 docpipeline/__main__.py build-language-docs $SOURCE_BUCKET $LANGUAGE
        exit_code=$?
    else
        python3 docpipeline/__main__.py build-all-docs $SOURCE_BUCKET
        exit_code=$?
    fi
elif [ "$FORCE_GENERATE_LATEST" == "true" ]; then
    if [ -n "$LANGUAGE" ]; then
        python3 docpipeline/__main__.py build-latest-language-docs $SOURCE_BUCKET $LANGUAGE
        exit_code=$?
    else
        python3 docpipeline/__main__.py build-latest-docs $SOURCE_BUCKET
        exit_code=$?
    fi
elif [ -n "$SOURCE_BLOB" ]; then
    python3 docpipeline/__main__.py build-one-doc $SOURCE_BUCKET $SOURCE_BLOB
    exit_code=$?
else
    python3 docpipeline/__main__.py build-new-docs $SOURCE_BUCKET
    exit_code=$?
fi

if [[ $KOKORO_BUILD_ARTIFACTS_SUBDIR = *"generate-prod"* ]] || \
   [[ $KOKORO_BUILD_ARTIFACTS_SUBDIR = *"generate-staging"* ]]; then
  chmod +x $KOKORO_GFILE_DIR/linux_amd64/flakybot
  $KOKORO_GFILE_DIR/linux_amd64/flakybot
fi

exit $exit_code
