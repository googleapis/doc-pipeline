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

import collections
from io import TextIOWrapper
import pathlib
import shutil
import tempfile
import tarfile
from typing import DefaultDict, Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET

from docuploader import log, shell, tar
from docuploader.protos import metadata_pb2
from google.cloud import storage
from google.protobuf import text_format, json_format
from docpipeline import prepare

import semver


DOCFX_PREFIX = "docfx-"

XREFS_DIR_NAME = "xrefs"

DEVSITE_SCHEME = "devsite://"

MULTI_VERSION_LANGUAGES = ["go", "java", "python", "ruby"]

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
      "_packageVersion": "{package_version}",
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


def clone_templates(dir: pathlib.Path) -> None:
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


def setup_templates() -> Tuple[pathlib.Path, pathlib.Path]:
    templates_dir = pathlib.Path("doc-templates")
    if templates_dir.is_dir():
        shutil.rmtree(templates_dir)
    templates_dir.mkdir(parents=True, exist_ok=True)
    log.info(f"Cloning templates into {templates_dir.absolute()}")
    clone_templates(templates_dir)
    log.info(f"Got the templates ({templates_dir.absolute()})!")
    devsite_template = templates_dir.joinpath("third_party/docfx/templates/devsite")

    return templates_dir, devsite_template


def format_docfx_json(metadata: metadata_pb2.Metadata) -> str:
    pkg = metadata.name
    xrefs = ", ".join([f'"{xref}"' for xref in metadata.xrefs if xref != ""])
    xref_services = ", ".join([f'"{xref}"' for xref in metadata.xref_services])
    path = get_path(metadata)
    version = metadata.version
    project_path = f"/{metadata.language}/docs/reference/"

    return DOCFX_JSON_TEMPLATE.format(
        package=pkg,
        package_version=version,
        path=path,
        project_path=project_path,
        xrefs=xrefs,
        xref_services=xref_services,
    )


def setup_local_docfx(
    tmp_path: pathlib.Path,
    api_path: pathlib.Path,
    decompress_path: pathlib.Path,
    blob: storage.Blob,
) -> Tuple[pathlib.Path, metadata_pb2.Metadata]:
    for item in blob.iterdir():
        if item.is_dir() and item.name == "api":
            decompress_path = tmp_path.joinpath("obj")
            break

    shutil.copytree(blob, decompress_path, dirs_exist_ok=True)
    log.info(f"Decompressed in {decompress_path}")

    return write_docfx_json(tmp_path, api_path, decompress_path, blob)


def setup_bucket_docfx(
    tmp_path: pathlib.Path,
    api_path: pathlib.Path,
    decompress_path: pathlib.Path,
    blob: storage.Blob,
) -> Tuple[pathlib.Path, metadata_pb2.Metadata]:
    tar_filename = tmp_path.joinpath(blob.name)
    tar_filename.parent.mkdir(parents=True, exist_ok=True)

    # Reinstantiate the blob in case it changed between listing and downloading.
    blob = blob.bucket.blob(blob.name)
    if not blob.exists():
        raise ValueError(
            (
                f"Blob gs://{blob.bucket.name}/{blob.name} does"
                "not exist (maybe it was deleted?)"
            )
        )
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

    return write_docfx_json(tmp_path, api_path, decompress_path, blob)


def write_docfx_json(
    tmp_path: pathlib.Path,
    api_path: pathlib.Path,
    decompress_path: pathlib.Path,
    blob: storage.Blob,
) -> Tuple[pathlib.Path, metadata_pb2.Metadata]:
    metadata = metadata_pb2.Metadata()
    metadata_path = decompress_path.joinpath("docs.metadata.json")
    if metadata_path.exists():
        json_format.Parse(metadata_path.read_text(), metadata)
    else:
        metadata_path = decompress_path.joinpath("docs.metadata")
        text_format.Merge(metadata_path.read_text(), metadata)

    try:
        metadata.xrefs[:] = [
            get_xref(xref, blob.bucket, tmp_path) for xref in metadata.xrefs
        ]
    except AttributeError:
        log.warning("Building locally will ignore xrefs in the metadata.")

    with open(tmp_path.joinpath("docfx.json"), "w") as f:
        f.write(format_docfx_json(metadata))
    log.info("Wrote docfx.json")

    # TODO: remove this once _toc.yaml is no longer created.
    if pathlib.Path(api_path.joinpath("_toc.yaml")).is_file():
        shutil.move(api_path.joinpath("_toc.yaml"), api_path.joinpath("toc.yml"))

    return metadata_path, metadata


