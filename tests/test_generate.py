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

import os
import pathlib
import shutil
import tempfile
import unittest

from docuploader import shell, tar
from docuploader.protos import metadata_pb2
from google.cloud import storage
from google.oauth2 import service_account
import pytest

from docpipeline import generate


@pytest.fixture
def yaml_dir(tmpdir):
    shutil.copytree("testdata", tmpdir, dirs_exist_ok=True)
    return tmpdir


@pytest.fixture
def api_dir(tmpdir):
    shutil.copytree("testdata", tmpdir / "api", dirs_exist_ok=True)
    shutil.copy("testdata/docs.metadata", tmpdir)
    return tmpdir


# Initializes key variables needed for the test
def test_init():
    test_bucket = os.environ.get("TEST_BUCKET")
    if not test_bucket:
        pytest.skip("must set TEST_BUCKET")

    credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials:
        pytest.skip("must set GOOGLE_APPLICATION_CREDENTIALS")

    parsed_credentials = service_account.Credentials.from_service_account_file(
        credentials
    )
    storage_client = storage.Client(
        project=parsed_credentials.project_id, credentials=parsed_credentials
    )

    return test_bucket, credentials, storage_client


# Fetches and uploads the blobs used for testing.
def setup_testdata(cwd, storage_client, credentials, test_bucket):
    yaml_blob_name = "docfx-python-doc-pipeline-test-2.1.1.tar.gz"
    html_blob_name = "python-doc-pipeline-test-2.1.1.tar.gz"
    bucket = storage_client.get_bucket(test_bucket)
    yaml_blob = bucket.blob(yaml_blob_name)
    html_blob = bucket.blob(html_blob_name)
    xref_blob = bucket.blob(f"{generate.XREFS_DIR_NAME}/{html_blob_name}.yml")

    # Clean up any previous test data in the bucket.
    if yaml_blob.exists():
        yaml_blob.delete()
    if html_blob.exists():
        html_blob.delete()
    if xref_blob.exists():
        xref_blob.delete()

    start_blobs = list(storage_client.list_blobs(test_bucket))

    # Upload DocFX YAML to test with.
    shell.run(
        [
            "docuploader",
            "upload",
            ".",
            f"--credentials={credentials}",
            f"--staging-bucket={test_bucket}",
            "--destination-prefix=docfx",
        ],
        cwd=cwd,
        hide_output=False,
    )

    # Make sure docuploader succeeded.
    assert (
        len(list(storage_client.list_blobs(test_bucket))) == len(start_blobs) + 1
    ), "should create 1 new YAML blob"

    return bucket, yaml_blob, html_blob


# Call generate.build_new_docs and assert a new tarball is uploaded.
def run_generate(storage_client, credentials, test_bucket):
    start_blobs = list(storage_client.list_blobs(test_bucket))

    # Generate!
    try:
        generate.build_new_docs(test_bucket, credentials)
    except Exception as e:
        pytest.fail(f"build_new_docs raised an exception: {e}")

    # Verify the results.
    # Expect 2 more files: an output blob and an output xref file.
    blobs = list(storage_client.list_blobs(test_bucket))
    assert len(blobs) == len(start_blobs) + 2


# Simple verification of the content
def verify_content(html_blob, tmpdir):
    assert html_blob.exists()

    tar_path = tmpdir.join("out.tgz")
    html_blob.download_to_filename(tar_path)
    tar.decompress(tar_path, tmpdir)
    assert tmpdir.join("docs.metadata").isfile()

    # Check _rootPath and docs.metadata parsing worked.
    toc_file_path = tmpdir.join("_toc.yaml")
    assert toc_file_path.isfile()
    got_text = toc_file_path.read_text("utf-8")
    # See testdata/docs.metadata.
    assert "/python/docs/reference/doc-pipeline-test/latest" in got_text

    # Check xrefmap.yml was created.
    xref_path = tmpdir.join("xrefmap.yml")
    assert xref_path.isfile()
    got_text = xref_path.read_text("utf-8")
    assert got_text.startswith(
        "### YamlMime:XRefMap\nbaseUrl: https://cloud.google.com"
    )

    # Check the template worked.
    html_file_path = tmpdir.join("google.api.customhttppattern.html")
    assert html_file_path.isfile()
    got_text = html_file_path.read_text("utf-8")
    assert "devsite" in got_text
    assert "/python/_book.yaml" in got_text

    # Check the manifest.json was not included.
    manifest_path = tmpdir.join("manifest.json")
    assert not manifest_path.exists(), "manifest.json should not be included"


