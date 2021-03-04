# Copyright 2021 Google LLC
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

from docpipeline import prepare
import shutil
import filecmp
import yaml
import pytest
import pathlib
import tempfile


@pytest.fixture
def testdata(tmpdir):
    shutil.copytree("testdata", tmpdir, dirs_exist_ok=True)
    shutil.copy("testdata/mock-java-original-toc.yml", tmpdir)
    shutil.copy("testdata/mock-java-updated-toc.yml", tmpdir)
    return tmpdir


def test_prepare_java_toc(testdata):
    tmp_path = pathlib.Path(testdata)
    original_toc = tmp_path.joinpath("mock-java-original-toc.yml")
    updated_toc = tmp_path.joinpath("mock-java-updated-toc.yml")

    # files should be different before
    assert (filecmp.cmp(original_toc, updated_toc, shallow=False)) is False

    prepare.prepare_java_toc(original_toc, "google-cloud-library")

    # files should be the same after
    assert (filecmp.cmp(original_toc, updated_toc, shallow=False)) is True

    with open(original_toc, "r") as stream:
        try:
            yaml.safe_load(stream)
        except yaml.YAMLError:
            pytest.fail(f"Unable to parse YAML: {original_toc}")


def test_add_prettyprint():
    tmp_dir = tempfile.TemporaryDirectory(prefix="doc-pipeline.prettyprint.")
    tmp_path = pathlib.Path(tmp_dir.name)

    files = [
        {
            "name": "one.html",
            "input": '<code class="lang-cs">hello</code>',
            "want": '<code class="prettyprint lang-cs">hello</code>',
        },
        {
            "name": "two.html",
            "input": '<code class="prettyprint">hello</code>',
            "want": '<code class="prettyprint">hello</code>',
        },
        {
            "name": "three.yml",
            "input": "nothing to do",
            "want": "nothing to do",
        },
    ]

    for file in files:
        with open(tmp_path.joinpath(file["name"]), "w") as f:
            f.write(file["input"])

    prepare.add_prettyprint(tmp_path)

    for file in files:
        with open(tmp_path.joinpath(file["name"])) as f:
            got = f.read()
            assert got == file["want"]
