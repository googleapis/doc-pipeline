# Google Cloud Platform document pipeline

`doc-pipeline` converts DocFX YAML to HTML. You can run it locally, but it is set
up to run periodically to generate new docs in production/staging/dev.

`doc-pipeline` uses
[docker-ci-helper](https://github.com/GoogleCloudPlatform/docker-ci-helper) to
facilitate running Docker. See the [instructions below](#running-locally) for
how to test and run locally.

`doc-pipeline` also depends on
[`docuploader`](https://github.com/googleapis/docuploader) to compress and
upload a directory to Google Cloud Storage.

## Using doc-pipeline

`doc-pipeline` is only for converting DocFX YAML to HTML suitable for
cloud.google.com.

You can generate DocFX YAML using language-specific generators.

### What to do during library releases

Here is how to use doc-pipeline. All of the steps except the credential setup
should be automated/scripted as part of the release process.

1. Fetch the credentials to be able to upload to the bucket. Add the following
   to your Kokoro build config:
   ```
   before_action {
      fetch_keystore {
         keystore_resource {
            keystore_config_id: 73713
            keyname: "docuploader_service_account"
         }
      }
   }
   ```
1. Generate DocFX YAML. Usually, this is done as part of the library release
   process.

   * **Note:** You **must** include a `toc.yml` file. However, do not include a
     `docfx.json` file because doc-pipeline generates one for you.
   * You can check the HTML looks OK by running the pipeline locally (see
     [below](#running-locally)).
1. Change to the directory that contains all of the `.yml` files.
1. Create a `docs.metadata` file in the same directory as the YAML:
   ```
   docuploader create-metadata
   ```
   
   Add flags to specify the language, package, version etc. See
   [`docuploader`](https://pypi.org/project/gcp-docuploader).
1. Upload the YAML with the `docfx` prefix:
   ```
   docuploader upload --staging-bucket docs-staging-v2-staging --destination-prefix docfx .
   ```

   There is also `docs-staging-v2` (production) and `docs-staging-v2-dev`
   (development). Use `-staging` until your HTML format is confirmed to be
   correct.
1. That's it! `doc-pipeline` periodically runs, generates the HTML for new
   `docfx-*` tarballs, and uploads the resulting HTML to the same bucket. The
   HTML has the same name as the DocFX tarball, except it doesn't have the
   `docfx` prefix.

### Cross references

DocFX supports [cross references using xrefmap files](https://dotnet.github.io/docfx/tutorial/links_and_cross_references.html#using-cross-reference).
Each file maps a UID to the URL for that object. The xref map files are
automatically generated when DocFX generates docs. One generation job can refer
to other xref map files to be able to link to those objects.

Here's how it works in `doc-pipeline`:

1. When we convert the YAML to HTML, we upload two things:
   1. The resulting HTML content (in a tarball).
   1. The xref map file to the `xrefs` directory of the bucket. You can see them
      all using `gsutil ls gs://docs-staging-v2/xrefs`.
1. You can use the `xref-services` argument for `docuploader create-metadata`
   to refer to
   [cross reference services](https://dotnet.github.io/docfx/tutorial/links_and_cross_references.html#cross-reference-services).
1. If one package wants to use the xref map from another `doc-pipeline` package,
   you need to configure it. Use the `xrefs` argument of `docuploader create-metadata`
   to specify the xref map files you need. Use the following format:
      * `devsite://lang/library[@version]`: If no version
        is given, the SemVer latest is used. For example,
        `devsite://dotnet/my-pkg@1.0.0` would lead to the xref
        map at `gs://docs-staging-v2/xrefs/dotnet-my-pkg-1.0.0.tar.gz.yml`.
        `devsite://dotnet/my-pkg` would get the latest version of `my-pkg`.
1. `doc-pipeline` will then download and use the specified xref maps. If an xref map cannot
   be found, a warning is logged, but the build does not fail. Because of this,
   you can generate docs that depend on each other in any order. If the dependency
   doesn't exist yet, that's OK, the next regen will pick it up.

### How to regenerate the HTML

You can regenerate all HTML by setting `FORCE_GENERATE_ALL=true` when triggering
the job.

You can regenerate the HTML for a single blob by setting
`SOURCE_BLOB=docfx-lang-pkg-version.tgz` when triggering the job.

If you want to use a different bucket than the default, set `SOURCE_BUCKET`.

## Development

### Environment variables

See `.trampolinerc` for the canonical list of relevant environment variables.

* `TESTING_BUCKET`: Set when running tests. See the Testing section.
* `SOURCE_BUCKET`: The bucket to use for regeneration. See Running locally.
* `SOURCE_BLOB`: A single blob to regenerate. Only the blob name - do not
  include `gs://` or the bucket.
* `LANGUAGE`: Regenerates all docs under specified language. For example: `LANGUAGE=dotnet`
* `FORCE_GENERATE_ALL`: Set to `true` to regenerate all docs.

### Formatting and style

Formatting is done with `black` and style is verified with `flake8`.

You can check everything is correct by running:
```
black --check docpipeline tests
flake8 docpipeline tests
```

If a file is not properly formatted, you can fix it with:
```
black docpipeline tests
```

### Testing

1. Create a testing Cloud Storage bucket (`my-bucket`).
1. Copy a service account with permission to access `my-bucket` to
   `/dev/shm/73713_docuploader_service_account`.
1. Run the following command, replacing `my-bucket` with your development bucket:
   ```
   TEST_BUCKET=my-bucket TRAMPOLINE_BUILD_FILE=./ci/run_tests.sh TRAMPOLINE_IMAGE=gcr.io/cloud-devrel-kokoro-resources/docfx TRAMPOLINE_DOCKERFILE=docfx/Dockerfile ci/trampoline_v2.sh
   ```
1. The tests upload a test DocFX YAML tarball, call the generator, and verify
   the content.

### Running locally for one package

1. Create a directory inside `doc-pipeline` (for example, `my-dir`).
1. Create a `docs.metadata` file in `my-dir`. You can copy one from [here](https://github.com/googleapis/doc-pipeline/blob/master/testdata/docs.metadata).
1. Move or copy the `.yml` files for one package to `my-dir`.
1. Run the following command, replacing `my-dir` with your directory name:
   ```
   INPUT=my-dir TRAMPOLINE_BUILD_FILE=./generate.sh TRAMPOLINE_IMAGE=gcr.io/cloud-devrel-kokoro-resources/docfx TRAMPOLINE_DOCKERFILE=docfx/Dockerfile ci/trampoline_v2.sh
   ```
1. The script runs `docfx build` over the package in my-dir, and places the
   resulting HTML inside a subdirectory in `my-dir`. The subdirectory is
   named after the package name found in the metadata.
1. Note: running through this method will skip on processing xrefs.

### Running locally with Cloud Storage bucket

1. Create a Cloud Storage bucket and add a `docfx-*.tgz` file. For example:
   ```
   gsutil cp gs://docs-staging-v2-staging/docfx-nodejs-scheduler-2.1.1.tar.gz gs://my-bucket
   ```
1. Copy a service account with permission to access `my-bucket` to
   `/dev/shm/73713_docuploader_service_account`.
1. Run the following command, replacing `my-bucket` with your development bucket:
   ```
   SOURCE_BUCKET=my-bucket TRAMPOLINE_BUILD_FILE=./generate.sh TRAMPOLINE_IMAGE=gcr.io/cloud-devrel-kokoro-resources/docfx TRAMPOLINE_DOCKERFILE=docfx/Dockerfile ci/trampoline_v2.sh
   ```
1. The script downloads the tarball, runs `docfx build`, and uploads the result.
1. You can download the resulting HTML `.tgz` file, unpack it, inspect a few
   files (you should see `<html devsite="">` at the top), and try staging it to
   confirm it looks OK.
