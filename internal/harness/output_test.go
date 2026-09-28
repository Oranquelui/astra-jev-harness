package harness

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestNativeOutputPreservesFailureAndCredentials(t *testing.T) {
	r := New("")
	r.credential = func() (string, string) { t.Fatal("must not read credentials"); return "", "" }
	root := t.TempDir()
	var out, stderr bytes.Buffer
	t.Setenv("TYPESAFE_API_KEY", "fixture-secret")
	code := r.runOutput([]string{"/bin/sh", "-c", "test -z \"${TYPESAFE_API_KEY-}\" || exit 9; printf 'original stdout'; printf 'original stderr' >&2; exit 7"}, "Build project", filepath.Join(root, "output"), []string{}, 2, "jev", &out, &stderr)
	if code != 7 || out.String() != "original stdout" || stderr.String() != "original stderr" {
		t.Fatalf("%d %s %s", code, &out, &stderr)
	}
	if exists(filepath.Join(root, "output")) {
		t.Fatal("failed command caused API artifacts")
	}
	for _, text := range []string{"token=fixture-secret", "authorization: Bearer fixture", "progress one\x1b[0m\n"} {
		raw := []byte(text)
		visible, record := r.selectOutput(raw, "Build project", filepath.Join(root, "skipped"), []string{}, 2, "jev", func() bool { return false })
		if !bytes.Equal(raw, visible) || integer(record["attempted_calls"]) != 0 {
			t.Fatal(record)
		}
	}
}
func TestNativeOutputOneExecutionArchiveAndFailureFallback(t *testing.T) {
	r := New("")
	root := t.TempDir()
	calls := 0
	failHTTP := false
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		calls++
		if failHTTP {
			w.WriteHeader(503)
			return
		}
		raw, _ := io.ReadAll(req.Body)
		p := object(decode(raw))
		answers := M{}
		for k := range obj(p, "questions") {
			answers[k] = M{"type": "noul", "noul": .01}
		}
		fmt.Fprint(w, string(wire(M{"model": jevModel, "answers": answers, "usage": M{"input_tokens": 10, "output_tokens": 1}})))
	}))
	defer server.Close()
	r.endpoint = server.URL
	r.credential = func() (string, string) { return "fixture-key", "test" }
	raw := []byte("Build start\n" + strings.Repeat("progress fetching dependency\n", 600) + "tests passed\n")
	out := filepath.Join(root, "selected")
	visible, record := r.selectOutput(raw, "Build project", out, []string{}, 2, "jev", func() bool { return false })
	if len(visible) >= len(raw) || !bytes.Contains(visible, []byte("tests passed")) || calls < 1 || calls > 2 {
		t.Fatal(record)
	}
	if !bytes.Equal(readBytes(filepath.Join(out, "stdout.txt"), 2000000), raw) {
		t.Fatal("archive lost original")
	}
	info := must(os.Stat(filepath.Join(out, "stdout.txt")))
	if info.Mode().Perm() != 0600 {
		t.Fatal(info.Mode())
	}
	calls = 0
	failHTTP = true
	visible, record = r.selectOutput(raw, "Build project", filepath.Join(root, "failed"), []string{}, 2, "jev", func() bool { return false })
	if !bytes.Equal(raw, visible) || calls != 1 || record["reason"] != "provider_failure" {
		t.Fatal(record)
	}
}
func TestNativeOutputStreamingLimitAndArgumentValidation(t *testing.T) {
	r := New("")
	r.credential = func() (string, string) { t.Fatal("oversized output called provider"); return "", "" }
	root := t.TempDir()
	var out, stderr bytes.Buffer
	code := r.runOutput([]string{"/usr/bin/head", "-c", "2000001", "/dev/zero"}, "Build project", filepath.Join(root, "large"), []string{}, 2, "jev", &out, &stderr)
	if code != 0 || out.Len() != 2000001 || exists(filepath.Join(root, "large")) {
		t.Fatal(code, out.Len())
	}
	marker := filepath.Join(root, "ran")
	reject(t, func() {
		r.runOutput([]string{"/usr/bin/touch", marker}, "", filepath.Join(root, "bad"), []string{}, 2, "jev", &out, &stderr)
	})
	if exists(marker) {
		t.Fatal("invalid options executed command")
	}
}
func TestNativeUsageUnknownAndDecimalPrices(t *testing.T) {
	root := t.TempDir()
	p := filepath.Join(root, "receipt.json")
	save(p, M{"surface": "desktop", "status": "selected", "attempted_calls": 2, "jev_calls": []M{{"model": jevModel, "usage": M{"input_tokens": 10, "output_tokens": 2}}}, "seconds": 1})
	s := summarize([]string{p, p}, M{jevModel: M{"input": "0.04", "output": "0.10"}})
	if integer(s["record_count"]) != 1 || obj(s, "astra")["attempted_calls"] != nil || flag(obj(s, "jev")["complete_usage"]) || s["dollar_cost"] != nil {
		t.Fatal(s)
	}
	cost := obj(obj(s, "cost_estimates"), "jev")
	if cost["known_subtotal_usd"] != "0.0000006" || cost["estimated_usd"] != nil {
		t.Fatal(cost)
	}
	save(p, M{"kind": "unrecognized", "seconds": 1000})
	if summarize([]string{p}, nil)["summed_run_seconds"] != nil {
		t.Fatal("unknown receipt supplied duration")
	}
	r, w, o := cacheCounts(M{"input_tokens": 100, "cached_input_tokens": 60, "input_tokens_details": M{"cached_tokens": 50}, "cache_write_tokens": 0})
	if r != nil || w != 0 || o != nil {
		t.Fatal("conflicting cache aliases accepted")
	}
	reject(t, func() { validatePrices(M{jevModel: M{"input": "NaN"}}) })
}

func TestNativeNullCallListNeverBecomesFreeUsage(t *testing.T) {
	n := normalizeRecord(M{"kind": "tool-output", "version": 1, "attempted_calls": 0, "calls": nil})
	if n["jcount"] != nil || flag(providerSummary(maps(n["jev"]), n["jcount"], false)["complete_usage"]) {
		t.Fatal("null calls became complete zero spend")
	}
}
