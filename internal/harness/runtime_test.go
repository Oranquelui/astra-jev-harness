package harness

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func fixtureRepo(t *testing.T) (string, string) {
	t.Helper()
	root := t.TempDir()
	repo := filepath.Join(root, "repo")
	need(os.Mkdir(repo, 0700) == nil, "fixture mkdir")
	run := func(args ...string) {
		t.Helper()
		c := exec.Command("git", append([]string{"-C", repo}, args...)...)
		if out, err := c.CombinedOutput(); err != nil {
			t.Fatalf("git: %v %s", err, out)
		}
	}
	run("init", "-q")
	run("config", "user.email", "fixture@example.invalid")
	run("config", "user.name", "Fixture")
	files := map[string]string{"AGENTS.md": "Preserve contracts.\n", "src/app.py": "from pkg import value\nprint(value)\n", "src/pkg/__init__.py": "from .values import value\n", "src/pkg/values.py": "value = 42\n", "noise.txt": "unrelated\n"}
	for p, s := range files {
		target := filepath.Join(repo, p)
		need(os.MkdirAll(filepath.Dir(target), 0700) == nil, "fixture mkdir")
		writeBytes(target, []byte(s), 0644)
	}
	run("add", ".")
	run("commit", "-qm", "fixture")
	return repo, root
}
func reject(t *testing.T, fn func()) {
	t.Helper()
	if guarded(fn) == nil {
		t.Fatal("operation should reject")
	}
}
func cachedPlan(t *testing.T) (*Runtime, string, string, M) {
	repo, root := fixtureRepo(t)
	planDir := filepath.Join(root, "plan")
	p := hostMakePlan("desktop", repo, "Implement src/app.py value behavior", planDir, []string{}, []string{}, 4)
	cache := filepath.Join(root, "cache")
	cat := units(p)
	for _, b := range batches(p) {
		payload := jevPayload(p, b, cat)
		a := M{}
		for k := range obj(payload, "questions") {
			a[k] = M{"type": "noul", "noul": .9}
		}
		writeCache(payload, M{"model": jevModel, "answers": a}, cache)
	}
	r := New("")
	r.credential = func() (string, string) { t.Fatal("cache hit must not access credentials"); return "", "" }
	return r, root, cache, p
}
func TestNativeHostCachedWorkflowAndFreshness(t *testing.T) {
	r, root, cache, p := cachedPlan(t)
	dir := filepath.Join(root, "selected")
	record := r.hostSelect("desktop", filepath.Join(root, "plan"), dir, "batch", cache, "", "jev", 4, true)
	if integer(record["attempted_calls"]) != 0 || integer(callCounts(record)["jev_reused_calls"]) == 0 {
		t.Fatal("cache accounting")
	}
	hostCheck("desktop", dir, true)
	read := hostRead("desktop", dir, "src/app.py", 1, 2, true)
	if !strings.Contains(str(read["text"]), "from pkg") {
		t.Fatal(read)
	}
	page := hostPresent("desktop", dir, 1024, 0, 12)
	if len(spaced(page))+1 > 1024 {
		t.Fatal("view budget")
	}
	hostCompare("desktop", dir, []string{"src/app.py"})
	reject(t, func() { hostCheck("claude-code", dir, true) })
	writeBytes(filepath.Join(str(p["repo"]), "src/pkg/values.py"), []byte("value = 43\n"), 0644)
	reject(t, func() { hostCheck("desktop", dir, true) })
}
func TestNativeBudgetsAndJevRequiredBeforeCredentialOrWrite(t *testing.T) {
	r, root, _, _ := cachedPlan(t)
	for _, mode := range []string{"local", "auto"} {
		out := filepath.Join(root, "out-"+mode)
		reject(t, func() { r.hostSelect("desktop", filepath.Join(root, "plan"), out, "batch", "", "", mode, 4, true) })
		if exists(out) {
			t.Fatal("created output on rejected route")
		}
	}
	out := filepath.Join(root, "budget")
	reject(t, func() { r.hostSelect("desktop", filepath.Join(root, "plan"), out, "batch", "", "", "jev", 0, true) })
	if exists(out) {
		t.Fatal("budget checked too late")
	}
}
func TestNativePathsSecretsAndParserFallback(t *testing.T) {
	repo, root := fixtureRepo(t)
	for _, p := range []string{"../escape", "/absolute", "a/../b", "a\\b", "a//b", "a\n"} {
		reject(t, func() { safePath(repo, p) })
	}
	need(os.Symlink(root, filepath.Join(repo, "link")) == nil, "fixture symlink")
	reject(t, func() { safePath(repo, "link/file.py") })
	if eligibility(".env.example") == "" || !secret.MatchString("password='"+strings.Repeat("x", 30)+"'") {
		t.Fatal("secret guard")
	}
	files := M{"main.py": "import pkg.values as value\n", "pkg/__init__.py": "", "pkg/values.py": "value = 42", "other.py": "x=2"}
	got := dependencies(files, []string{"main.py"})
	if !contains(got, "pkg/values.py") {
		t.Fatal(got)
	}
	files["main.py"] = "def broken(:"
	if !contains(dependencies(files, []string{"main.py"}), "other.py") {
		t.Fatal("syntax error dropped dependencies")
	}
}
func TestNativeHTTPNoRetryRedirectOrBodyLeak(t *testing.T) {
	calls := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		calls++
		w.WriteHeader(503)
		fmt.Fprint(w, "secret-body-marker")
	}))
	defer server.Close()
	r := New("")
	r.endpoint = server.URL
	payload := M{"model": jevModel, "state": M{}, "questions": M{"f0": M{"type": "noul"}}}
	err := guarded(func() { r.request(payload, "fixture-key") })
	if err == nil || calls != 1 || strings.Contains(err.Error(), "secret-body-marker") {
		t.Fatal("failed request contract")
	}
	f := failure(err, "fixture")
	if f["http_status"] != 503 || f["usage"] != nil || f["automatic_retries"] != 0 {
		t.Fatal(f)
	}
	targetCalls := 0
	target := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { targetCalls++ }))
	defer target.Close()
	redirect := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { http.Redirect(w, r, target.URL, 307) }))
	defer redirect.Close()
	r.endpoint = redirect.URL
	reject(t, func() { r.request(payload, "fixture-key") })
	if targetCalls != 0 {
		t.Fatal("redirect forwarded credentials")
	}
}
func TestNativeSelectionFailureReceiptAndCacheTamper(t *testing.T) {
	r, root, cache, _ := cachedPlan(t)
	for _, entry := range must(os.ReadDir(cache)) {
		p := filepath.Join(cache, entry.Name())
		v := load(p)
		obj(v, "response")["model"] = "wrong"
		save(p, v)
	}
	reject(t, func() {
		r.hostSelect("desktop", filepath.Join(root, "plan"), filepath.Join(root, "tampered"), "batch", cache, "", "jev", 4, true)
	})
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(503) }))
	defer server.Close()
	r.endpoint = server.URL
	r.credential = func() (string, string) { return "fixture-key", "test" }
	out := filepath.Join(root, "failed")
	reject(t, func() { r.hostSelect("desktop", filepath.Join(root, "plan"), out, "batch", "", "", "jev", 4, true) })
	record := load(filepath.Join(out, "selection.json"))
	if record["status"] != "failed" || integer(record["attempted_calls"]) != 1 || len(array(record["jev_calls"])) != 0 {
		t.Fatal(record)
	}
}
func TestNativeEvidencePinnedOfflineAndTampering(t *testing.T) {
	root := t.TempDir()
	source := filepath.Join(root, "facts.txt")
	writeBytes(source, []byte("permission: only local edits\n"), 0600)
	plan := filepath.Join(root, "plan")
	evidenceMakePlan("Implement boundary", []string{}, []string{source}, plan)
	r := New("")
	r.credential = func() (string, string) { t.Fatal("pinned evidence must be offline"); return "", "" }
	out := filepath.Join(root, "selection")
	record := r.evidenceSelect(plan, out, "", 0)
	if integer(record["attempted_calls"]) != 0 {
		t.Fatal(record)
	}
	evidenceCheck(out)
	writeBytes(source, []byte("changed\n"), 0600)
	reject(t, func() { evidenceCheck(out) })
}