def build_and_format(
    blob: storage.Blob, is_bucket: bool, devsite_template: pathlib.Path
) -> Tuple[pathlib.Path, metadata_pb2.Metadata, pathlib.Path]:
    tmp_path = pathlib.Path(tempfile.TemporaryDirectory(prefix="doc-pipeline.").name)

    api_path = decompress_path = tmp_path.joinpath("obj/api")

    api_path.mkdir(parents=True, exist_ok=True)

    # If building blobs on a bucket, use setup_bucket_docfx
    # Else, use setup_local_docfx
    if is_bucket:
        metadata_path, metadata = setup_bucket_docfx(
            tmp_path, api_path, decompress_path, blob
        )
        blob_name = blob.name
    else:
        metadata_path, metadata = setup_local_docfx(
            tmp_path, api_path, decompress_path, blob
        )
        blob_name = metadata.name

    site_path = tmp_path.joinpath("site")

    log.info(f"Running `docfx build` for {blob_name}...")
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

    html_files = list(site_path.glob("**/*.html"))
    if len(html_files) == 0:
        raise ValueError("Did not generate any HTML files.")

    # Remove the manifest.json file.
    site_path.joinpath("manifest.json").unlink()

    # Add the prettyprint class to code snippets
    prepare.add_prettyprint(site_path)

    log.success(f"Done building HTML for {blob_name}. Starting upload...")

    # Reuse the same docs.metadata file. The original docfx- prefix is an
    # command line option when uploading, not part of docs.metadata.
    shutil.copy(metadata_path, site_path)

    return tmp_path, metadata, site_path


def get_path(metadata: metadata_pb2.Metadata) -> str:
    path = f"/{metadata.language}/docs/reference/{metadata.name}"
    if metadata.stem != "":
        path = metadata.stem
    if metadata.name != "help":
        if metadata.language in MULTI_VERSION_LANGUAGES and metadata.version:
            path += f"/{metadata.version}"
        else:
            path += "/latest"
    return path


def process_blob(blob: storage.Blob, devsite_template: pathlib.Path) -> None:
    is_bucket = True
    tmp_path, metadata, site_path = build_and_format(blob, is_bucket, devsite_template)

    # Use the input blob name as the name of the xref file to avoid collisions.
    # The input blob has a "docfx-" prefix; make sure to remove it.
    xrefmap = site_path.joinpath("xrefmap.yml")
    xrefmap_lines = xrefmap.read_text().splitlines()
    # The baseUrl must start with a scheme and domain. With no scheme, docfx
    # assumes it's a file:// link.
    base_url = f"baseUrl: https://cloud.google.com{get_path(metadata)}/"

    # Insert base_url after the YamlMime first line.
    xrefmap_lines.insert(1, base_url)
    xrefmap.write_text("\n".join(xrefmap_lines))

    xref_blob_name_base = blob.name[len("docfx-") :]
    xref_blob = blob.bucket.blob(f"{XREFS_DIR_NAME}/{xref_blob_name_base}.yml")
    xref_blob.upload_from_filename(filename=xrefmap)

    shell.run(
        [
            "docuploader",
            "upload",
            ".",
            f"--staging-bucket={blob.bucket.name}",
        ],
        cwd=site_path,
        hide_output=False,
    )

    shutil.rmtree(tmp_path)

    log.success(f"Done with {blob.name}!")


def get_xref(xref: str, bucket: storage.Bucket, dir: pathlib.Path) -> str:
    if not xref.startswith(DEVSITE_SCHEME):
        return xref

    d_xref = xref[len(DEVSITE_SCHEME) :]
    lang, pkg = d_xref.split("/", 1)
    version = "latest"
    extension = ".tar.gz.yml"
    if "@" in pkg:
        pkg, version = pkg.rsplit("@", 1)
    if version == "latest":
        # List all blobs, sort by semver, and pick the latest.
        prefix = f"{XREFS_DIR_NAME}/{lang}-{pkg}-"
        blobs = bucket.list_blobs(prefix=prefix)
        version = find_latest_version(blobs, prefix, extension)

        if version == "":
            # There are no versions, so there is no latest version.
            log.error(f"Could not find {xref} in gs://{bucket.name}. Skipping.")
            return ""

    d_xref = f"{XREFS_DIR_NAME}/{lang}-{pkg}-{version}{extension}"

    blob = bucket.blob(d_xref)
    if not blob.exists():
        # Log warning. Dependency may not be generated yet.
        log.error(f"Could not find gs://{bucket.name}/{d_xref}. Skipping.")
        return ""
    d_xref_path = dir.joinpath(d_xref).absolute()
    d_xref_path.parent.mkdir(parents=True, exist_ok=True)
    blob.download_to_filename(d_xref_path)
    return str(d_xref_path)


