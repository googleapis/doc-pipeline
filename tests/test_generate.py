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

import datetime
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
from parameterized import parameterized
import pytest

from docpipeline import generate, local_generate


@pytest.fixture
def yaml_dir(tmpdir) -> pathlib.Path:
    shutil.copytree("testdata/go", tmpdir, dirs_exist_ok=True)
    return pathlib.Path(tmpdir)


@pytest.fixture
def api_dir(tmpdir) -> pathlib.Path:
    shutil.copytree("testdata/go", tmpdir / "api", dirs_exist_ok=True)
    shutil.copy("testdata/go/docs.metadata", tmpdir)
    return pathlib.Path(tmpdir)


def swap_file(parent_dir, file1, file2):
    temp_file = parent_dir / (file1.name + "_temp")
    shutil.copy(file1, temp_file)
    shutil.copy(file2, file1)
    shutil.copy(temp_file, file2)
    os.remove(temp_file)


# Initializes key variables needed for the test
def init_test():
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
    # Clean up any previous test data that is more than 24 hours old.
    blobs = list(storage_client.list_blobs(test_bucket))
    blobs_to_remove = [
        blob
        for blob in blobs
        if (datetime.datetime.now(tz=datetime.timezone.utc) - blob.time_created).days
        > 0
    ]
    for blob_to_remove in blobs_to_remove:
        blob_to_remove.delete()

    yaml_blob_name = "docfx-go-cloud.google.com/go/storage-v1.40.0.tar.gz"
    html_blob_name = "go-cloud.google.com/go/storage-v1.40.0.tar.gz"
    bucket = storage_client.get_bucket(test_bucket)
    yaml_blob = bucket.blob(yaml_blob_name)
    html_blob = bucket.blob(html_blob_name)

    upload_yaml(cwd, test_bucket)

    # Make sure docuploader succeeded.
    assert yaml_blob.exists(), "should create the YAML blob"

    return bucket, yaml_blob, html_blob


# Call generate.build_new_docs and assert a new tarball is uploaded.
def run_generate(storage_client, test_bucket):
    html_blob_name = "go-cloud.google.com/go/storage-v1.40.0.tar.gz"

    # Generate!
    try:
        generate.build_new_docs(test_bucket, storage_client)
    except Exception as e:
        pytest.fail(f"build_new_docs raised an exception: {e}")

    # Verify the results.
    # Expect 2 more files: an output blob and an output xref file.
    bucket = storage_client.get_bucket(test_bucket)
    html_blob = bucket.blob(html_blob_name)
    xref_blob = bucket.blob(f"{generate.XREFS_DIR_NAME}/{html_blob_name}.yml")
    assert html_blob.exists(), "should create the HTML blob"
    assert xref_blob.exists(), "should create the xref blob"


def run_local_generate(local_path):
    # Test with invalid path given, must throw exception
    try:
        local_generate.build_local_doc(local_path.basename[1:], pathlib.Path("unused"))
    except Exception:
        pass
    else:
        pytest.fail("build_local_doc is attempting to generate on invalid input path")

    # Generate!
    output_dir = local_path / "cloud.google.com/go/storage"
    try:
        local_generate.build_local_doc(local_path, output_dir=output_dir)
    except Exception as e:
        pytest.fail(f"build_local_doc raised an exception: {e}")

    # Verify the results.
    # Expect a local directory of pages to be made from building locally
    assert output_dir.is_dir()

    # Return the directory containing locally generated docs
    return output_dir


def verify_template_content(tmpdir):
    assert tmpdir.joinpath("docs.metadata").is_file()

    # Check _rootPath and docs.metadata parsing worked.
    toc_file_path = tmpdir / "_toc.yaml"
    assert toc_file_path.is_file()
    got_text = toc_file_path.read_text("utf-8")
    # See testdata/go/docs.metadata.
    assert "/go/docs/reference/cloud.google.com/go/storage/latest" in got_text

    # Check the template worked.
    html_file_path = tmpdir / "index.html"
    assert html_file_path.is_file()
    got_text = html_file_path.read_text("utf-8")
    assert "devsite" in got_text
    assert (
        "/go/docs/reference/cloud.google.com/go/storage/latest/_book.yaml" in got_text
    )

    # Check the manifest.json was not included.
    manifest_path = tmpdir / "manifest.json"
    assert not manifest_path.exists(), "manifest.json should not be included"


