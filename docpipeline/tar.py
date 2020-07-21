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

"""Handles decompressing tarballs."""

import subprocess

from docuploader import shell


def decompress(archive: str, destination: str) -> subprocess.CompletedProcess:
    """Decompress the given tarfile to the destination."""
    # Note: we don't use the stdlib's "tarfile" module for performance reasons.
    # While it can handle creating tarfiles, its not as efficient on large
    # numbers of files like the tar command.
    return shell.run(
        [
            "tar",
            "--extract",
            f"--directory={destination}",
            f"--file={archive}",
            "--gzip",
            "--verbose",
        ],
        hide_output=True,
    )
