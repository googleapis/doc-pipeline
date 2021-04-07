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
from bs4 import BeautifulSoup


@pytest.fixture
def prepare_java_testdata(tmpdir):
    shutil.copy("testdata/mock-java-original-toc.yml", tmpdir)
    shutil.copy("testdata/mock-java-updated-toc.yml", tmpdir)
    return tmpdir


@pytest.fixture
def prepare_html_testdata(tmpdir):
    shutil.copytree("testdata", tmpdir, dirs_exist_ok=True)
    return tmpdir


def test_prepare_java_toc(prepare_java_testdata):
    tmp_path = pathlib.Path(prepare_java_testdata)
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
            "name": "should_update.html",
            "input": '<code class="lang-cs">hello</code>',
            "want": '<code class="lang-cs prettyprint">hello</code>',
        },
        {
            "name": "should_not_update.html",
            "input": '<code class="prettyprint">hello</code>',
            "want": '<code class="prettyprint">hello</code>',
        },
        {
            "name": "nothing.yml",
            "input": "nothing to do",
            "want": "nothing to do",
        },
    ]

    for file in files:
        tmp_file = tmp_path.joinpath(file["name"])
        # write input to file
        with open(tmp_file, "w") as f:
            f.write(file["input"])

        # add prettyprint
        soup = BeautifulSoup(open(tmp_file), "html.parser")
        prepare.add_prettyprint(soup)
        with open(tmp_file, "w") as f:
            f.write(str(soup))

    # verify 'input' now matches 'want'
    for file in files:
        with open(tmp_path.joinpath(file["name"])) as f:
            got = f.read()
            assert got == file["want"]


def test_addadd_inherited_members_drowdown():
    tmp_dir = tempfile.TemporaryDirectory(prefix="doc-pipeline.prettyprint.")
    tmp_path = pathlib.Path(tmp_dir.name)

    files = [
        {
            "name": "should_update.html",
            "input": '<div class="inheritedMembers">\n  <h5>Inherited Members</h5>\n  <div>\n    <span class="xref">System.Object.ToString()</span>\n  </div>\n</div>',
            "want": '<devsite-expandable><div class="inheritedMembers">\n<h5 class="showalways">Inherited Members</h5>\n<div>\n<span class="xref">System.Object.ToString()</span>\n</div>\n</div></devsite-expandable>',
        },
        {
            "name": "should_not_update.html",
            "input": '<div class="Inheritance">\n  <h5>inheritance</h5>\n  <span><span class="xref">Google.Protobuf.IMessage</span></span>\n</div>',
            "want": '<div class="Inheritance">\n<h5>inheritance</h5>\n<span><span class="xref">Google.Protobuf.IMessage</span></span>\n</div>',
        },
        {
            "name": "nothing.yml",
            "input": "",
            "want": "",
        },
    ]

    for file in files:
        tmp_file = tmp_path.joinpath(file["name"])
        # write input to file
        with open(tmp_file, "w") as f:
            f.write(file["input"])

        # add dropdown
        soup = BeautifulSoup(open(tmp_file), "html.parser")
        prepare.add_inherited_members_drowdown(soup)
        with open(tmp_file, "w") as f:
            f.write(str(soup))

    # verify 'input' now matches 'want'
    for file in files:
        with open(tmp_path.joinpath(file["name"])) as f:
            got = f.read()
            assert got == file["want"]


def test_prepare_html(prepare_html_testdata):
    tmp_path = pathlib.Path(prepare_html_testdata)
    original_dir = tmp_path.joinpath("original_prepare_html")
    updated_dir = tmp_path.joinpath("updated_prepare_html")

    html_files = [
        "dotnet-Google.Cloud.Asset.V1.BatchGetAssetsHistoryRequest.html",
        "go-pkg-readme.html",
        "java-com.google.cloud.speech.v1.SpeechClient.html",
    ]

    for file in html_files:
        # files should be different before
        assert (
            filecmp.cmp(
                original_dir.joinpath(file), updated_dir.joinpath(file), shallow=False
            )
        ) is False

    prepare.prepare_html(original_dir)

    for file in html_files:
        # files should be the same after
        assert (
            filecmp.cmp(
                original_dir.joinpath(file), updated_dir.joinpath(file), shallow=False
            )
        ) is True