# Simple verification of the content
def verify_content(html_blob, tmpdir):
    assert html_blob.exists()

    tar_path = tmpdir / "out.tgz"
    html_blob.download_to_filename(tar_path)
    tar.decompress(tar_path, tmpdir)

    verify_template_content(tmpdir)

    # Check xrefmap.yml was created.
    xref_path = tmpdir / "xrefmap.yml"
    assert xref_path.is_file()
    got_text = xref_path.read_text("utf-8")
    assert got_text.startswith(
        "### YamlMime:XRefMap\nbaseUrl: https://cloud.google.com"
    )


def test_apidir(api_dir, tmpdir):
    test_bucket, storage_client = init_test()

    bucket, yaml_blob, html_blob = setup_testdata(api_dir, storage_client, test_bucket)

    # Test for api directory content
    run_generate(storage_client, test_bucket)

    verify_content(html_blob, pathlib.Path(tmpdir))


def test_setup_docfx(yaml_dir):
    test_bucket, storage_client = init_test()

    bucket, yaml_blob, html_blob = setup_testdata(yaml_dir, storage_client, test_bucket)

    tmp_path = pathlib.Path(tempfile.TemporaryDirectory(prefix="doc-pipeline.").name)

    api_path = decompress_path = tmp_path / "obj/api"

    api_path.mkdir(parents=True, exist_ok=True)

    metadata_path, metadata = generate.setup_bucket_docfx(
        tmp_path, api_path, decompress_path, yaml_blob
    )

    docfx_json_file = tmp_path / "docfx.json"
    assert docfx_json_file.exists()
    with open(docfx_json_file) as w:
        got_text = w.read()
        assert "/go/docs/reference/cloud.google.com/go/storage/latest" in got_text

    assert metadata_path.exists()
    assert metadata.name == "cloud.google.com/go/storage"


def test_setup_docfx_not_found():
    test_bucket, storage_client = init_test()
    tmp_path = pathlib.Path(tempfile.TemporaryDirectory(prefix="doc-pipeline.").name)
    fake_blob = storage_client.bucket(test_bucket).blob("fake_blob_name")
    with pytest.raises(ValueError):
        generate.setup_bucket_docfx(
            tmp_path,
            pathlib.Path("/unused"),
            pathlib.Path("/unused"),
            fake_blob,
        )


