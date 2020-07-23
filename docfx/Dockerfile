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

FROM ubuntu:20.04

ENV DEBIAN_FRONTEND noninteractive
ENV PATH ${PATH}:/opt/docfx

RUN apt-get update && \
    apt-get -y install gnupg ca-certificates wget zip python3 python3-pip

# Install mono with the instructions at:
# https://www.mono-project.com/download/stable/#download-lin
RUN apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 \
    --recv-keys 3FA7E0328081BFF6A14DA29AA6A19B38D3D831EF && \
    echo "deb https://download.mono-project.com/repo/ubuntu stable-focal main" \
    | tee /etc/apt/sources.list.d/mono-official-stable.list && \
    apt-get update && \
    apt-get install -y mono-complete ca-certificates-mono

ARG DOCFX_VERSION=v2.56.1

# Install docfx
RUN mkdir -p /opt/docfx
RUN wget \
    https://github.com/dotnet/docfx/releases/download/${DOCFX_VERSION}/docfx.zip \
    -O /opt/docfx/docfx.zip && \
    cd /opt/docfx && \
    unzip docfx.zip

# A shell wrapper
RUN echo '#!/usr/bin/bash' >> /opt/docfx/docfx && \
    echo 'exec mono /opt/docfx/docfx.exe $@' >> /opt/docfx/docfx && \
    chmod 0755 /opt/docfx/docfx
