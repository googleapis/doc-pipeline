// Copyright 2021 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package main

import (
	"bytes"
	"testing"
)

func TestTrimVersion(t *testing.T) {
	tests := []struct {
		name    string
		want    string
		wantErr bool
	}{
		{
			name:    "go-my-pkg-1.0.0.tar.gz",
			want:    "go-my-pkg",
			wantErr: false,
		},
		{
			name:    "go-my-pkg-1.0.tar.gz",
			wantErr: true,
		},
	}

	for _, test := range tests {
		got, err := trimVersion(test.name)
		if got != test.want {
			t.Errorf("%q got %q, want %q", test.name, got, test.want)
		}
		if test.wantErr {
			if err == nil {
				t.Errorf("%q got nil error, want an error", test.name)
			}
		} else {
			if err != nil {
				t.Errorf("%q got err %v, want no error", test.name, err)
			}
		}
	}
}

func TestWriteRobots(t *testing.T) {
	excludes := []string{"go-two", "go-one", "java-three", "java-four"}
	buf := &bytes.Buffer{}
	if err := writeRobots(buf, excludes); err != nil {
		t.Fatalf("writeRobots(%v) got err: %v", excludes, err)
	}
	want := `User-agent: *
Disallow: /go/one/
Disallow: /go/two/
Disallow: /java/four/
Disallow: /java/three/
`
	if got := buf.String(); got != want {
		t.Errorf("writeRobots(%v) got\n%v\nWant\n%v", excludes, got, want)
	}
}
