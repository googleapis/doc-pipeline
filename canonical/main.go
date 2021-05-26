// Copyright 2021 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// The canonical command processes buckets to add canonical links.
// For now, canonical only processes .NET objects.
package main

import (
	"archive/tar"
	"bufio"
	"bytes"
	"compress/gzip"
	"context"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"runtime"
	"runtime/pprof"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"cloud.google.com/go/storage"
	"github.com/cheggaaa/pb/v3"
	"golang.org/x/sync/errgroup"
	"golang.org/x/sync/semaphore"
	"google.golang.org/api/iterator"
)

const (
	dotnetPrefix  = "dotnet-"
	cloudFunction = "https://us-central1-jonskeet-integration-tests.cloudfunctions.net/canonicalize-link"
)

var (
	startHead = []byte("<head>")
	endHead   = []byte("</head>")
	canonical = []byte(`rel="canonical"`)
)

var httpClient = &http.Client{
	Timeout: 60 * time.Minute,
	Transport: &http.Transport{
		MaxIdleConnsPerHost: 512,
	},
}

var pbTemplate pb.ProgressBarTemplate = `{{string . "prefix"}} {{counters . }} {{ bar . "[" "-" (cycle . "←" "↖" "↑" "↗" "→" "↘" "↓" "↙" ) "_" "]" }} {{percent . }} {{etime . }}`

func main() {
	inBucket := flag.String("inbucket", "", "the input bucket")
	outBucket := flag.String("outbucket", "", "the output bucket")
	processEverything := flag.Bool("f", false, "process every tarball")

	cpuprofile := flag.String("cpuprofile", "", "write cpu profile to file")
	memprofile := flag.String("memprofile", "", "write memory profile to this file")

	flag.Parse()

	if *inBucket == "" {
		log.Fatal("Must provide -inbucket")
	}
	if *outBucket == "" {
		log.Fatal("Must provide -outbucket")
	}
	if *inBucket == *outBucket {
		log.Fatal("-inbucket must be different from -outbucket")
	}

	if *cpuprofile != "" {
		f, err := os.Create(*cpuprofile)
		if err != nil {
			log.Fatal(err)
		}
		defer f.Close()

		pprof.StartCPUProfile(f)
		defer pprof.StopCPUProfile()
	}

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancel()

	err := processBucket(ctx, *inBucket, *outBucket, *processEverything)

	if *memprofile != "" {
		f, err := os.Create(*memprofile)
		if err != nil {
			log.Fatal(err)
		}
		runtime.GC() // get up-to-date statistics
		pprof.WriteHeapProfile(f)
		f.Close()
		return
	}

	if err != nil {
		fmt.Println("error processing bucket:", err)
		return
	}
}

// processBucket processes all tarballs in the given bucket
// and stores the output in the output bucket.
// If processEverything is false, only new tarballs will be processed.
func processBucket(ctx context.Context, inBucketName, outBucketName string, processEverything bool) error {
	client, err := storage.NewClient(ctx)
	if err != nil {
		return fmt.Errorf("storage.NewClient: %v", err)
	}

	inBucket := client.Bucket(inBucketName)
	if _, err := inBucket.Attrs(ctx); err != nil {
		return fmt.Errorf("could not get bucket %q: %v", inBucketName, err)
	}

	outBucket := client.Bucket(outBucketName)
	if _, err := outBucket.Attrs(ctx); err != nil {
		return fmt.Errorf("could not get bucket %q: %v", outBucketName, err)
	}

	allInputs, err := objects(ctx, inBucket)
	if err != nil {
		return err
	}

	existingOutputs, err := objects(ctx, outBucket)
	if err != nil {
		return err
	}

	inputs := []string{}
	for name := range allInputs {
		if processEverything || !existingOutputs[name] {
			inputs = append(inputs, name)
		}
	}

	if len(inputs) == 0 {
		fmt.Println("Nothing to do. Add -f flag?")
		return nil
	}

	bar := pbTemplate.Start(len(inputs)).Set("prefix", "Canonicalizing... ").SetRefreshRate(time.Second)

	g, ctx := errgroup.WithContext(ctx)
	sem := semaphore.NewWeighted(500)

	for _, name := range inputs {
		if err := ctx.Err(); ctx.Err() != nil {
			bar.Finish()
			log.Println(err)
			break
		}

		if err := sem.Acquire(ctx, 1); err != nil {
			bar.Finish()
			log.Println(err)
			break
		}
		releaseOnce := &sync.Once{}

		// Capture for loop variable.
		name := name

		g.Go(func() error {
			defer bar.Increment()
			defer releaseOnce.Do(func() { sem.Release(1) })

			return processTarball(ctx, inBucket, outBucket, name, bar)
		})
	}
	if err := g.Wait(); err != nil {
		bar.Finish()
		return err
	}
	bar.Finish()

	return nil
}

var numFiles int64

