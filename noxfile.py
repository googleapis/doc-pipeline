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

import nox


@nox.session(python='3.8')
def blacken(session):
    session.install('black')
    session.run('black', 'docpipeline', 'tests')


@nox.session(python='3.8')
def lint(session):
    session.install('flake8', 'black')
    session.run('pip', 'install', '-e', '.')
    session.run('black', '--check', 'docpipeline', 'tests')
    session.run('flake8', 'docpipeline', 'tests')


@nox.session(python='3.8')
def test(session):
    session.install('pytest', 'pytest-cov')
    session.run('pip', 'install', '-e', '.')
    session.run('pytest', '--cov-report', 'term-missing', '--cov', 'docpipeline',
                'tests', *session.posargs)
