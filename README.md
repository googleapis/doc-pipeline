# Google Cloud Platform document pipeline

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