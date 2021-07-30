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
	"errors"
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
	"sync/atomic"
	"time"

	"cloud.google.com/go/storage"
	"github.com/cheggaaa/pb/v3"
	"golang.org/x/sync/errgroup"
	"golang.org/x/sync/semaphore"
	"google.golang.org/api/iterator"
)

var langFunctions = map[string]string{
	"dotnet": "https://us-central1-jonskeet-integration-tests.cloudfunctions.net/canonicalize-link",
	"nodejs": "https://us-central1-cloud-rad-canonical.cloudfunctions.net/canonicalizeLink",
	"java":   "https://us-west2-tbp-samples.cloudfunctions.net/canonicalize-java-link",
}

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
	lang := flag.String("lang", "", "the language to process")
	inBucket := flag.String("inbucket", "", "the input bucket")
	outBucket := flag.String("outbucket", "", "the output bucket")
	processEverything := flag.Bool("f", false, "process every tarball")

	cpuprofile := flag.String("cpuprofile", "", "write cpu profile to file")
	memprofile := flag.String("memprofile", "", "write memory profile to this file")

	flag.Parse()

	if _, ok := langFunctions[*lang]; !ok {
		langs := []string{}
		for l := range langFunctions {
			langs = append(langs, l)
		}
		log.Fatalf("Must set supported -lang: one of %q", langs)
	}
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

	err := processBucket(ctx, *lang, *inBucket, *outBucket, *processEverything)

	if *memprofile != "" {
		f, err := os.Create(*memprofile)
		if err != nil {
			log.Fatal(err)
		}
		runtime.GC() // get up-to-date statistics
		pprof.WriteHeapProfile(f)
		f.Close()
	}

	if err != nil {
		fmt.Println("error processing bucket:", err)
		return
	}
}

// processBucket processes all tarballs in the given bucket
// and stores the output in the output bucket.
// If processEverything is false, only new tarballs will be processed.
func processBucket(ctx context.Context, lang, inBucketName, outBucketName string, processEverything bool) error {
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

	allInputs, err := objects(ctx, inBucket, lang)
	if err != nil {
		return err
	}

	existingOutputs, err := objects(ctx, outBucket, lang)
	if err != nil {
		return err
	}

	var inputs []string
	for name := range allInputs {
		if processEverything || !existingOutputs[name] {
			inputs = append(inputs, name)
		}
	}

	if len(inputs) == 0 {
		log.Println("Nothing to do. Add -f flag?")
		return nil
	}

	bar := pbTemplate.Start(len(inputs)).Set("prefix", "Canonicalizing... ").SetRefreshRate(time.Second)
	defer bar.Finish()

	g, ctx := errgroup.WithContext(ctx)
	sem := semaphore.NewWeighted(500)

	for _, name := range inputs {
		if err := ctx.Err(); ctx.Err() != nil {
			log.Println(err)
			break
		}

		if err := sem.Acquire(ctx, 1); err != nil {
			log.Println(err)
			break
		}

		// Capture for loop variable.
		name := name

		g.Go(func() error {
			defer bar.Increment()
			defer sem.Release(1)

			return processTarball(ctx, inBucket, outBucket, lang, name, bar)
		})
	}
	if err := g.Wait(); err != nil {
		return err
	}

	return nil
}

var numFiles int64

// processTarball processes the given tarball in the given bucket.
// The progress bar is updated with the number of files processed as a prefix.
func processTarball(ctx context.Context, inBucket, outBucket *storage.BucketHandle, lang, name string, bar *pb.ProgressBar) (outErr error) {
	// cancelWrite can be used to abort the operation.
	// For example, in case there are no updates to make to the tarball.
	ctx, cancelWrite := context.WithCancel(ctx)
	defer cancelWrite()
	pkg := parsePkg(name)

	obj := inBucket.Object(name)

	// Storage reader
	//   -> un-gzip
	//     -> un-tar
	//       -> process
	//     -> tar
	//   -> gzip
	// -> Storage writer.
	r, err := obj.NewReader(ctx)
	if err != nil {
		return fmt.Errorf("unable to read from gs://%s/%s: %v", obj.BucketName(), name, err)
	}
	defer r.Close()

	gr, err := gzip.NewReader(r)
	if err != nil {
		return fmt.Errorf("gzip.NewReader: %v", err)
	}
	defer gr.Close()
	tr := tar.NewReader(gr)

	outObj := outBucket.Object(name)
	ow := outObj.NewWriter(ctx)
	defer func() {
		if err := ow.Close(); err != nil && !errors.Is(err, context.Canceled) {
			outErr = fmt.Errorf("ow.Close: %w", err)
		}
	}()

	gw := gzip.NewWriter(ow)
	defer gw.Close()
	tw := tar.NewWriter(gw)
	defer tw.Close()

	// tarballModified keeps track of if we've actually inserted a canonical
	// link somewhere in the tarball. If not, no need to write the result back
	// to Cloud Storage.
	tarballModified := false

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

		// Don't use a bufio.Scanner due to large lines.
		br := bufio.NewReader(tr)
		// Write to a buffer so we can get the new number of bytes for the record.
		out := &bytes.Buffer{}

		// foundCanonical and inHead keep track of where we are, naively,
		// in the HTML file.
		foundCanonical := false
		inHead := false

		filename := hdr.Name[len("./"):]

		// Copy the start of the file, until </head>. If needed,
		// a canonical link is inserted.
		//
		// Note: this does not preserve line endings.
		// You can `diff --ignore-space-change` to verify there
		// are no changes to content.
		for {
			// Read as bytes to avoid an unnecessary string allocation.
			text, err := br.ReadBytes('\n')
			if errors.Is(err, io.EOF) {
				out.Write(text)
				break
			}
			if err != nil {
				return fmt.Errorf("unable to ReadBytes: %v", err)
			}

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
					link, err := canonicalLink(ctx, lang, pkg, filename)
					if err != nil {
						return fmt.Errorf("canonicalLink: %v", err)
					}
					// Skip files without a canonical link.
					if link != "" {
						fmt.Fprintf(out, "    <link rel=\"canonical\" href=%q/>\n", link)
						foundCanonical = true
						tarballModified = true
					}
				}
				inHead = false

				out.Write(text)
				fmt.Fprintln(out) // Text does not have a newline. Add one.
				break             // Nothing left to do.
			}

			// Have not seen </head> yet.
			out.Write(text)
			fmt.Fprintln(out) // Text does not have a newline. Add one.
		}

		// Copy the rest of the file.
		if _, err := io.Copy(out, br); err != nil {
			return fmt.Errorf("io.Copy: %v", err)
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

	if !tarballModified {
		// We didn't modify anything, so don't write anything.
		cancelWrite()
	}

	return nil
}

// parsePkg gets the package name from the tarball name.
func parsePkg(tarballName string) string {
	name := tarballName[strings.Index(tarballName, "-")+1:] // Discard lang prefix.
	name = name[:strings.Index(name, "-")]                  // Discard after first remaining -.
	return name
}

// canonicalLink returns the canonical link for the given package and page.
func canonicalLink(ctx context.Context, lang, pkg, page string) (string, error) {
	q := url.Values{
		"package": []string{pkg},
		"page":    []string{page},
	}
	u, err := url.Parse(langFunctions[lang])
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
	if resp.StatusCode != 200 {
		return "", fmt.Errorf("%v: status: %v", u.String(), resp.Status)
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
func objects(ctx context.Context, bucket *storage.BucketHandle, lang string) (map[string]bool, error) {
	objs := map[string]bool{}
	q := &storage.Query{Prefix: lang + "-"}
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
