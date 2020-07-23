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

if [ -z "$TEST_BUCKET" ]; then
    echo "Must set TEST_BUCKET"
    exit 1
fi

# Disable buffering, so that the logs stream through.
export PYTHONUNBUFFERED=1

# If running locally, copy a service account file to
# /dev/shm/73713_docuploader_service_account before calling ci/trampoline_v2.sh.
export GOOGLE_APPLICATION_CREDENTIALS=$KOKORO_KEYSTORE_DIR/73713_docuploader_service_account

# Add the path where pip installs commands to PATH.
export PATH=$PATH:${HOME}/.local/bin

python3 -m pip install -e .
python3 -m pip install flake8 black pytest pytest-cov

black --check docpipeline tests
flake8 docpipeline tests

pytest --cov-report term-missing --cov docpipeline tests