// processTarball processes the given tarball in the given bucket.
// The progress bar is updated with the number of files processed as a prefix.
func processTarball(ctx context.Context, inBucket, outBucket *storage.BucketHandle, name string, bar *pb.ProgressBar) error {
	pkg := parsePkg(name)

	obj := inBucket.Object(name)

	// Storage reader -> un-gzip -> un-tar
	// -> process
	// -> tar -> gzip -> Storage writer.
	r, err := obj.NewReader(ctx)
	if err != nil {
		return fmt.Errorf("unable to read from gs://%s/%s: %v", obj.BucketName(), name, err)
	}

	gr, err := gzip.NewReader(r)
	if err != nil {
		log.Fatal(err)
	}
	tr := tar.NewReader(gr)

	outObj := outBucket.Object(name)
	ow := outObj.NewWriter(ctx)
	gw := gzip.NewWriter(ow)
	tw := tar.NewWriter(gw)

	// Loop over every header in the tarball.
	for {
		hdr, err := tr.Next()
		if err == io.EOF {
			break // End of archive
		}

		if err != nil {
			return fmt.Errorf("error reading block from gs://%s/%s: %v", obj.BucketName(), name, err)
		}

		// Don't need to do anything with directory headers.
		if hdr.FileInfo().IsDir() {
			tw.WriteHeader(hdr)
			continue
		}

		// Only process .html files.
		if !strings.HasSuffix(hdr.Name, ".html") {
			tw.WriteHeader(hdr)
			if l, err := io.Copy(tw, tr); err != nil || l != hdr.Size {
				return fmt.Errorf("error writing %q %q: wrote %v bytes: %v", name, hdr.Name, l, err)
			}
			continue
		}

		// Scanner to read every line.
		scanner := bufio.NewScanner(tr)
		// Write to a buffer so we can get the new number of bytes for the record.
		out := &bytes.Buffer{}

		// foundCanonical and inHead keep track of where we are, naively,
		// in the HTML file.
		foundCanonical := false
		inHead := false

		filename := hdr.Name[len("./"):]

		// Note: this does not preserve line endings.
		// You can `diff --ignore-space-change` to verify there
		// are no changes to content.
		for scanner.Scan() {
			// Read as bytes to avoid an unnecessary string allocation.
			text := scanner.Bytes()

			// Trim space rather than use regex.
			trimmed := bytes.TrimSpace(text)
			if bytes.Equal(trimmed, startHead) {
				inHead = true
			}

			if inHead && bytes.Contains(text, canonical) {
				foundCanonical = true
			}

			if inHead && bytes.Equal(trimmed, endHead) {
				if !foundCanonical {
					link, err := canonicalLink(ctx, pkg, filename)
					if err != nil {
						return fmt.Errorf("canonicalLink: %v", err)
					}
					fmt.Fprintf(out, "    <link rel=\"canonical\" href=%q/>\n", link)
					foundCanonical = true
				}
				inHead = false
			}

			out.Write(text)
			fmt.Fprintln(out) // Text does not have a newline. Add one.
		}
		if err := scanner.Err(); err != nil {
			return fmt.Errorf("error scanning %q %q: %v", name, hdr.Name, err)
		}

		// Update the header to have the right size. Otherwise, leave hdr unchanged.
		hdr.Size = int64(out.Len())
		tw.WriteHeader(hdr)
		if l, err := tw.Write(out.Bytes()); err != nil || l != int(hdr.Size) {
			return fmt.Errorf("error writing %q %q: wrote %v bytes: %v", name, hdr.Name, l, err)
		}

		atomic.AddInt64(&numFiles, 1)
		bar.Set("prefix", fmt.Sprintf("Canonicalizing... %d files |", numFiles))
	}

	if err := tw.Close(); err != nil {
		return fmt.Errorf("error closing tar %v: %v", name, err)
	}
	if err := gw.Close(); err != nil {
		return fmt.Errorf("error closing gzip %v: %v", name, err)
	}
	if err := ow.Close(); err != nil {
		return fmt.Errorf("error closing obj %q writer: %v", name, err)
	}

	return nil
}

// parsePkg gets the package name from the tarball name.
func parsePkg(tarballName string) string {
	name := tarballName[len(dotnetPrefix):] // Trim docfx- prefix.
	name = name[:strings.Index(name, "-")]  // Discard after first remaining -.
	return name
}

// canonicalLink returns the canonical link for the given package and page.
func canonicalLink(ctx context.Context, pkg, page string) (string, error) {
	q := url.Values{
		"package": []string{pkg},
		"page":    []string{page},
	}
	u, err := url.Parse(cloudFunction)
	if err != nil {
		return "", err
	}
	u.RawQuery = q.Encode()
	r := newRequestWithContext(ctx, http.MethodGet, u.String())
	resp, err := httpClient.Do(r)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	b, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	return string(b), nil
}

func newRequestWithContext(ctx context.Context, method, url string) *http.Request {
	req, err := http.NewRequestWithContext(ctx, method, url, nil)
	if err != nil {
		panic(err)
	}
	return req
}

// objects returns a map of object names in the bucket.
func objects(ctx context.Context, bucket *storage.BucketHandle) (map[string]bool, error) {
	objs := map[string]bool{}
	q := &storage.Query{Prefix: dotnetPrefix}
	if err := q.SetAttrSelection([]string{"Name"}); err != nil {
		return nil, err
	}
	it := bucket.Objects(ctx, q)
	for {
		attrs, err := it.Next()
		if err == iterator.Done {
			break
		}
		if err != nil {
			return nil, err
		}
		objs[attrs.Name] = true
	}
	return objs, nil
}