def test_generate(yaml_dir, tmpdir):
    tmpdir = pathlib.Path(tmpdir)
    test_bucket, storage_client = init_test()

    bucket, yaml_blob, html_blob = setup_testdata(yaml_dir, storage_client, test_bucket)

    # Test for non-api directory content
    run_generate(storage_client, test_bucket)

    verify_content(html_blob, tmpdir)

    # Ensure xref file was properly uploaded. Also ensure download_xrefs gets
    # the right content.
    path = generate.get_xref("devsite://go/cloud.google.com/go/storage", bucket, tmpdir)
    assert path != ""
    assert pathlib.Path(path).exists()

    # Force regeneration and verify the timestamp is different.
    html_blob = bucket.get_blob(html_blob.name)
    t1 = html_blob.updated
    generate.build_all_docs(test_bucket, storage_client)
    html_blob = bucket.get_blob(html_blob.name)
    t2 = html_blob.updated
    assert t1 != t2, "HTML is updated"

    # Force regeneration of a single doc and verify timestamp.
    generate.build_one_doc(test_bucket, yaml_blob.name, storage_client)
    html_blob = bucket.get_blob(html_blob.name)
    t3 = html_blob.updated
    assert t2 != t3, "single doc gets updated"

    # Force generation of Go docs and verify timestamp.
    language = "go"
    generate.build_language_docs(test_bucket, language, storage_client)
    html_blob = bucket.get_blob(html_blob.name)
    t4 = html_blob.updated
    assert t3 != t4, "Go docs get updated"

    # Force generation of Python docs, verify Go HTML timestamp does not change.
    language = "python"
    generate.build_language_docs(test_bucket, language, storage_client)
    html_blob = bucket.get_blob(html_blob.name)
    t5 = html_blob.updated
    assert t4 == t5, "Go timestamp doesn't change"

    # Build new docs with unchanged YAML and verify the HTML
    # timestamp does not change.
    generate.build_new_docs(test_bucket, storage_client)
    html_blob = bucket.get_blob(html_blob.name)
    t6 = html_blob.updated
    assert t5 == t6, "same YAML, no updates"

    # Update the YAML, build new docs, and verify the HTML was updated.
    upload_yaml(yaml_dir, test_bucket)
    generate.build_new_docs(test_bucket, storage_client)
    html_blob = bucket.get_blob(html_blob.name)
    t7 = html_blob.updated
    assert t6 != t7, "new YAML, HTML gets updated"

    # Upload new blob, build only latest, and verify only latest is updated.
    new_metadata = "docs.metadata.newer"
    latest_html_blob_name = "go-cloud.google.com/go/storage-v1.40.1.tar.gz"

    # Swap to newer metadata to upload newer version of tarball.
    swap_file(yaml_dir, yaml_dir / "docs.metadata", yaml_dir / new_metadata)
    # Upload newer version of tarball, then switch the metadata back.
    upload_yaml(yaml_dir, test_bucket)
    swap_file(yaml_dir, yaml_dir / "docs.metadata", yaml_dir / new_metadata)

    generate.build_all_docs(test_bucket, storage_client, only_latest=True)

    # Verify old version HTML is not updated.
    html_blob = bucket.get_blob(html_blob.name)
    t8 = html_blob.updated
    assert t7 == t8, "old version was updated after build_all_docs"

    # Verify latest version HTML is updated.
    latest_html_blob = bucket.get_blob(latest_html_blob_name)
    t1_latest = latest_html_blob.updated
    assert t7 != t1_latest, "latest is updated"

    # Force generation of latest Go docs
    language = "go"
    generate.build_language_docs(
        test_bucket, language, storage_client, only_latest=True
    )

    # Verify old version HTML is not updated.
    html_blob = bucket.get_blob(html_blob.name)
    t9 = html_blob.updated
    assert t8 == t9, "old version was updated after build_language_docs"

    # Verify latest version HTML is updated.
    latest_html_blob = bucket.get_blob(latest_html_blob_name)
    t2_latest = latest_html_blob.updated
    assert t1_latest != t2_latest, "latest is updated"

    # Update the YAML, build new docs, and verify the old HTML is updated.
    upload_yaml(yaml_dir, test_bucket)
    generate.build_new_docs(test_bucket, storage_client)
    html_blob = bucket.get_blob(html_blob.name)
    t10 = html_blob.updated
    assert t9 != t10, "old version was not updated after build_new_docs"


def test_local_generate(yaml_dir, tmpdir):
    # Test for local generation content
    output_path = run_local_generate(yaml_dir)

    verify_template_content(output_path)


@pytest.fixture(scope="module")
def xref_test_blobs():
    test_bucket, storage_client = init_test()
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
    test_bucket, storage_client = init_test()
    bucket = storage_client.get_bucket(test_bucket)

    tmpdir = pathlib.Path(tmpdir)
    got = generate.get_xref(test_input, bucket, tmpdir)

    if ":" in expected:
        assert got == expected
        return
    if expected == "":
        assert got == expected
        return
    expected_path = tmpdir / expected
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
        metadata.version = "2.1.1"

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
      "_packageVersion": "2.1.1",
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
      "_projectPath": "/python/docs/reference/"
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
      "_packageVersion": "",
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
      "_projectPath": "/dotnet/docs/reference/"
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

    test_jobs = [
        [
            "cloud-devrel/client-libraries/doc-pipeline/generate/generate-prod",
            "generate-prod",
        ],
        [
            "cloud-devrel/client-libraries/doc-pipeline/generate/generate-dev",
            "generate-dev",
        ],
        [
            "cloud-devrel/client-libraries/doc-pipeline/generate/generate-staging",
            "generate-staging",
        ],
    ]

    @parameterized.expand(test_jobs)
    def test_write_xunit(self, kokoro_job_name, job_name):
        want = """<testsuites>
  <testsuite tests="2" failures="1" name="{}">
    <testcase classname="build" name="hello" />
    <testcase classname="build" name="goodbye">
      <failure message="Failed" />
    </testcase>
  </testsuite>
</testsuites>""".format(
            job_name
        )
        f = io.StringIO()
        successes = ["hello"]
        failures = ["goodbye"]
        os.environ["KOKORO_JOB_NAME"] = kokoro_job_name
        generate.write_xunit(f, successes, failures)
        got = f.getvalue()
        self.assertMultiLineEqual(want, got)

    def test_parse_blob_name(self):
        want = ["python", "spanner"]
        blob_name = "docfx-python-spanner-3.7.0.tar.gz"
        got = list(generate.parse_blob_name(blob_name))
        self.assertCountEqual(want, got)


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
