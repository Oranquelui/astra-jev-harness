package main

import (
	"bytes"
	"strings"
	"testing"
)

func TestProtocolContinuesAfterErrorAndExitsNonzero(t *testing.T) {
	var out bytes.Buffer
	code := run(strings.NewReader("{\"op\":\"unknown\"}\n{\"op\":\"hash\",\"value\":{}}\n"), &out)
	lines := strings.Split(strings.TrimSpace(out.String()), "\n")
	if code != 2 || len(lines) != 2 || !strings.Contains(lines[0], `"status": "error"`) || !strings.Contains(lines[1], `"canonical_json": "{}"`) {
		t.Fatalf("%d %s", code, out.String())
	}
}

func TestProtocolRejectsOversizedInput(t *testing.T) {
	var out bytes.Buffer
	if code := run(strings.NewReader(strings.Repeat("x", 2_000_001)), &out); code != 2 || !strings.Contains(out.String(), "exceeds limit") {
		t.Fatal(code, out.String())
	}
}
