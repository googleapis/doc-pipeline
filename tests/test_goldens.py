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

from pathlib import Path
import difflib
import filecmp
import os
import shutil

from docpipeline import local_generate

import pytest


@pytest.mark.parametrize("test_dir", ["go"])
def test_goldens(update_goldens, tmpdir, test_dir):
    input_dir = Path("testdata") / test_dir
    output_dir = Path(tmpdir)
    golden_dir = Path("testdata/goldens") / test_dir

    local_generate.build_local_doc(input_dir, output_dir=output_dir)

    if update_goldens:
        shutil.rmtree(golden_dir, ignore_errors=True)
        shutil.copytree(output_dir, golden_dir, dirs_exist_ok=True)
        pytest.skip(
            "Updated goldens! Re-run the test without the --update-goldens flag."
        )

    got_files = [os.path.relpath(f, output_dir) for f in output_dir.glob("**/*")]
    golden_files = [os.path.relpath(f, golden_dir) for f in golden_dir.glob("**/*")]

    nl = "\n"
    extra = "Extra:\n" + "\n+ ".join([f for f in got_files if f not in golden_files])
    missing = "Missing:\n" + "\n- ".join(
        [f for f in golden_files if f not in got_files]
    )

    assert len(got_files) == len(
        golden_files
    ), f"got {len(got_files)} files, want {len(golden_files)}:{nl}{extra}{nl}{missing}"

    (eq, neq, other) = filecmp.cmpfiles(
        output_dir, golden_dir, got_files, shallow=False
    )
    other = [(output_dir / f).as_posix() for f in other]

    if other:
        pytest.fail(f"found unknown files (should never happen): {other}")
    if neq:
        diff = ""
        for f in neq:
            with open(output_dir / f) as out:
                with open(golden_dir / f) as gold:
                    out_lines = out.readlines()
                    gold_lines = gold.readlines()
                    diff = "\n" + "\n".join(
                        difflib.context_diff(
                            gold_lines,
                            out_lines,
                            fromfile=str(golden_dir / f),
                            tofile=str(output_dir / f),
                        )
                    )

        pytest.fail(f"got files that don't match goldens: {diff}")
