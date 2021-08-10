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

import io
import os
import pathlib
import shutil
import tempfile
import unittest

import docuploader.credentials
from docuploader import shell, tar
from docuploader.protos import metadata_pb2
from google.cloud import storage
import pytest

from docpipeline import generate, local_generate


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

    credentials, project_id = docuploader.credentials.find(credentials_file="")

    storage_client = storage.Client(project=project_id, credentials=credentials)

    return test_bucket, storage_client


def upload_yaml(cwd, test_bucket):
    # Upload DocFX YAML to test with.
    shell.run(
        [
            "docuploader",
            "upload",
            ".",
            f"--staging-bucket={test_bucket}",
            "--destination-prefix=docfx",
        ],
        cwd=cwd,
        hide_output=False,
    )


# Fetches and uploads the blobs used for testing.
def setup_testdata(cwd, storage_client, test_bucket):
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

    upload_yaml(cwd, test_bucket)

    # Make sure docuploader succeeded.
    assert (
        len(list(storage_client.list_blobs(test_bucket))) == len(start_blobs) + 1
    ), "should create 1 new YAML blob"

    return bucket, yaml_blob, html_blob


# Call generate.build_new_docs and assert a new tarball is uploaded.
def run_generate(storage_client, test_bucket):
    start_blobs = list(storage_client.list_blobs(test_bucket))

    # Generate!
    try:
        generate.build_new_docs(test_bucket, storage_client)
    except Exception as e:
        pytest.fail(f"build_new_docs raised an exception: {e}")

    # Verify the results.
    # Expect 2 more files: an output blob and an output xref file.
    blobs = list(storage_client.list_blobs(test_bucket))
    assert len(blobs) == len(start_blobs) + 2


def run_local_generate(local_path):

    # Test with invalid path given, must throw exception
    try:
        local_generate.build_local_doc(local_path.basename[1:])
    except Exception:
        pass
    else:
        pytest.fail("build_local_doc is attempting to generate on invalid input path")

    # Generate!
    try:
        local_generate.build_local_doc(local_path)
    except Exception as e:
        pytest.fail(f"build_local_doc raised an exception: {e}")

    # Verify the results.
    # Expect a local directory of pages to be made from building locally
    output_path = local_path.join("doc-pipeline-test")
    assert output_path.isdir()

    # Return the directory containing locally generated docs
    return output_path


def verify_template_content(tmpdir):

    assert tmpdir.join("docs.metadata").isfile()

    # Check _rootPath and docs.metadata parsing worked.
    toc_file_path = tmpdir.join("_toc.yaml")
    assert toc_file_path.isfile()
    got_text = toc_file_path.read_text("utf-8")
    # See testdata/docs.metadata.
    assert "/python/docs/reference/doc-pipeline-test/latest" in got_text

    # Check the template worked.
    html_file_path = tmpdir.join("google.api.customhttppattern.html")
    assert html_file_path.isfile()
    got_text = html_file_path.read_text("utf-8")
    assert "devsite" in got_text
    assert "/python/_book.yaml" in got_text

    # Check the manifest.json was not included.
    manifest_path = tmpdir.join("manifest.json")
    assert not manifest_path.exists(), "manifest.json should not be included"


# Simple verification of the content
def verify_content(html_blob, tmpdir):
    assert html_blob.exists()

    tar_path = tmpdir.join("out.tgz")
    html_blob.download_to_filename(tar_path)
    tar.decompress(tar_path, tmpdir)

    verify_template_content(tmpdir)

    # Check xrefmap.yml was created.
    xref_path = tmpdir.join("xrefmap.yml")
    assert xref_path.isfile()
    got_text = xref_path.read_text("utf-8")
    assert got_text.startswith(
        "### YamlMime:XRefMap\nbaseUrl: https://cloud.google.com"
    )


def test_apidir(api_dir, tmpdir):
    test_bucket, storage_client = test_init()

    bucket, yaml_blob, html_blob = setup_testdata(api_dir, storage_client, test_bucket)

    # Test for api directory content
    run_generate(storage_client, test_bucket)

    verify_content(html_blob, tmpdir)