// Optional migration oracle, never invoked by a runtime command. All sources are
// synthetic and local; no provider or timing calls. CI supplies the interpreter.
func TestPythonArtifactCompatibility(t *testing.T) {
	python := os.Getenv("ASTRA_JEV_REFERENCE_PYTHON")
	if python == "" {
		t.Skip("optional development-only Python oracle")
	}
	repo, root := fixtureRepo(t)
	planDir := filepath.Join(root, "native")
	p := snapshot(repo, "Implement src/app.py value", planDir, []string{}, []string{}, []string{}, []string{}, 4, 2000000)
	script := `import json,sys
from shared import repo_context as r, context_chunks as c
from shared.jev import jev_request,request_hash
p=json.load(sys.stdin)
bs=r.jev_batches(p)
calls=[{'probabilities':{key: [0.1,0.5,0.9][i%3] for i,key in enumerate(b)}} for b in bs]
print(json.dumps({'units':c.units(p),'requests':[jev_request(r.selection_case(p,b)) for b in bs], 'hashes':[request_hash(jev_request(r.selection_case(p,b))) for b in bs], 'resolved':r.resolve_selection(p,calls)}))
`
	cmd := exec.Command(python, "-c", script)
	cmd.Dir = filepath.Join("..", "..")
	cmd.Env = childEnv("TYPESAFE_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY")
	cmd.Stdin = strings.NewReader(string(wire(p)))
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("oracle: %v %s", err, out)
	}
	reference := object(decode(out))
	cat := units(p)
	if hash(cat.Units) != hash(reference["units"]) {
		t.Fatal("unit mismatch")
	}
	requests := []M{}
	hashes := []string{}
	calls := []M{}
	for _, b := range batches(p) {
		request := jevPayload(p, b, cat)
		requests = append(requests, request)
		hashes = append(hashes, hash(request))
		scores := M{}
		for i, k := range b.Keys {
			scores[k] = []float64{.1, .5, .9}[i%3]
		}
		calls = append(calls, M{"probabilities": scores})
	}
	for k, v := range (M{"requests": requests, "hashes": hashes, "resolved": resolveSelection(p, calls, "batch")}) {
		if hash(v) != hash(reference[k]) {
			t.Fatalf("%s compatibility mismatch\nnative: %s\npython: %s", k, wire(v), wire(reference[k]))
		}
	}
}