def version_sort(v: str) -> semver.VersionInfo:
    if v[0] == "v":  # Remove v prefix, if any.
        v = v[1:]
    return semver.VersionInfo.parse(v)


def find_latest_version(
    blobs: List[storage.Blob], prefix: str, extension: Optional[str] = None
) -> str:
    """Finds the latest version from blobs with specified prefix."""
    tarball_extension = extension if extension else ".tar.gz"
    versions = []
    for blob in blobs:
        # Be sure to trim the suffix extension.
        version = blob.name[len(prefix) : -len(tarball_extension)]
        # Skip if version is not a valid version, like when some other package
        # has prefix as a prefix (...foo-1.0.0" and "...foo-beta1-1.0.0").
        try:
            version_sort(version)
            versions.append(version)
        except ValueError:
            pass  # Ignore.

    if len(versions) == 0:
        return ""

    versions = sorted(versions, key=version_sort)
    return versions[-1]


def parse_blob_name(blob_name: str) -> Tuple[str, str]:
    """Parses the blob's name and returns its language and package."""
    split_name = blob_name.split("-")
    language = split_name[1]
    pkg = "-".join(split_name[2:-1])
    return language, pkg


def find_latest_blobs(
    bucket: storage.Bucket, blobs: List[storage.Blob]
) -> List[storage.Blob]:
    """Gets a list of the latest blob for each package."""
    latest_blobs = []
    blobs_by_language_and_pkg = group_blobs_by_language_and_pkg(blobs)

    # For each unique package, find latest version for its language
    for language, pkgs in blobs_by_language_and_pkg.items():
        for pkg, blobs in pkgs.items():
            prefix = f"{DOCFX_PREFIX}{language}-{pkg}-"
            version = find_latest_version(blobs, prefix)
            if version == "":
                log.error(f"Found no versions for {prefix}, skipping.")
                continue

            latest_blob_name = f"{prefix}{version}.tar.gz"
            latest_blobs.append(bucket.blob(latest_blob_name))

    return latest_blobs


def group_blobs_by_language_and_pkg(
    blobs: List[storage.Blob],
) -> DefaultDict[str, DefaultDict[str, List[storage.Blob]]]:
    """Gets a map from language to package name to a list of blobs."""
    packages: DefaultDict[
        str, DefaultDict[str, List[storage.Blob]]
    ] = collections.defaultdict(lambda: collections.defaultdict(list))
    for blob in blobs:
        language, pkg = parse_blob_name(blob.name)
        packages[language][pkg].append(blob)
    return packages


def build_blobs(blobs: List[storage.Blob]):
    """Builds the HTML for the given blobs."""
    num = len(blobs)
    if num == 0:
        log.success("No blobs to process!")
        return

    log.info("Let's build some docs!")

    blob_names = "\n".join(map(lambda blob: blob.name, blobs))
    log.info(f"Processing {num} blob{'' if num == 1 else 's'}:\n{blob_names}")

    # Clone doc-templates.
    templates_dir, devsite_template = setup_templates()

    # Process every blob.
    failures = []
    successes = []
    for i, blob in enumerate(blobs):
        try:
            log.info(f"Processing {i+1} of {len(blobs)}: {blob.name}...")
            if not blob.name.startswith("docfx"):
                raise ValueError(
                    (
                        f"{blob.name} does not start with docfx,"
                        f"did you mean docfx-{blob.name}?"
                    )
                )
            process_blob(blob, devsite_template)
            successes.append(blob.name)
        except Exception as e:
            # Keep processing the other files if an error occurs.
            log.error(f"Error processing {blob.name}:\n\n{e}")
            failures.append(blob.name)

    shutil.rmtree(templates_dir)

    with open("sponge_log.xml", "w") as f:
        write_xunit(f, successes, failures)

    if len(failures) > 0:
        failure_str = "\n".join(failures)
        raise Exception(
            f"Got errors while processing the following archives:\n{failure_str}"
        )

    log.success("Done!")