def test_setup_docfx(yaml_dir):
    test_bucket, storage_client = test_init()

    bucket, yaml_blob, html_blob = setup_testdata(yaml_dir, storage_client, test_bucket)

    tmp_path = pathlib.Path(tempfile.TemporaryDirectory(prefix="doc-pipeline.").name)

    api_path = decompress_path = tmp_path.joinpath("obj/api")

    api_path.mkdir(parents=True, exist_ok=True)

    metadata_path, metadata = generate.setup_bucket_docfx(
        tmp_path, api_path, decompress_path, yaml_blob
    )

    docfx_json_file = tmp_path.joinpath("docfx.json")
    assert docfx_json_file.exists()
    with open(docfx_json_file) as w:
        got_text = w.read()
        assert "/python/docs/reference/doc-pipeline-test/latest" in got_text

    assert metadata_path.exists()
    assert metadata.name == "doc-pipeline-test"


def test_generate(yaml_dir, tmpdir):
    test_bucket, storage_client = test_init()

    bucket, yaml_blob, html_blob = setup_testdata(yaml_dir, storage_client, test_bucket)

    # Test for non-api directory content
    run_generate(storage_client, test_bucket)

    verify_content(html_blob, tmpdir)

    # Ensure xref file was properly uploaded. Also ensure download_xrefs gets
    # the right content.
    path = generate.get_xref(
        "devsite://python/doc-pipeline-test", bucket, pathlib.Path(tmpdir)
    )
    assert path != ""
    assert pathlib.Path(path).exists()

    # Force regeneration and verify the timestamp is different.
    html_blob = bucket.get_blob(html_blob.name)
    t1 = html_blob.updated
    generate.build_all_docs(test_bucket, storage_client)
    html_blob = bucket.get_blob(html_blob.name)
    t2 = html_blob.updated
    assert t1 != t2

    # Force regeneration of a single doc and verify timestamp.
    generate.build_one_doc(test_bucket, yaml_blob.name, storage_client)
    html_blob = bucket.get_blob(html_blob.name)
    t3 = html_blob.updated
    assert t2 != t3

    # Force generation of Python docs and verify timestamp.
    language = "python"
    generate.build_language_docs(test_bucket, language, storage_client)
    html_blob = bucket.get_blob(html_blob.name)
    t4 = html_blob.updated
    assert t3 != t4

    # Force generation of Go docs, verify Python HTML timestamp does not change.
    language = "go"
    generate.build_language_docs(test_bucket, language, storage_client)
    html_blob = bucket.get_blob(html_blob.name)
    t5 = html_blob.updated
    assert t4 == t5

    # Force regeneration of a single doc with old YAML and verify
    # timestamp does not change.
    generate.build_new_docs(test_bucket, storage_client)
    html_blob = bucket.get_blob(html_blob.name)
    t6 = html_blob.updated
    assert t5 == t6

    # Update the YAML, build new docs, and verify the HTML was updated.
    upload_yaml(yaml_dir, test_bucket)
    generate.build_new_docs(test_bucket, storage_client)
    html_blob = bucket.get_blob(html_blob.name)
    t7 = html_blob.updated
    assert t6 != t7


def test_local_generate(yaml_dir, tmpdir):
    # Test for local generation content
    output_path = run_local_generate(yaml_dir)

    verify_template_content(output_path)


