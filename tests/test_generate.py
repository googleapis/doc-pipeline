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
from unittest import mock

from docuploader import shell, tar
from docuploader.protos import metadata_pb2
from google.cloud import storage
from google.protobuf import text_format
from parameterized import parameterized
import pytest

from docpipeline import generate, local_generate


# Unique identifier for running tests in parallel.
_UUID = str(datetime.datetime.now(tz=datetime.timezone.utc).timestamp()).replace(
    ".", ""
)

# Prefixes to check to delete test blobs if found.
_HTML_BLOB_PREFIX = "go-cloud.google.com/go/storage"
_TEST_BLOB_PREFIXES = (
    f"docfx-{_HTML_BLOB_PREFIX}",
    _HTML_BLOB_PREFIX,
    f"{generate.XREFS_DIR_NAME}/{_HTML_BLOB_PREFIX}",
)

# Blob names with UUID for testing.
_UNIQUE_YAML_BLOB_NAME = f"docfx-go-cloud.google.com/go/storage-v1.51.0+{_UUID}.tar.gz"
_UNIQUE_HTML_BLOB_NAME = f"go-cloud.google.com/go/storage-v1.51.0+{_UUID}.tar.gz"

_XREF_BLOBS = (
    "xrefs/go-unused-v0.0.1.tar.gz.yml",
    "xrefs/dotnet-my-pkg-1.0.0.tar.gz.yml",
    "xrefs/dotnet-my-pkg-v1.1.0.tar.gz.yml",
    "xrefs/dotnet-my-pkg-2.0.0-SNAPSHOT.tar.gz.yml",
    "xrefs/dotnet-my-pkg-2.0.0.tar.gz.yml",
    "xrefs/dotnet-my-pkg-unused-3.0.0.tar.gz.yml",
    "xrefs/dotnet-v-pkg-v3.0.0.tar.gz.yml",
    "xrefs/dotnet-v-pkg-v4.0.0.tar.gz.yml",
)


def _add_uuid_to_metadata(cwd, metadata_name) -> None:
    metadata_path = cwd.joinpath(metadata_name)
    metadata = metadata_pb2.Metadata()
    text_format.Merge(metadata_path.read_text(), metadata)
    metadata.version += f"+{_UUID}"
    with open(metadata_path, "w") as f:
        f.write(str(metadata))


@pytest.fixture
def yaml_dir(tmpdir) -> pathlib.Path:
    yaml_path = pathlib.Path(tmpdir) / "yaml_input"
    shutil.copytree("testdata/go", yaml_path, dirs_exist_ok=True)
    _add_uuid_to_metadata(yaml_path, "docs.metadata")
    _add_uuid_to_metadata(yaml_path, "docs.metadata.newer")
    return yaml_path


@pytest.fixture
def api_dir(tmpdir) -> pathlib.Path:
    api_input_path = pathlib.Path(tmpdir) / "api_input"
    shutil.copytree("testdata/go", api_input_path / "api", dirs_exist_ok=True)
    shutil.copy("testdata/go/docs.metadata", api_input_path)
    _add_uuid_to_metadata(api_input_path, "docs.metadata")
    return api_input_path


def swap_file(parent_dir, file1, file2):
    temp_file = parent_dir / (file1.name + "_temp")
    shutil.copy(file1, temp_file)
    shutil.copy(file2, file1)
    shutil.copy(temp_file, file2)
    os.remove(temp_file)


def _is_current_run_or_shared_blob(blob_name: str, uuid: str = _UUID) -> bool:
    if not any(blob_name.startswith(prefix) for prefix in _TEST_BLOB_PREFIXES):
        return True
    return f"+{uuid}" in blob_name


def _wrap_storage_client(storage_client, uuid: str = _UUID):
    orig_list_blobs = storage_client.list_blobs
    storage_client._unfiltered_list_blobs = orig_list_blobs
    storage_client.list_blobs = lambda *args, **kwargs: [
        blob
        for blob in orig_list_blobs(*args, **kwargs)
        if _is_current_run_or_shared_blob(blob.name, uuid)
    ]
    return storage_client


# Initializes key variables needed for the test
def init_test():
    test_bucket = os.environ.get("TEST_BUCKET")
    if not test_bucket:
        pytest.skip("must set TEST_BUCKET")

    storage_client = _wrap_storage_client(storage.Client())

    return test_bucket, storage_client


