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

import setuptools


dependencies = [
    "click",
    "google-cloud-storage<2.15.1",
    "gcp-docuploader",
    "semver",
    "six",
    "protobuf==5.29.6",  # DO NOT UPGRADE. Keep pinned to 3.20.3.
]

packages = setuptools.find_packages()
scripts = ["docuploader=docuploader.__main__:main"]

setuptools.setup(
    name="gcp-doc-pipeline",
    version="0.0.1",
    description="DocFX YAML to HTML pipeline",
    url="http://github.com/googleapis/doc-pipeline",
    author="Google LLC",
    author_email="noreply@google.com",
    license="Apache 2",
    packages=packages,
    install_requires=dependencies,
    zip_safe=False,
)
