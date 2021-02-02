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
import shutil

from docuploader import shell, tar
from google.cloud import storage
from google.oauth2 import service_account
import pytest

from docpipeline import generate


@pytest.fixture
def api_dir(tmpdir):
    tmpdir = tmpdir / "api"
    shutil.copytree("testdata", tmpdir, dirs_exist_ok=True)
    return tmpdir


def test_apidir(api_dir, tmpdir):
    test_bucket = os.environ.get("TEST_BUCKET")
    if not test_bucket:
        pytest.skip("Must set TEST_BUCKET")

    credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials:
        pytest.skip("Must set GOOGLE_APPLICATION_CREDENTIALS")

    parsed_credentials = service_account.Credentials.from_service_account_file(
        credentials
    )
    storage_client = storage.Client(
        project=parsed_credentials.project_id, credentials=parsed_credentials
    )

    # Clean up any previous test data.
    yaml_blob_name = "docfx-python-doc-pipeline-test-2.1.1.tar.gz"
    html_blob_name = "python-doc-pipeline-test-2.1.1.tar.gz"
    bucket = storage_client.get_bucket(test_bucket)
    yaml_blob = bucket.blob(yaml_blob_name)
    html_blob = bucket.blob(html_blob_name)
    if yaml_blob.exists():
        yaml_blob.delete()
    if html_blob.exists():
        html_blob.delete()

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
        cwd=api_dir,
        hide_output=False,
    )

    # Make sure docuploader succeeded.
    assert len(list(storage_client.list_blobs(test_bucket))) == len(start_blobs) + 1

    # Generate!
    try:
        generate.build_new_docs(test_bucket, credentials)
    except Exception as e:
        pytest.fail(f"build_new_docs raised an exception: {e}")

    # Verify the results.
    blobs = list(storage_client.list_blobs(test_bucket))
    assert len(blobs) == len(start_blobs) + 2

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

    # Check the template worked.
    html_file_path = tmpdir.join("google.api.customhttppattern.html")
    assert html_file_path.isfile()
    got_text = html_file_path.read_text("utf-8")
    assert "devsite" in got_text
    assert "/python/_book.yaml" in got_text