def clean_up_bucket(storage_client, test_bucket):
    list_blobs_fn = storage_client.__dict__.get(
        "_unfiltered_list_blobs", storage_client.list_blobs
    )
    blobs = list(list_blobs_fn(test_bucket))
    for blob in blobs:
        # If blob starts with any of the prefixes to delete, mark for deletion.
        if (
            datetime.datetime.now(tz=datetime.timezone.utc) - blob.time_created
        ).days == 0 or not any(
            blob.name.startswith(prefix) for prefix in _TEST_BLOB_PREFIXES
        ):
            continue

        try:
            blob.delete()
        except Exception:
            continue


def clean_up_current_run(storage_client, test_bucket, uuid: str = _UUID):
    list_blobs_fn = storage_client.__dict__.get(
        "_unfiltered_list_blobs", storage_client.list_blobs
    )
    blobs = list(list_blobs_fn(test_bucket))
    for blob in blobs:
        if f"+{uuid}" not in blob.name or not any(
            blob.name.startswith(prefix) for prefix in _TEST_BLOB_PREFIXES
        ):
            continue

        try:
            blob.delete()
        except Exception:
            continue


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_run():
    yield
    test_bucket = os.environ.get("TEST_BUCKET")
    if test_bucket:
        clean_up_current_run(storage.Client(), test_bucket)


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
    clean_up_bucket(storage_client, test_bucket)

    upload_yaml(cwd, test_bucket)

    # Make sure docuploader succeeded.
    bucket = storage_client.get_bucket(test_bucket)
    yaml_blob = bucket.blob(_UNIQUE_YAML_BLOB_NAME)
    html_blob = bucket.blob(_UNIQUE_HTML_BLOB_NAME)
    assert yaml_blob.exists(), "should create the YAML blob"
    return bucket, yaml_blob, html_blob


