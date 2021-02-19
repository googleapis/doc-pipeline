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
        "src": "obj/api"
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


def add_prettyprint(output_path):
    files = output_path.glob("**/*.html")
    # Handle files in binary to avoid line endings
    # being changed when running on Windows.
    for file in files:
        with open(file, "rb") as file_handle:
            html = file_handle.read()
        html = html.replace(
            '<code class="lang-'.encode(), '<code class="prettyprint lang-'.encode()
        )
        with open(file, "wb") as file_handle:
            file_handle.write(html)


def setup_docfx(tmp_path, input_path):
    api_path = decompress_path = tmp_path.joinpath("obj/api")

    api_path.mkdir(parents=True, exist_ok=True)

    for item in input_path.iterdir():
        if item.is_dir() and item.name == "api":
            decompress_path = tmp_path.joinpath("obj")
            break

    shutil.copytree(input_path, decompress_path, dirs_exist_ok=True)
    log.info(f"Decompressed in {decompress_path}")

    metadata = metadata_pb2.Metadata()
    metadata_path = decompress_path.joinpath("docs.metadata.json")
    if metadata_path.exists():
        json_format.Parse(metadata_path.read_text(), metadata)
    else:
        metadata_path = decompress_path.joinpath("docs.metadata")
        text_format.Merge(metadata_path.read_text(), metadata)

    with open(tmp_path.joinpath("docfx.json"), "w") as f:
        f.write(format_docfx_json(metadata))
    log.info("Wrote docfx.json")

    # TODO: remove this once _toc.yaml is no longer created.
    if pathlib.Path(api_path.joinpath("_toc.yaml")).is_file():
        shutil.move(api_path.joinpath("_toc.yaml"), api_path.joinpath("toc.yml"))

    return metadata_path, metadata


def process_blob(input_path, devsite_template):
    tmp_path = pathlib.Path(tempfile.TemporaryDirectory(prefix="doc-pipeline.").name)

    metadata_path, metadata = setup_docfx(tmp_path, input_path)

    site_path = tmp_path.joinpath("site")

    log.info(f"Running `docfx build` for {metadata.name}...")
    shell.run(
        ["docfx", "build", "-t", f"{devsite_template.absolute()}"],
        cwd=tmp_path,
        hide_output=False,
    )

    # Rename the output TOC file to be _toc.yaml to match the expected
    # format. As well, support both toc.html and toc.yaml
    try:
        shutil.move(site_path.joinpath("toc.yaml"), site_path.joinpath("_toc.yaml"))
    except FileNotFoundError:
        shutil.move(site_path.joinpath("toc.html"), site_path.joinpath("_toc.yaml"))

    # Remove the manifest.json file.
    site_path.joinpath("manifest.json").unlink()

    # Add the prettyprint class to code snippets
    add_prettyprint(site_path)

    log.success(f"Done building HTML for {metadata.name}. Copying over...")

    # Reuse the same docs.metadata file. The original docfx- prefix is an
    # command line option when uploading, not part of docs.metadata.
    shutil.copy(metadata_path, site_path)

    output_path = input_path.joinpath(metadata.name)
    if output_path.exists():
        log.info(f"deleting existing directory: {output_path}")
        shutil.rmtree(output_path)
    shutil.copytree(site_path, output_path, dirs_exist_ok=True)
    shutil.rmtree(tmp_path)

    log.success(f"Done with {metadata.name}!")


def build_blob(input_path):
    log.info("Let's build some docs!")

    # Clone doc-templates.
    templates_dir = pathlib.Path("doc-templates")
    if templates_dir.is_dir():
        shutil.rmtree(templates_dir)
    templates_dir.mkdir(parents=True, exist_ok=True)
    log.info(f"Cloning templates into {templates_dir.absolute()}")
    clone_templates(templates_dir)
    log.info(f"Got the templates ({templates_dir.absolute()})!")
    devsite_template = templates_dir.joinpath("third_party/docfx/templates/devsite")

    failure = 0
    try:
        log.info("Processing files in directory...")
        process_blob(input_path, devsite_template)
    except Exception as e:
        failure = 1
        log.error(f"Error processing local build, {e}")

    shutil.rmtree(templates_dir)

    if failure:
        raise Exception("Got errors while processing the directory")

    log.success("Done!")


def build_local_doc(input_path):
    input_path = pathlib.Path(input_path)
    if not input_path.exists():
        raise Exception(f"{input_path} is not a valid directory path!")
    build_blob(input_path)