def test_apidir(api_dir, tmpdir):
    test_bucket, credentials, storage_client = test_init()

    bucket, yaml_blob, html_blob = setup_testdata(
        api_dir, storage_client, credentials, test_bucket
    )

    # Test for api directory content
    run_generate(storage_client, credentials, test_bucket)

    verify_content(html_blob, tmpdir)


def test_setup_docfx(yaml_dir):
    test_bucket, credentials, storage_client = test_init()

    bucket, yaml_blob, html_blob = setup_testdata(
        yaml_dir, storage_client, credentials, test_bucket
    )

    xrefs = ["xrefs/test.yml"]

    tmp_path = pathlib.Path(tempfile.TemporaryDirectory(prefix="doc-pipeline.").name)
    metadata_path, metadata = generate.setup_docfx(tmp_path, yaml_blob, xrefs)

    docfx_json_file = tmp_path.joinpath("docfx.json")
    assert docfx_json_file.exists()
    with open(docfx_json_file) as w:
        got_text = w.read()
        assert "/python/docs/reference/doc-pipeline-test/latest" in got_text
        assert xrefs[0] in got_text

    assert metadata_path.exists()
    assert metadata.name == "doc-pipeline-test"


def test_generate(yaml_dir, tmpdir):
    test_bucket, credentials, storage_client = test_init()

    bucket, yaml_blob, html_blob = setup_testdata(
        yaml_dir, storage_client, credentials, test_bucket
    )

    # Test for non-api directory content
    run_generate(storage_client, credentials, test_bucket)

    verify_content(html_blob, tmpdir)

    # Ensure xref file was properly uploaded. Also ensure download_xrefs gets
    # the right content.
    xrefs, xref_dir = generate.download_xrefs(storage_client, test_bucket)
    assert len(xrefs) == 1
    assert xrefs[0].endswith("python-doc-pipeline-test-2.1.1.tar.gz.yml")
    assert xref_dir.name == generate.XREFS_DIR_NAME

    # Force regeneration and verify the timestamp is different.
    html_blob = bucket.get_blob(html_blob.name)
    t1 = html_blob.updated
    generate.build_all_docs(test_bucket, credentials)
    html_blob = bucket.get_blob(html_blob.name)
    t2 = html_blob.updated
    assert t1 != t2

    # Force regeneration of a single doc and verify timestamp.
    generate.build_one_doc(test_bucket, yaml_blob.name, credentials)
    html_blob = bucket.get_blob(html_blob.name)
    t3 = html_blob.updated
    assert t2 != t3

    # Force generation of Python docs and verify timestamp
    language = "python"
    generate.build_language_docs(test_bucket, language, credentials)
    html_blob = bucket.get_blob(html_blob.name)
    t4 = html_blob.updated
    assert t3 != t4

    # Force generation of Go docs, verify timestamp does not change
    language = "go"
    generate.build_language_docs(test_bucket, language, credentials)
    html_blob = bucket.get_blob(html_blob.name)
    t5 = html_blob.updated
    assert t4 == t5


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
    generate.add_prettyprint(tmp_path)
    for file in files:
        with open(tmp_path.joinpath(file["name"])) as f:
            got = f.read()
            assert got == file["want"]


class TestGenerate(unittest.TestCase):
    def test_format_docfx_json(self):
        self.maxDiff = None
        metadata = metadata_pb2.Metadata()
        metadata.name = "doc-pipeline"
        metadata.xrefs.extend(["one.yml", "two.yml"])
        metadata.xref_services.extend(["one.google.com", "two.google.com"])
        metadata.language = "python"

        want = """
{
  "build": {
    "content": [
      {
        "files": ["**/*.yml", "**/*.md"],
        "src": "obj/api"
      }
    ],
    "globalMetadata": {
      "_appTitle": "doc-pipeline",
      "_disableContribution": true,
      "_appFooter": " ",
      "_disableNavbar": true,
      "_disableBreadcrumb": true,
      "_enableSearch": false,
      "_disableToc": true,
      "_disableSideFilter": true,
      "_disableAffix": true,
      "_disableFooter": true,
      "_rootPath": "/python/docs/reference/doc-pipeline/latest",
      "_projectPath": "/python/"
    },
    "overwrite": [
      "obj/examples/*.md"
    ],
    "dest": "site",
    "xref": ["one.yml", "two.yml"],
    "xrefService": ["one.google.com", "two.google.com"],
  }
}
"""
        got = generate.format_docfx_json(metadata)

        self.assertMultiLineEqual(got, want)
