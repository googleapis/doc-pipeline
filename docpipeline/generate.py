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

import pathlib
import shutil
import tempfile
import tarfile

from docuploader import log, shell, tar
from docuploader.protos import metadata_pb2
from google.cloud import storage
from google.oauth2 import service_account
from google.protobuf import text_format, json_format


DOCFX_PREFIX = "docfx-"

DOCFX_JSON_TEMPLATE = """
{{
  "build": {{
    "content": [
      {{
        "files": ["**/*.yml", "**/*.md"],
        "src": "obj/api",
        "dest": "api"
      }}
    ],
    "globalMetadata": {{
      "_appTitle": "{package}",
      "_disableContribution": true,
      "_appFooter": " ",
      "_disableNavbar": true,
      "_disableBreadcrumb": true,
      "_enableSearch": false,
      "_disableToc": true,
      "_disableSideFilter": true,
      "_disableAffix": true,
      "_disableFooter": true,
      "_rootPath": "{path}",
      "_projectPath": "{project_path}"
    }},
    "overwrite": [
      "obj/examples/*.md"
    ],
    "dest": "site",
    "xref": [{xrefs}],
    "xrefService": [{xref_services}],
  }}
}}
"""


def clone_templates(dir):
    shell.run(
        [
            "git",
            "clone",
            "--depth=1",
            "https://github.com/googleapis/doc-templates.git",
            ".",
        ],
        cwd=dir,
        hide_output=True,
    )


def format_docfx_json(metadata):
    pkg = metadata.name
    xrefs = ", ".join([f'"{xref}"' for xref in metadata.xrefs])
    xref_services = ", ".join([f'"{xref}"' for xref in metadata.xref_services])

    return DOCFX_JSON_TEMPLATE.format(
        package=pkg,
        path=f"/{metadata.language}/docs/reference/{pkg}/latest",
        project_path=f"/{metadata.language}/",
        xrefs=xrefs,
        xref_services=xref_services,
    )


def process_blob(blob, credentials, devsite_template):
    tmp_path = pathlib.Path(tempfile.TemporaryDirectory(prefix="doc-pipeline.").name)
    api_path = decompress_path = tmp_path.joinpath("obj/api")
    output_path = tmp_path.joinpath("site")
    output_api_path = output_path.joinpath("api")

    api_path.mkdir(parents=True, exist_ok=True)
    tar_filename = tmp_path.joinpath(blob.name)
    tar_filename.parent.mkdir(parents=True, exist_ok=True)

    blob.download_to_filename(tar_filename)
    log.info(f"Downloaded gs://{blob.bucket.name}/{blob.name} to {tar_filename}")

    # Check to see if api directory exists in the tarball.
    # If so, only decompress things into obj/*
    tar_file = tarfile.open(tar_filename)
    for tarinfo in tar_file:
        if tarinfo.isdir() and tarinfo.name == "./api":
            decompress_path = tmp_path.joinpath("obj")
            break

    tar.decompress(tar_filename, decompress_path)
    log.info(f"Decompressed {blob.name} in {decompress_path}")

    metadata_file = "docs.metadata"
    if decompress_path.joinpath("docs.metadata.json").exists():
        metadata_file = "docs.metadata.json"

    metadata_path = decompress_path.joinpath(metadata_file)
    metadata = metadata_pb2.Metadata()
    if metadata_file.endswith(".json"):
        json_format.Parse(metadata_path.read_text(), metadata)
    else:
        text_format.Merge(metadata_path.read_text(), metadata)

    with open(tmp_path.joinpath("docfx.json"), "w") as f:
        f.write(format_docfx_json(metadata))
    log.info("Wrote docfx.json")

    # TODO: remove this once _toc.yaml is no longer created.
    if pathlib.Path(api_path.joinpath("_toc.yaml")).is_file():
        shutil.move(api_path.joinpath("_toc.yaml"), api_path.joinpath("toc.yml"))

    log.info(f"Running `docfx build` for {blob.name}...")
    shell.run(
        ["docfx", "build", "-t", f"{devsite_template.absolute()}"],
        cwd=tmp_path,
        hide_output=False,
    )

    # Rename the output TOC file to be _toc.yaml to match the expected
    # format. As well, support both toc.html and toc.yaml
    try:
        shutil.move(
            output_api_path.joinpath("toc.yaml"), output_api_path.joinpath("_toc.yaml")
        )
    except FileNotFoundError:
        shutil.move(
            output_api_path.joinpath("toc.html"), output_api_path.joinpath("_toc.yaml")
        )

    # Move the xrefmap file to the output directory.
    shutil.move(
        output_path.joinpath("xrefmap.yml"), output_api_path.joinpath("xrefmap.yml")
    )

    log.success(f"Done building HTML for {blob.name}. Starting upload...")

    # Reuse the same docs.metadata file. The original docfx- prefix is an
    # command line option when uploading, not part of docs.metadata.
    shutil.copyfile(metadata_path, output_api_path.joinpath(metadata_file))

    shell.run(
        [
            "docuploader",
            "upload",
            ".",
            f"--credentials={credentials}",
            f"--staging-bucket={blob.bucket.name}",
        ],
        cwd=output_api_path,
        hide_output=False,
    )
    shutil.rmtree(tmp_path)

    log.success(f"Done with {blob.name}!")