def build_all_docs(
    bucket_name: str, storage_client: storage.Client, only_latest: bool = False
):
    """Builds all of the blobs in the bucket."""
    all_blobs = storage_client.list_blobs(bucket_name)
    docfx_blobs = [blob for blob in all_blobs if blob.name.startswith(DOCFX_PREFIX)]
    if only_latest:
        bucket = storage_client.get_bucket(bucket_name)
        docfx_blobs = find_latest_blobs(bucket, docfx_blobs)

    build_blobs(docfx_blobs)


def build_one_doc(bucket_name: str, object_name: str, storage_client: storage.Client):
    """Builds a single blob."""
    blob = storage_client.bucket(bucket_name).get_blob(object_name)
    if blob is None:
        raise Exception(f"Could not find gs://{bucket_name}/{object_name}!")
    build_blobs([blob])


def has_new_blob(
    docfx_blobs: List[storage.Blob], html_blobs: Dict[str, storage.Blob]
) -> bool:
    for blob in docfx_blobs:
        html_name = blob.name[len(DOCFX_PREFIX) :]
        if html_name not in html_blobs:
            return True

        # For existing blobs, check if the YAML is newer than the HTML.
        yaml_last_updated = blob.updated
        html_last_updated = html_blobs[html_name].updated

        if yaml_last_updated > html_last_updated:
            return True

    # If no YAML is newer than its corresponding HTML, there are no updates
    # required.
    return False


def build_new_docs(bucket_name: str, storage_client: storage.Client):
    """Lazily builds just the new blobs in the bucket.

    If the DocFX blob of a package is uploaded for the first time or is newer
    than the corresponding HTML blob, the docs for all versions of the package
    are updated. The new version may or may not be the latest SemVer.
    """
    all_blobs = list(storage_client.list_blobs(bucket_name))
    docfx_blobs = [blob for blob in all_blobs if blob.name.startswith(DOCFX_PREFIX)]
    html_blobs = {b.name: b for b in all_blobs if not b.name.startswith(DOCFX_PREFIX)}

    docfx_blobs_to_process = []
    blobs_by_language_and_pkg = group_blobs_by_language_and_pkg(docfx_blobs)

    for lang, pkgs in blobs_by_language_and_pkg.items():
        for pkg, pkg_blobs in pkgs.items():
            if has_new_blob(pkg_blobs, html_blobs):
                log.info(f"found new blobs for {lang}-{pkg}")
                docfx_blobs_to_process.extend(pkg_blobs)

    build_blobs(docfx_blobs_to_process)


def build_language_docs(
    bucket_name: str,
    language: str,
    storage_client: storage.Client,
    only_latest: bool = False,
):
    """Builds all of the blobs for the given language."""
    all_blobs = storage_client.list_blobs(bucket_name)
    language_prefix = f"{DOCFX_PREFIX}{language}-"
    docfx_blobs = [blob for blob in all_blobs if blob.name.startswith(language_prefix)]
    if only_latest:
        bucket = storage_client.get_bucket(bucket_name)
        docfx_blobs = find_latest_blobs(bucket, docfx_blobs)

    build_blobs(docfx_blobs)


def write_xunit(f: TextIOWrapper, successes: List[str], failures: List[str]):
    testsuites = ET.Element("testsuites")
    testsuite = ET.SubElement(
        testsuites,
        "testsuite",
        attrib={
            "tests": str(len(successes) + len(failures)),
            "failures": str(len(failures)),
            "name": "github.com/googleapis/doc-pipeline/generate",
        },
    )
    for success in successes:
        ET.SubElement(
            testsuite, "testcase", attrib={"classname": "build", "name": success}
        )
    for failure in failures:
        testcase = ET.SubElement(
            testsuite, "testcase", attrib={"classname": "build", "name": failure}
        )
        ET.SubElement(testcase, "failure", attrib={"message": "Failed"})

    tree = ET.ElementTree(element=testsuites)
    ET.indent(tree)
    tree.write(f, encoding="unicode")
