# Google Cloud Platform document pipeline

## Formatting and style

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

## Testing

1. Create a testing Cloud Storage bucket (`my-bucket`).
1. Copy a service account with permission to access `my-bucket` to
   `/dev/shm/73713_docuploader_service_account`.
1. Run the following command, replacing `my-bucket` with your development bucket:
   ```
   TEST_BUCKET=my-bucket TRAMPOLINE_BUILD_FILE=./ci/run_tests.sh TRAMPOLINE_IMAGE=gcr.io/cloud-devrel-kokoro-resources/docfx TRAMPOLINE_DOCKERFILE=docfx/Dockerfile ci/trampoline_v2.sh
   ```
1. The tests upload a test DocFX YAML tarball, call the generator, and verify
   the content.

## Running locally

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