# Call generate.build_new_docs and assert a new tarball is uploaded.
def run_generate(storage_client, test_bucket):
    # Generate!
    try:
        generate.build_new_docs(test_bucket, storage_client)
    except Exception as e:
        pytest.fail(f"build_new_docs raised an exception: {e}")

    # Verify the results.
    # Expect an output blob and an output xref file.
    bucket = storage_client.get_bucket(test_bucket)
    html_blob = bucket.blob(_UNIQUE_HTML_BLOB_NAME)
    xref_blob = bucket.blob(f"{generate.XREFS_DIR_NAME}/{_UNIQUE_HTML_BLOB_NAME}.yml")
    assert html_blob.exists(), "should create HTML blob"
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
        "### YamlMime:XRefMap\nbaseUrl: https://docs.cloud.google.com"
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
    latest_html_blob_name = f"go-cloud.google.com/go/storage-v1.51.1+{_UUID}.tar.gz"

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

    for b in _XREF_BLOBS:
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

    def test_clean_up_bucket(self):
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        old_time = now - datetime.timedelta(days=2)
        recent_time = now - datetime.timedelta(hours=1)

        def make_blob(name, time_created):
            blob = mock.MagicMock()
            blob.name = name
            blob.time_created = time_created
            return blob

        blobs_to_delete = [
            make_blob(
                "docfx-go-cloud.google.com/go/storage-v1.51.0+123.tar.gz", old_time
            ),
            make_blob(
                "docfx-go-cloud.google.com/go/storage-v1.51.1+123.tar.gz", old_time
            ),
            make_blob("go-cloud.google.com/go/storage-v1.51.0+123.tar.gz", old_time),
            make_blob("go-cloud.google.com/go/storage-v1.51.1+123.tar.gz", old_time),
            make_blob(
                "xrefs/go-cloud.google.com/go/storage-v1.51.0+123.tar.gz.yml", old_time
            ),
            make_blob(
                "xrefs/go-cloud.google.com/go/storage-v1.51.1+123.tar.gz.yml", old_time
            ),
            make_blob(
                "xrefs/go-cloud.google.com/go/storage-v1.40.0+123.tar.gz.yml", old_time
            ),
        ]
        blobs_to_keep = [
            make_blob(
                "docfx-go-cloud.google.com/go/storage-v1.51.0+456.tar.gz", recent_time
            ),
            make_blob("go-cloud.google.com/go/storage-v1.51.0+456.tar.gz", recent_time),
            make_blob(
                "xrefs/go-cloud.google.com/go/storage-v1.51.0+456.tar.gz.yml",
                recent_time,
            ),
            make_blob("xrefs/dotnet-my-pkg-1.0.0.tar.gz.yml", old_time),
            make_blob("xrefs/go-unused-v0.0.1.tar.gz.yml", old_time),
        ]

        storage_client = mock.MagicMock()
        storage_client.list_blobs.return_value = blobs_to_delete + blobs_to_keep
        _wrap_storage_client(storage_client, uuid="456")

        clean_up_bucket(storage_client, "doc-pipeline-test")

        for blob in blobs_to_delete:
            blob.delete.assert_called_once_with()
        for blob in blobs_to_keep:
            blob.delete.assert_not_called()

    def test_wrap_storage_client_filters_other_runs(self):
        def make_blob(name):
            blob = mock.MagicMock()
            blob.name = name
            return blob

        current_run_blobs = [
            make_blob("docfx-go-cloud.google.com/go/storage-v1.51.0+111.tar.gz"),
            make_blob("go-cloud.google.com/go/storage-v1.51.0+111.tar.gz"),
            make_blob("xrefs/go-cloud.google.com/go/storage-v1.51.0+111.tar.gz.yml"),
            make_blob("xrefs/dotnet-my-pkg-1.0.0.tar.gz.yml"),
        ]
        other_run_blobs = [
            make_blob("docfx-go-cloud.google.com/go/storage-v1.51.0+222.tar.gz"),
            make_blob("docfx-go-cloud.google.com/go/storage-v1.51.1+222.tar.gz"),
            make_blob("go-cloud.google.com/go/storage-v1.51.0+222.tar.gz"),
            make_blob("xrefs/go-cloud.google.com/go/storage-v1.51.0+222.tar.gz.yml"),
        ]

        storage_client = mock.MagicMock()
        storage_client.list_blobs.return_value = current_run_blobs + other_run_blobs
        _wrap_storage_client(storage_client, uuid="111")

        got = storage_client.list_blobs("doc-pipeline-test")
        self.assertEqual(got, current_run_blobs)

    def test_clean_up_current_run(self):
        def make_blob(name):
            blob = mock.MagicMock()
            blob.name = name
            return blob

        blobs_to_delete = [
            make_blob("docfx-go-cloud.google.com/go/storage-v1.51.0+111.tar.gz"),
            make_blob("docfx-go-cloud.google.com/go/storage-v1.51.1+111.tar.gz"),
            make_blob("go-cloud.google.com/go/storage-v1.51.0+111.tar.gz"),
            make_blob("go-cloud.google.com/go/storage-v1.51.1+111.tar.gz"),
            make_blob("xrefs/go-cloud.google.com/go/storage-v1.51.0+111.tar.gz.yml"),
            make_blob("xrefs/go-cloud.google.com/go/storage-v1.51.1+111.tar.gz.yml"),
        ]
        blobs_to_keep = [
            make_blob("docfx-go-cloud.google.com/go/storage-v1.51.0+222.tar.gz"),
            make_blob("go-cloud.google.com/go/storage-v1.51.0+222.tar.gz"),
            make_blob("xrefs/go-cloud.google.com/go/storage-v1.51.0+222.tar.gz.yml"),
            make_blob("xrefs/dotnet-my-pkg-1.0.0.tar.gz.yml"),
        ]

        storage_client = mock.MagicMock()
        storage_client.list_blobs.return_value = blobs_to_delete + blobs_to_keep

        clean_up_current_run(storage_client, "doc-pipeline-test", uuid="111")

        for blob in blobs_to_delete:
            blob.delete.assert_called_once_with()
        for blob in blobs_to_keep:
            blob.delete.assert_not_called()


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


@parameterized.expand(
    [
        ("docfx-go-cloud.google.com/go/automl-v1.14.0.tar.gz", True),
        ("docfx-go-cloud.google.com/go/maintenance-v1.0.0.tar.gz", True),
        ("docfx-go-cloud.google.com/go/compute-v1.20.0.tar.gz", True),
        ("docfx-go-cloud.google.com/go/compute/metadata-v0.2.3.tar.gz", False),
        ("docfx-go-cloud.google.com/go/compute-something-v1.0.0.tar.gz", False),
        ("docfx-go-cloud.google.com/go/storage-v1.51.0.tar.gz", False),
        ("docfx-python-storageinsights-0.1.12.tar.gz", False),
    ]
)
def test_should_skip_blob(blob_name, expected):
    assert generate.should_skip_blob(blob_name) == expected
