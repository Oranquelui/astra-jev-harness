// Package harness implements the native runtime. Artifacts retain the published
// JSON contracts; invalid data is rejected at the command boundary.
package harness

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"unicode/utf8"

	"github.com/Oranquelui/astra-jev-harness/internal/nativecore"
)

type M = map[string]any
type fault struct {
	message    string
	diagnostic M
	partial    M
}

func (e fault) Error() string { return e.message }
func fail(s string)           { panic(fault{message: s}) }
func need(ok bool, s string) {
	if !ok {
		fail(s)
	}
}
func must[T any](v T, err error) T {
	if err != nil {
		fail("Local operation failed")
	}
	return v
}
func object(v any) M { m, ok := v.(map[string]any); need(ok, "Expected an object"); return m }
func obj(m M, k string) M {
	if m[k] == nil {
		return M{}
	}
	return object(m[k])
}
func str(v any) string { s, ok := v.(string); need(ok, "Expected a string"); return s }
func sget(m M, k string) string {
	if m[k] == nil {
		return ""
	}
	return str(m[k])
}
func array(v any) []any {
	if v == nil {
		return []any{}
	}
	switch x := v.(type) {
	case []any:
		return x
	case []string:
		r := []any{}
		for _, s := range x {
			r = append(r, s)
		}
		return r
	case []M:
		r := []any{}
		for _, s := range x {
			r = append(r, s)
		}
		return r
	}
	fail("Expected an array")
	return nil
}
func stringsOf(v any) []string {
	r := []string{}
	for _, x := range array(v) {
		r = append(r, str(x))
	}
	return r
}
func maps(v any) []M {
	r := []M{}
	for _, x := range array(v) {
		r = append(r, object(x))
	}
	return r
}
func number(v any) float64 {
	switch n := v.(type) {
	case int:
		return float64(n)
	case float64:
		return n
	case json.Number:
		return must(n.Float64())
	}
	fail("Expected a number")
	return 0
}
func integer(v any) int {
	switch n := v.(type) {
	case int:
		return n
	case json.Number:
		return must(strconv.Atoi(string(n)))
	}
	fail("Expected an integer")
	return 0
}
func flag(v any) bool {
	if v == nil {
		return false
	}
	b, ok := v.(bool)
	need(ok, "Expected boolean")
	return b
}
func keys(m M) []string {
	r := make([]string, 0, len(m))
	for k := range m {
		r = append(r, k)
	}
	sort.Strings(r)
	return r
}
func clone(m M) M {
	r := M{}
	for k, v := range m {
		r[k] = v
	}
	return r
}
func merge(ms ...M) M {
	r := M{}
	for _, m := range ms {
		for k, v := range m {
			r[k] = v
		}
	}
	return r
}
func set(xs []string) M {
	r := M{}
	for _, s := range xs {
		r[s] = true
	}
	return r
}
func contains(xs []string, s string) bool {
	for _, x := range xs {
		if x == s {
			return true
		}
	}
	return false
}
func unique(xs []string) []string { return keys(set(xs)) }
func digest(raw []byte) string    { h := sha256.Sum256(raw); return hex.EncodeToString(h[:]) }
func wire(v any) []byte           { return must(nativecore.JSON(v, false)) }
func spaced(v any) []byte         { return must(nativecore.JSON(v, true)) }
func hash(v any) string           { return digest(wire(v)) }
func decode(raw []byte) any       { return must(nativecore.Decode(raw)) }
func readBytes(p string, limit int64) []byte {
	f := must(os.Open(p))
	defer f.Close()
	info := must(f.Stat())
	need(info.Mode().IsRegular() && info.Size() <= limit, "File missing or oversized")
	b := must(os.ReadFile(p))
	need(int64(len(b)) <= limit, "File exceeds limit")
	return b
}
func readText(p string, limit int64) string {
	b := readBytes(p, limit)
	need(utf8.Valid(b), "Invalid UTF-8")
	return string(b)
}
func load(p string) M { return object(decode(readBytes(p, 40000000))) }
func writeBytes(p string, b []byte, mode os.FileMode) {
	if err := os.WriteFile(p, b, mode); err != nil {
		fail("Cannot write artifact")
	}
}
func save(p string, v any) {
	dir := filepath.Dir(p)
	f := must(os.CreateTemp(dir, ".astra-json-*"))
	name := f.Name()
	defer os.Remove(name)
	need(f.Chmod(0600) == nil, "Artifact permission failure")
	_, err := f.Write(append(wire(v), '\n'))
	closeErr := f.Close()
	need(err == nil && closeErr == nil, "Cannot save artifact")
	need(os.Rename(name, p) == nil, "Cannot replace artifact")
}
func exists(p string) bool { _, err := os.Lstat(p); return err == nil }

// Resolve symlinks even when the final path has not been created yet.
func absolute(p string) string {
	need(p != "", "Missing path")
	p = must(filepath.Abs(p))
	if exists(p) {
		return must(filepath.EvalSymlinks(p))
	}
	parent := filepath.Dir(p)
	need(parent != p, "Unresolvable path")
	return filepath.Join(absolute(parent), filepath.Base(p))
}
func within(p, root string) bool {
	rel, err := filepath.Rel(root, p)
	return err == nil && (rel == "." || rel != ".." && !strings.HasPrefix(rel, ".."+string(os.PathSeparator)) && !filepath.IsAbs(rel))
}
func newDirectory(p string) string {
	p = absolute(p)
	need(!exists(p), "Use a new output directory")
	need(os.MkdirAll(p, 0700) == nil, "Cannot create output directory")
	return p
}
func sumBytes(files M) int {
	n := 0
	for _, v := range files {
		n += integer(object(v)["bytes"])
	}
	return n
}
func contents(plan M) M {
	r := M{}
	for p, v := range obj(plan, "files") {
		r[p] = object(v)["content"]
	}
	return r
}
func guarded(fn func()) (err error) {
	defer func() {
		if p := recover(); p != nil {
			if e, ok := p.(fault); ok {
				err = e
			} else {
				panic(p)
			}
		}
	}()
	fn()
	return
}
func failure(err error, stage string) M {
	d := M{}
	if f, ok := err.(fault); ok {
		d = f.diagnostic
	}
	kind := sget(d, "error_kind")
	if kind == "" {
		kind = "local_validation"
	}
	return M{"stage": stage, "error_kind": kind, "http_status": d["http_status"], "seconds": d["seconds"], "request_sha256": d["request_sha256"], "usage": nil, "usage_status": "unknown", "automatic_retries": 0}
}
func fmtJSON(v any) string          { return string(spaced(v)) }
func report(dir, name, text string) { writeBytes(filepath.Join(dir, name), []byte(text), 0600) }
func taskValid(task string) {
	need(strings.TrimSpace(task) != "" && len(task) <= 4000 && !isSecret(task), "Invalid or credential-like task")
}
func fieldName(prefix string, i int) string { return fmt.Sprintf("%s%d", prefix, i) }

func readTask(p string) string {
	return strings.ReplaceAll(strings.ReplaceAll(readText(p, 4000), "\r\n", "\n"), "\r", "\n")
}
