# Copyright 2021 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import yaml
from docuploader import log
from bs4 import BeautifulSoup


def prepare_java_toc(toc_file, product_name):
    with open(toc_file, "r") as yml_input:
        try:
            toc = yaml.safe_load(yml_input)

            # sort list of dict on dict key 'uid' value
            toc.sort(key=lambda x: x.get("uid"))

            # include index.md overview page
            overview = [{"name": "Overview", "href": "index.md"}]
            toc = overview + toc

            # include product level hierarchy
            toc = [{"name": product_name, "items": toc}]

            with open(toc_file, "w") as f:
                # Add back necessary docfx comment YamlMime
                f.write("### YamlMime:TableOfContent\n")

                yaml.dump(toc, f, default_flow_style=False, sort_keys=False)

        except yaml.YAMLError as e:
            log.error("Error parsing java toc file")
            raise e


def prepare_html(output_path):
    files = output_path.glob("**/*.html")
    # Handle files in binary to avoid line endings
    # being changed when running on Windows.

    for file in files:
        soup = BeautifulSoup(open(file), "html.parser")
        add_prettyprint(soup)
        add_inherited_members_drowdown(soup)

        with open(file, "w") as f:
            f.write(str(soup.prettify(formatter=None)))


def add_prettyprint(soup):
    # adds 'prettyprint' class to <code class="lang-*"></code>
    for code in soup.select('code[class*="lang-"]'):
        code["class"] = code.get("class", []) + ["prettyprint"]


def add_inherited_members_drowdown(soup):
    # https://developers.google.com/devsite/reference/widgets/expandable
    # wraps 'inheritedMembers' in devsite-expandable tag
    for div in soup.find_all("div", {"class": "inheritedMembers"}, limit=1):
        div.wrap(soup.new_tag("devsite-expandable"))

    # adds 'showalways' class to Inherited Members h5
    for h5 in soup.find_all("h5", string="Inherited Members"):
        h5["class"] = "showalways"