def build_blobs(blobs, credentials):
    num = len(blobs)
    if num == 0:
        log.success("No blobs to process!")
        return

    log.info("Let's build some docs!")

    blobs_str = "\n".join(map(lambda blob: blob.name, blobs))
    log.info(f"Processing {num} blob{'' if num == 1 else 's'}:\n{blobs_str}")

    templates_dir = pathlib.Path("doc-templates")
    if templates_dir.is_dir():
        shutil.rmtree(templates_dir)
    templates_dir.mkdir(parents=True, exist_ok=True)
    log.info(f"Cloning templates into {templates_dir.absolute()}")
    clone_templates(templates_dir)
    log.info(f"Got the templates ({templates_dir.absolute()})!")
    devsite_template = templates_dir.joinpath("third_party/docfx/templates/devsite")

    failures = []

    for i, blob in enumerate(blobs):
        try:
            log.info(f"Processing {i+1} of {len(blobs)}: {blob.name}...")
            process_blob(blob, credentials, devsite_template)
        except Exception as e:
            # Keep processing the other files if an error occurs.
            log.error(f"Error processing {blob.name}:\n\n{e}")
            failures.append(blob.name)

    shutil.rmtree(templates_dir)

    if len(failures) > 0:
        failure_str = "\n".join(failures)
        raise Exception(
            f"Got errors while processing the following archives:\n{failure_str}"
        )

    log.success("Done!")


def storage_client(credentials):
    parsed_credentials = service_account.Credentials.from_service_account_file(
        credentials
    )
    return storage.Client(
        project=parsed_credentials.project_id, credentials=parsed_credentials
    )


def build_all_docs(bucket_name, credentials):
    all_blobs = storage_client(credentials).list_blobs(bucket_name)
    docfx_blobs = [blob for blob in all_blobs if blob.name.startswith(DOCFX_PREFIX)]
    build_blobs(docfx_blobs, credentials)


def build_one_doc(bucket_name, object_name, credentials):
    blob = storage_client(credentials).bucket(bucket_name).get_blob(object_name)
    if blob is None:
        raise Exception(f"Could not find gs://{bucket_name}/{object_name}!")
    build_blobs([blob], credentials)


def build_new_docs(bucket_name, credentials):
    all_blobs = list(storage_client(credentials).list_blobs(bucket_name))
    docfx_blobs = [blob for blob in all_blobs if blob.name.startswith(DOCFX_PREFIX)]
    other_blobs = [blob for blob in all_blobs if not blob.name.startswith(DOCFX_PREFIX)]
    other_names = set(map(lambda b: b.name, other_blobs))

    new_blobs = []
    for blob in docfx_blobs:
        new_name = blob.name[len(DOCFX_PREFIX) :]
        if new_name not in other_names:
            new_blobs.append(blob)
    build_blobs(new_blobs, credentials)


def build_language_docs(bucket_name, language, credentials):
    all_blobs = storage_client(credentials).list_blobs(bucket_name)
    language_prefix = DOCFX_PREFIX + language + "-"
    docfx_blobs = [blob for blob in all_blobs if blob.name.startswith(language_prefix)]
    build_blobs(docfx_blobs, credentials)
