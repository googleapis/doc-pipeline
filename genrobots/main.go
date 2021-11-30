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

// Command genrobots generates a robots.txt file for the given buckets.
package main

import (
	"context"
	"flag"
	"fmt"
	"io"
	"log"
	"os"
	"regexp"
	"sort"
	"strings"

	"cloud.google.com/go/storage"
	"google.golang.org/api/iterator"
)

// versionRE matches versions of libraries. Examples:
//    rev1234-2.3.4
//    v1.0.0
//    0.1.2
//    HEAD
var versionRE = regexp.MustCompile(`(rev\d+-)?v?(\d+\.\d+\.\d+|HEAD)`)

func main() {
	googleapisBucketName := flag.String("gbucket", "", "googleapis.dev bucket name")
	cgcBucketName := flag.String("cgcbucket", "", "c.g.c. bucket name")
	robotsFilename := "robots.txt"

	flag.Parse()

	if *googleapisBucketName == "" {
		log.Fatal("must set -gbucket")
	}
	if *cgcBucketName == "" {
		log.Fatal("must set -cgcbucket")
	}

	ctx := context.Background()

	client, err := storage.NewClient(ctx)
	if err != nil {
		log.Fatalf("failed to create storage client: %v", err)
	}
	defer client.Close()

	googleapisBucket := client.Bucket(*googleapisBucketName)
	googleapisPkgs, err := names(ctx, googleapisBucket)
	if err != nil {
		log.Fatal(err)
	}

	cgcBucket := client.Bucket(*cgcBucketName)
	cgcPkgs, err := names(ctx, cgcBucket)
	if err != nil {
		log.Fatal(err)
	}

	excludeInRobots := []string{}
	for name := range googleapisPkgs {
		if _, ok := cgcPkgs[name]; ok {
			excludeInRobots = append(excludeInRobots, name)
		}
	}
	f, err := os.OpenFile(robotsFilename, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0664)
	if err != nil {
		log.Fatal(err)
	}
	defer f.Close()
	if err := writeRobots(f, excludeInRobots); err != nil {
		log.Fatal(err)
	}
}

func names(ctx context.Context, bucket *storage.BucketHandle) (map[string]struct{}, error) {
	names := map[string]struct{}{}
	it := bucket.Objects(ctx, nil)
	for {
		obj, err := it.Next()
		if err == iterator.Done {
			break
		}
		if err != nil {
			return nil, err
		}
		if strings.HasPrefix(obj.Name, "docfx") || strings.HasPrefix(obj.Name, "xrefs") {
			continue
		}
		if !strings.HasPrefix(obj.Name, "dotnet") &&
			!strings.HasPrefix(obj.Name, "go") &&
			!strings.HasPrefix(obj.Name, "java") &&
			!strings.HasPrefix(obj.Name, "nodejs") &&
			!strings.HasPrefix(obj.Name, "python") {
			continue
		}
		name, err := trimVersion(obj.Name)
		if err != nil {
			return nil, err
		}
		names[name] = struct{}{}
	}
	return names, nil
}

func writeRobots(w io.Writer, excludes []string) error {
	fmt.Fprintf(w, "User-agent: *\n")

	sort.Strings(excludes)

	for _, exclude := range excludes {
		parts := strings.SplitN(exclude, "-", 2)
		lang := parts[0]
		pkg := parts[1]
		fmt.Fprintf(w, "Disallow: /%s/%s/\n", lang, pkg)
	}
	return nil
}

func trimVersion(name string) (string, error) {
	match := versionRE.FindStringIndex(name)
	if match == nil {
		return "", fmt.Errorf("invalid name: %q", name)
	}

	return name[:match[0]-1], nil
}
