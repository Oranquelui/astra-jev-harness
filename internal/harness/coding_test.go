package harness

import (
	"bytes"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func fakeCodex(t *testing.T, root, answer string) string {
	t.Helper()
	bin := filepath.Join(root, "fake-bin")
	need(os.MkdirAll(bin, 0700) == nil, "fixture mkdir")
	script := `#!/bin/sh
if [ -n "${TYPESAFE_API_KEY-}${OPENAI_API_KEY-}${CODEX_API_KEY-}" ]; then exit 91; fi
case "$1" in
app-server)
 IFS= read -r line
 printf '%s\n' '{"id":1,"result":{}}'
 IFS= read -r line
 IFS= read -r line
 printf '%s\n' '{"id":2,"result":{"config":{"model":"configured-model","model_reasoning_effort":"high"}}}'
 ;;
exec)
 while [ "$#" -gt 0 ]; do
  if [ "$1" = '--output-last-message' ]; then shift; answer_file=$1; fi
  shift
 done
 cat >/dev/null
 cat >"$answer_file" <<'ANSWER'
` + answer + `
ANSWER
 printf '%s\n' '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":2}}'
 ;;
sandbox) exit 0 ;;
*) exit 92 ;;
esac
`
	writeBytes(filepath.Join(bin, "codex"), []byte(script), 0700)
	return bin
}
func TestNativeCLIFromConfiguredModelThroughExplicitApply(t *testing.T) {
	repo, root := fixtureRepo(t)
	planDir := filepath.Join(root, "plan")
	snapshot(repo, "Update src/pkg/values.py value", planDir, []string{}, []string{}, []string{"new/added.py"}, []string{}, 4, 350000)
	bin := fakeCodex(t, root, `{"summary":"Update value","needs_context":[],"files":[{"path":"src/pkg/values.py","content":"value = 43\n"},{"path":"new/added.py","content":"created = True\n"}]}`)
	t.Setenv("PATH", bin+string(os.PathListSeparator)+os.Getenv("PATH"))
	t.Setenv("TYPESAFE_API_KEY", "must-not-reach-child")
	t.Setenv("OPENAI_API_KEY", "must-not-reach-child")
	r := New("")
	r.credential = func() (string, string) { t.Fatal("astra route must not access Jev credentials"); return "", "" }
	dir := filepath.Join(root, "run")
	result := r.codingRun(planDir, dir, "astra", "", "", []string{"fixture-test"}, 5)
	if result["status"] != "verified" {
		t.Fatal(result)
	}
	if readText(filepath.Join(repo, "src/pkg/values.py"), 100000) != "value = 42\n" || exists(filepath.Join(repo, "new/added.py")) {
		t.Fatal("run mutated original")
	}
	if obj(result, "model_settings")["model"] != "configured-model" || len(array(result["astra_calls"])) != 1 {
		t.Fatal("configured model was lost")
	}
	reverify(dir, 5)
	applied := applyRun(dir)
	if applied["status"] != "applied" || !exists(filepath.Join(repo, "new/added.py")) {
		t.Fatal(applied)
	}
	if readText(filepath.Join(repo, "src/pkg/values.py"), 100000) != "value = 43\n" {
		t.Fatal("apply lost edit")
	}
	reject(t, func() { applyRun(dir) })
}
func preparedApply(t *testing.T) (string, string, M) {
	repo, root := fixtureRepo(t)
	planDir := filepath.Join(root, "plan")
	p := snapshot(repo, "Update source values", planDir, []string{}, []string{}, []string{"new/created.py"}, []string{}, 4, 350000)
	dir := newDirectory(filepath.Join(root, "run"))
	edits := M{"src/app.py": "value = 3\n", "src/pkg/values.py": "value = 4\n", "new/created.py": "created = True\n"}
	materialize(p, filepath.Join(dir, "candidate"), edits)
	hashes := M{}
	for k, v := range edits {
		hashes[k] = digest([]byte(str(v)))
	}
	result := M{"status": "verified", "verification_exit_code": 0, "plan": planDir, "plan_sha256": digest(readBytes(filepath.Join(planDir, "plan.json"), 40000000)), "edits": hashes}
	result["candidate_hashes"] = candidateHashes(filepath.Join(dir, "candidate"), candidatePaths(p, result))
	save(filepath.Join(dir, "result.json"), result)
	return dir, repo, p
}
func TestNativeApplyRollbackAndConcurrentChange(t *testing.T) {
	for _, concurrent := range []bool{false, true} {
		t.Run(map[bool]string{false: "rollback", true: "preserve-concurrent"}[concurrent], func(t *testing.T) {
			dir, repo, _ := preparedApply(t)
			calls := 0
			reject(t, func() {
				applyWith(dir, func(temp, target string, isNew bool) error {
					calls++
					if calls == 2 {
						if concurrent {
							writeBytes(filepath.Join(repo, "new/created.py"), []byte("external change\n"), 0644)
						}
						return errors.New("fixture failure")
					}
					return installFile(temp, target, isNew)
				})
			})
			record := load(filepath.Join(dir, "result.json"))
			if record["status"] != "apply_failed" {
				t.Fatal(record)
			}
			if concurrent {
				if !contains(stringsOf(record["recovery_incomplete"]), "new/created.py") || readText(filepath.Join(repo, "new/created.py"), 1000) != "external change\n" {
					t.Fatal("overwrote concurrent source")
				}
			} else if exists(filepath.Join(repo, "new")) || len(array(record["recovery_incomplete"])) > 0 {
				t.Fatal("rollback incomplete")
			}
			if readText(filepath.Join(repo, "src/pkg/values.py"), 1000) != "value = 42\n" {
				t.Fatal("unrelated source changed")
			}
		})
	}
}
func TestNativeApplyRefusesStaleCandidateAndOccupiedCreation(t *testing.T) {
	for _, kind := range []string{"candidate", "source", "occupied"} {
		t.Run(kind, func(t *testing.T) {
			dir, repo, _ := preparedApply(t)
			switch kind {
			case "candidate":
				writeBytes(filepath.Join(dir, "candidate/src/app.py"), []byte("tampered"), 0644)
			case "source":
				writeBytes(filepath.Join(repo, "src/app.py"), []byte("changed"), 0644)
			case "occupied":
				need(os.Mkdir(filepath.Join(repo, "new"), 0700) == nil, "mkdir")
				writeBytes(filepath.Join(repo, "new/created.py"), []byte("owner content"), 0644)
			}
			reject(t, func() { applyRun(dir) })
			if readText(filepath.Join(repo, "src/pkg/values.py"), 1000) != "value = 42\n" {
				t.Fatal("refusal wrote source")
			}
		})
	}
}
func TestNativeModelAndPermissionBoundaries(t *testing.T) {
	for _, config := range []M{{"model_provider": "custom"}, {"profile": "work"}, {"model": "bad\nname"}, {"model_reasoning_effort": "unknown"}} {
		reject(t, func() { modelSettings(config) })
	}
	for _, kind := range []string{"command_execution", "mcp_tool_call", "file_change", "web_search", "collab_tool_call"} {
		if !flag(parseCodexEvents(`{"type":"item.completed","item":{"type":"` + kind + `"}}`)["contaminated"]) {
			t.Fatal(kind)
		}
	}
	dir, repo, p := preparedApply(t)
	_ = repo
	reject(t, func() { materialize(p, filepath.Join(dir, "bad"), M{"AGENTS.md": "overwrite"}) })
	reject(t, func() { materialize(p, filepath.Join(dir, "bad-test"), M{"tests/test_new.py": "pass"}) })
	err := guarded(func() {
		process([]string{"/bin/sh", "-c", "printf partial; sleep 10"}, "", childEnv("TYPESAFE_API_KEY"), 30*time.Millisecond, "")
	})
	if err == nil || failure(err, "test")["error_kind"] != "timeout" {
		t.Fatal(err)
	}
	if f := err.(fault); sget(f.partial, "stdout") != "partial" {
		t.Fatal("lost partial output")
	}
}
func TestNativeGoDependencyClosure(t *testing.T) {
	files := M{"go.mod": "module example.invalid/repo\n", "cmd/main.go": "package main\nimport \"example.invalid/repo/internal/lib\"\n", "internal/lib/lib.go": "package lib\n", "internal/lib/other.go": "package lib\n", "unrelated/other.go": "package unrelated\n"}
	got := dependencies(files, []string{"cmd/main.go"})
	if !contains(got, "go.mod") || !contains(got, "internal/lib/lib.go") || !contains(got, "internal/lib/other.go") || contains(got, "unrelated/other.go") {
		t.Fatal(got)
	}
	if eligibility("main.go") != "" || eligibility("go.mod") != "" || eligibility("go.sum") != "lockfile" || !isTest("foo_test.go") {
		t.Fatal("Go eligibility contract")
	}
}
func TestNativeCommandParserAndNoPythonExecutable(t *testing.T) {
	root := t.TempDir()
	binary := filepath.Join(root, "astra-jev")
	goBinary := os.Getenv("ASTRA_JEV_TEST_GO")
	if goBinary == "" {
		t.Skip("binary smoke requires explicit build tool")
	}
	cmd := exec.Command(goBinary, "build", "-o", binary, "./cmd/astra-jev")
	cmd.Dir = filepath.Join("..", "..")
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("build: %v %s", err, out)
	}
	cmd = exec.Command(binary, "--help")
	cmd.Env = []string{"PATH=" + root}
	out, err := cmd.CombinedOutput()
	if err != nil || !bytes.Contains(out, []byte("No Python required")) {
		t.Fatalf("native launch: %v %s", err, out)
	}
	r := New("")
	r.credential = func() (string, string) { t.Fatal("help accessed key"); return "", "" }
	for _, args := range [][]string{{"desktop", "plan", "--help"}, {"cli", "run", "--help"}, {"evidence", "select", "--help"}, {"output", "--help"}, {"install", "--help"}} {
		var stdout, stderr bytes.Buffer
		if code := r.Run(args, &stdout, &stderr); code != 0 {
			t.Fatalf("%v %s", args, stderr.String())
		}
	}
	var stdout, stderr bytes.Buffer
	if code := r.Run([]string{"desktop", "plan", "--allow-create", "bad.py"}, &stdout, &stderr); code == 0 {
		t.Fatal("host accepted CLI permission")
	}
	if strings.Contains(stderr.String(), "panic") {
		t.Fatal(stderr.String())
	}
}