@pytest.fixture(scope="module")
def xref_test_blobs():
    test_bucket, storage_client = test_init()
    bucket = storage_client.get_bucket(test_bucket)

    # Remove all existing test xref blobs.
    blobs_to_delete = bucket.list_blobs(prefix="xrefs/")
    for blob in blobs_to_delete:
        blob.delete()

    blobs_to_create = [
        "xrefs/go-unused-v0.0.1.tar.gz.yml",
        "xrefs/dotnet-my-pkg-1.0.0.tar.gz.yml",
        "xrefs/dotnet-my-pkg-v1.1.0.tar.gz.yml",
        "xrefs/dotnet-my-pkg-2.0.0-SNAPSHOT.tar.gz.yml",
        "xrefs/dotnet-my-pkg-2.0.0.tar.gz.yml",
        "xrefs/dotnet-my-pkg-unused-3.0.0.tar.gz.yml",
        "xrefs/dotnet-v-pkg-v3.0.0.tar.gz.yml",
        "xrefs/dotnet-v-pkg-v4.0.0.tar.gz.yml",
    ]
    for b in blobs_to_create:
        blob = bucket.blob(b)
        if not blob.exists():
            blob.upload_from_string("unused")


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ("http://google.com", "http://google.com"),
        ("devsite://does/not/exist", ""),
        ("devsite://does/not/exist@latest", ""),
        ("devsite://dotnet/my-pkg@1.0.0", "xrefs/dotnet-my-pkg-1.0.0.tar.gz.yml"),
        ("devsite://dotnet/my-pkg", "xrefs/dotnet-my-pkg-2.0.0.tar.gz.yml"),
        ("devsite://dotnet/my-pkg@latest", "xrefs/dotnet-my-pkg-2.0.0.tar.gz.yml"),
        ("devsite://dotnet/v-pkg@latest", "xrefs/dotnet-v-pkg-v4.0.0.tar.gz.yml"),
    ],
)
def test_get_xref(test_input, expected, tmpdir, xref_test_blobs):
    test_bucket, storage_client = test_init()
    bucket = storage_client.get_bucket(test_bucket)

    tmpdir = pathlib.Path(tmpdir)
    got = generate.get_xref(test_input, bucket, tmpdir)

    if ":" in expected:
        assert got == expected
        return
    if expected == "":
        assert got == expected
        return
    expected_path = tmpdir.joinpath(expected)
    assert str(expected_path) == got
    assert expected_path.exists(), f"expected {expected_path} to exist"


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

    def test_format_docfx_json_help(self):
        self.maxDiff = None
        metadata = metadata_pb2.Metadata()
        metadata.name = "help"
        metadata.language = "dotnet"
        metadata.stem = "/dotnet/is/awesome"

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
      "_appTitle": "help",
      "_disableContribution": true,
      "_appFooter": " ",
      "_disableNavbar": true,
      "_disableBreadcrumb": true,
      "_enableSearch": false,
      "_disableToc": true,
      "_disableSideFilter": true,
      "_disableAffix": true,
      "_disableFooter": true,
      "_rootPath": "/dotnet/is/awesome",
      "_projectPath": "/dotnet/"
    },
    "overwrite": [
      "obj/examples/*.md"
    ],
    "dest": "site",
    "xref": [],
    "xrefService": [],
  }
}
"""
        got = generate.format_docfx_json(metadata)

        self.assertMultiLineEqual(got, want)

    def test_write_xunit(self):
        want = """<testsuites>
  <testsuite tests="2" failures="1" name="github.com/googleapis/doc-pipeline/generate">
    <testcase classname="build" name="hello" />
    <testcase classname="build" name="goodbye">
      <failure message="Failed" />
    </testcase>
  </testsuite>
</testsuites>"""
        f = io.StringIO()
        successes = ["hello"]
        failures = ["goodbye"]
        generate.write_xunit(f, successes, failures)
        got = f.getvalue()
        self.assertMultiLineEqual(want, got)


@pytest.mark.parametrize(
    "lang,name,stem,expected",
    [
        ("go", "help", "", "/go/docs/reference/help"),
        ("go", "other", "", "/go/docs/reference/other/latest"),
        (
            "python",
            "other2",
            "",
            "/python/docs/reference/other2/latest",
        ),
        ("go", "other", "/foo/bar", "/foo/bar/latest"),
    ],
)
def test_get_path(lang, name, stem, expected):
    metadata = metadata_pb2.Metadata()
    metadata.language = lang
    metadata.name = name
    metadata.stem = stem
    got = generate.get_path(metadata)
    assert got == expected
