#!/usr/bin/env bash
# Copyright 2021 Google LLC
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

if ! [[ "$BLOB_TO_DELETE" =~ ^gs:\/\/[^/]+\/.+$ ]]; then
  echo "BLOB_TO_DELETE ($BLOB_TO_DELETE) must be of the form gs://my-bucket/my-blob"
  exit 1
fi

MATCHING_BLOBS=$(gsutil ls "$BLOB_TO_DELETE")
NUM_BLOBS=$(echo "$MATCHING_BLOBS" | wc -l)

if [ $NUM_BLOBS -gt 1 ]; then
  echo "$BLOB_TO_DELETE matched $NUM_BLOBS blobs, expected to match only 1"
  exit 2
fi

gsutil rm "$BLOB_TO_DELETE"
