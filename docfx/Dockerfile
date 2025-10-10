# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Use the official Python 3.12 image based on Debian Bookworm
FROM python:3.12

# Set environment variables
# DEBIAN_FRONTEND=noninteractive prevents interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
# DOCFX_VERSION can be overridden at build time
ARG DOCFX_VERSION=v2.58

# Install system dependencies, Mono, and clean up in a single layer
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gnupg \
        ca-certificates \
        wget \
        zip \
        git \
        apt-transport-https \
        dirmngr && \
    # Add the Mono repository key securely
    wget -qO - "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x3FA7E0328081BFF6A14DA29AA6A19B38D3D831EF" | gpg --dearmor -o /usr/share/keyrings/mono-official-archive-keyring.gpg && \
    # Add the Mono repository using the correct name 'stable-buster'
    echo "deb [signed-by=/usr/share/keyrings/mono-official-archive-keyring.gpg] https://download.mono-project.com/repo/debian stable-buster main" > /etc/apt/sources.list.d/mono-official-stable.list && \
    # Update package lists and install Mono
    apt-get update && \
    apt-get install -y --no-install-recommends \
        mono-complete \
        ca-certificates-mono && \
    # Clean up to reduce image size
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/docfx && \
    wget https://github.com/dotnet/docfx/releases/download/${DOCFX_VERSION}/docfx.zip -O /opt/docfx/docfx.zip && \
    unzip /opt/docfx/docfx.zip -d /opt/docfx && \
    rm /opt/docfx/docfx.zip

# Create a shell wrapper for docfx
RUN echo '#!/bin/bash' > /opt/docfx/docfx && \
    echo 'exec mono /opt/docfx/docfx.exe "$@"' >> /opt/docfx/docfx && \
    chmod +x /opt/docfx/docfx

# Install Google Cloud SDK and clean up in a single layer
RUN wget https://dl.google.com/dl/cloudsdk/release/google-cloud-sdk.tar.gz -O /tmp/google-cloud-sdk.tar.gz && \
    mkdir -p /usr/local/gcloud && \
    tar -xvf /tmp/google-cloud-sdk.tar.gz -C /usr/local/gcloud && \
    rm /tmp/google-cloud-sdk.tar.gz && \
    /usr/local/gcloud/google-cloud-sdk/install.sh --quiet

# Set the PATH environment variable to include all new executables
ENV PATH="${PATH}:/opt/docfx:/usr/local/gcloud/google-cloud-sdk/bin"
