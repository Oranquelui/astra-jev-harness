package harness

import (
	"os"
	"path"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"

	"golang.org/x/text/cases"
)

var secret = regexp.MustCompile(`(?i)apikey_[a-zA-Z0-9_]{40,}|sk-(?:proj-)?[a-zA-Z0-9_-]{25,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|(?:api_key|password|secret|token)\s*[:=]\s*["'][^"'\n]{24,}["']`)

// Python's Unicode-aware whitespace/IGNORECASE must not become a narrower
// credential guard during migration. Normalize only a temporary scan copy.
func isSecret(text string) bool {
	return secret.MatchString(strings.Map(func(r rune) rune {
		if r == 'ı' || r == 'İ' {
			return 'i'
		}
		if r != '\n' && r != '\r' && unicode.IsSpace(r) {
			return ' '
		}
		return r
	}, text))
}

var extensions = set(strings.Fields(".go .py .ts .tsx .js .jsx .mjs .cjs .mts .cts .json .jsonc .toml .yaml .yml .md .txt .css .html .sql"))
var excludedDirs = set(strings.Fields(".git .venv venv node_modules dist build .next __pycache__"))

func safePath(root, rel string) string {
	need(rel != "" && rel != "." && !strings.ContainsAny(rel, "\\\x00\n\r") && !path.IsAbs(rel) && path.Clean(rel) == rel, "Invalid relative path")
	parts := strings.Split(rel, "/")
	p := root
	for _, part := range parts {
		need(part != "..", "Path escape refused")
		p = filepath.Join(p, part)
		i, err := os.Lstat(p)
		need(os.IsNotExist(err) || err == nil && i.Mode()&os.ModeSymlink == 0, "Symlink path refused")
	}
	need(within(p, root), "Path escape refused")
	return p
}
func eligibility(rel string) string {
	p := strings.ToLower(rel)
	parts := strings.Split(p, "/")
	for _, part := range parts {
		if excludedDirs[part] != nil {
			return "generated_or_data_directory"
		}
	}
	if parts[0] == "data" || parts[0] == "uploads" {
		return "generated_or_data_directory"
	}
	base := path.Base(p)
	ext := path.Ext(p)
	if strings.HasPrefix(base, ".env") || contains([]string{".pem", ".key", ".p12", ".sqlite", ".db"}, ext) || contains([]string{"auth.json", "credentials.json", "secrets.json"}, base) {
		return "credential_or_database_file"
	}
	if strings.HasSuffix(base, "-lock.json") || strings.HasSuffix(base, "-lock.yaml") || contains([]string{"yarn.lock", "uv.lock", "poetry.lock"}, base) {
		return "lockfile"
	}
	if base == "go.sum" {
		return "lockfile"
	}
	if base == "go.mod" || base == "go.work" {
		return ""
	}
	if extensions[ext] == nil {
		return "unsupported_file_type"
	}
	return ""
}
func isInstruction(p string) bool {
	p = strings.ToLower(p)
	return path.Base(p) == "agents.md" || contains(strings.Split(p, "/"), "policies")
}
func isTest(p string) bool {
	base := path.Base(p)
	for _, s := range strings.Split(p, "/") {
		if contains([]string{"test", "tests", "__tests__"}, s) {
			return true
		}
	}
	return base == "conftest.py" || strings.HasPrefix(base, "test_") || strings.HasSuffix(base, "_test.py") || strings.HasSuffix(base, "_test.go") || strings.Contains(base, ".test.") || strings.Contains(base, ".spec.")
}
func validateScope(plan M) {
	creates, tests := stringsOf(plan["create_paths"]), stringsOf(plan["test_edit_paths"])
	files := obj(plan, "files")
	for _, paths := range [][]string{creates, tests} {
		seen := M{}
		for _, p := range paths {
			fold := cases.Fold().String(p)
			need(seen[fold] == nil, "Duplicate change path")
			seen[fold] = true
			safePath(str(plan["repo"]), p)
			need(eligibility(p) == "" && !isInstruction(p), "Protected change path")
		}
	}
	need(len(files)+len(creates) <= 1500, "Too many planned files")
	occupied := append(append(keys(files), keys(obj(plan, "excluded"))...), keys(obj(plan, "scoped_out"))...)
	for _, p := range creates {
		for _, other := range append(append([]string{}, occupied...), creates...) {
			if other == p && !contains(occupied, other) {
				continue
			}
			a, b := cases.Fold().String(p), cases.Fold().String(other)
			need(a != b && !strings.HasPrefix(a, b+"/") && !strings.HasPrefix(b, a+"/"), "Creation path conflict")
		}
	}
	for _, p := range tests {
		need(files[p] != nil && isTest(p), "Invalid test edit permission")
	}
}
func checkDestinations(plan M) {
	root := str(plan["repo"])
	for _, p := range stringsOf(plan["create_paths"]) {
		target := safePath(root, p)
		need(!exists(target), "Creation destination exists")
		for d := filepath.Dir(target); d != root; d = filepath.Dir(d) {
			if info, err := os.Stat(d); err == nil {
				need(info.IsDir(), "Creation parent is not directory")
			}
		}
	}
}
func editable(plan M, paths []string) []string {
	r := stringsOf(plan["create_paths"])
	for _, p := range paths {
		if !isInstruction(p) && (!isTest(p) || contains(stringsOf(plan["test_edit_paths"]), p)) {
			r = append(r, p)
		}
	}
	return unique(r)
}

var camel = regexp.MustCompile(`([a-z0-9])([A-Z])`)
var termPattern = regexp.MustCompile(`[a-z][a-z0-9]*`)
var stopWords = set(strings.Fields("add and code coding file files fix for from implement into new repo repository task test tests the then this update use using with"))

func scopeTerms(v string) M {
	v = cases.Fold().String(camel.ReplaceAllString(v, "${1} ${2}"))
	r := M{}
	for _, s := range termPattern.FindAllString(v, -1) {
		if len(s) >= 3 && stopWords[s] == nil {
			r[s] = true
		}
	}
	return r
}
func intersection(a, b M) int {
	n := 0
	for k := range a {
		if b[k] != nil {
			n++
		}
	}
	return n
}
func shortlist(files M, task string, includes, focus, tests []string, maxCalls, maxBytes int) []string {
	texts := M{}
	for p, v := range files {
		texts[p] = object(v)["content"]
	}
	required := set(append(append(append([]string{}, includes...), focus...), tests...))
	for p := range files {
		if strings.Contains(task, p) {
			required[p] = true
		}
	}
	for p := range required {
		need(files[p] != nil, "Required file is not eligible")
	}
	bounded := func(paths []string) bool {
		chosen := M{}
		for _, p := range paths {
			chosen[p] = files[p]
		}
		return len(chosen) <= 1500 && sumBytes(chosen) <= maxBytes && len(batches(M{"files": chosen, "task": task, "context_format": contextFormat})) <= maxCalls
	}
	selected := dependencies(texts, keys(required))
	need(bounded(selected), "Required scope exceeds budget")
	terms := scopeTerms(task)
	type ranked struct {
		path  string
		score int
	}
	ranking := []ranked{}
	for p, v := range texts {
		if contains(selected, p) {
			continue
		}
		leaf := scopeTerms(strings.TrimSuffix(path.Base(p), path.Ext(p)))
		pt := scopeTerms(p)
		for k := range leaf {
			delete(pt, k)
		}
		score := 12*intersection(terms, leaf) + 4*intersection(terms, pt) + intersection(terms, scopeTerms(str(v)))
		if score > 0 {
			ranking = append(ranking, ranked{p, score})
		}
	}
	sort.Slice(ranking, func(i, j int) bool {
		if ranking[i].score != ranking[j].score {
			return ranking[i].score > ranking[j].score
		}
		return ranking[i].path < ranking[j].path
	})
	need(len(ranking) > 0 || len(required) > 0, "No local match; supply focus files")
	accepted := 0
	for _, v := range ranking {
		expanded := dependencies(texts, append(append([]string{}, selected...), v.path))
		if bounded(expanded) {
			selected = expanded
			accepted++
		} else {
			need(accepted > 0 || len(required) > 0, "Top match exceeds scope budget")
		}
	}
	need(len(selected) > 0 && (accepted > 0 || len(required) > 0), "No candidate fits scope")
	return selected
}
func snapshot(repo, task, out string, includes, focus, creates, tests []string, maxCalls, maxBytes int) M {
	repo = absolute(repo)
	need(absolute(strings.TrimSpace(string(git(repo, "rev-parse", "--show-toplevel")))) == repo, "Pass exact Git root")
	out = absolute(out)
	need(!within(out, repo) && !exists(out), "Use new external plan directory")
	taskValid(task)
	before := git(repo, "status", "--porcelain=v1", "-z")
	files, excluded := M{}, M{}
	need(len(unique(focus)) == len(focus), "Duplicate focus")
	for _, p := range focus {
		safePath(repo, p)
	}
	for _, p := range includes {
		target := safePath(repo, p)
		i, err := os.Stat(target)
		need(eligibility(p) == "" && err == nil && i.Mode().IsRegular(), "Invalid explicit include")
		q := process([]string{"git", "-C", repo, "check-ignore", "--quiet", "--", p}, "", childEnv("TYPESAFE_API_KEY"), 15*time.Second, "")
		need(integer(q["returncode"]) == 1, "Include ignored or cannot be checked")
	}
	tracked := strings.Split(strings.TrimSuffix(string(git(repo, "ls-files", "-z")), "\x00"), "\x00")
	for _, p := range unique(append(tracked, includes...)) {
		if p == "" {
			continue
		}
		need(utf8.ValidString(p), "Invalid repository path encoding")
		if why := eligibility(p); why != "" {
			excluded[p] = why
			continue
		}
		err := guarded(func() {
			target := safePath(repo, p)
			info, err := os.Stat(target)
			if err != nil || !info.Mode().IsRegular() || info.Size() > 100000 {
				excluded[p] = "missing_or_over_100KB"
				return
			}
			raw := readBytes(target, 100000)
			need(utf8.Valid(raw), "Invalid source encoding")
			if strings.ContainsRune(string(raw), 0) || isSecret(string(raw)) {
				excluded[p] = "binary_or_credential_pattern"
				return
			}
			files[p] = M{"sha256": digest(raw), "bytes": len(raw), "mode": int(info.Mode().Perm()), "content": string(raw)}
		})
		if err != nil {
			excluded[p] = "symlink_or_non_utf8"
		}
	}
	for _, p := range append(append([]string{}, includes...), focus...) {
		need(files[p] != nil, "Explicit file failed eligibility")
	}
	need(len(files) > 0, "No eligible files")
	need(maxCalls >= 1 && maxCalls <= 24 && maxBytes >= 1 && maxBytes <= 2000000, "Invalid scope budget")
	all := files
	scoped := M{}
	var scope M
	eligibleBytes := sumBytes(files)
	eligibleCount := len(files)
	if eligibleBytes > 2000000 || eligibleCount > 1500 || len(batches(M{"files": files, "task": task, "context_format": contextFormat})) > maxCalls {
		keep := set(shortlist(files, task, includes, focus, tests, maxCalls, maxBytes))
		files = M{}
		for p, v := range all {
			if keep[p] != nil {
				files[p] = v
			} else {
				r := clone(object(v))
				delete(r, "content")
				scoped[p] = r
			}
		}
		scope = M{"strategy": "local_task_shortlist", "eligible_files": eligibleCount, "eligible_bytes": eligibleBytes, "scoped_out_files": len(scoped), "scoped_out_bytes": sumBytes(scoped), "max_calls": maxCalls, "max_bytes": maxBytes, "planned_calls": len(batches(M{"files": files, "task": task, "context_format": contextFormat})), "focus_paths": focus}
	}
	need(string(git(repo, "status", "--porcelain=v1", "-z")) == string(before), "Repository status changed during snapshot")
	for p, v := range all {
		need(digest(readBytes(safePath(repo, p), 100000)) == object(v)["sha256"], "Repository content changed")
	}
	plan := M{"version": 1, "context_format": contextFormat, "repo": repo, "head": strings.TrimSpace(string(git(repo, "rev-parse", "HEAD"))), "branch": strings.TrimSpace(string(git(repo, "branch", "--show-current"))), "status_sha256": digest(before), "task": task, "files": files, "excluded": excluded, "explicit_includes": includes}
	if len(focus) > 0 {
		plan["focus_paths"] = focus
	}
	if scope != nil {
		plan["scoped_out"] = scoped
		plan["scope"] = scope
	}
	if len(creates) > 0 || len(tests) > 0 {
		plan["version"] = 2
		plan["create_paths"] = creates
		plan["test_edit_paths"] = tests
	}
	plan["inference"] = inference(plan)
	validateScope(plan)
	checkDestinations(plan)
	newDirectory(out)
	save(filepath.Join(out, "plan.json"), plan)
	planReport(plan, out)
	return plan
}
func planReport(p M, out string) {
	var b strings.Builder
	b.WriteString("# Repository context plan\n\nRepository: " + str(p["repo"]) + "\nHEAD: " + str(p["head"]) + "\n\nTask: " + str(p["task"]) + "\n\nInference: " + fmtJSON(p["inference"]) + "\nScope: " + fmtJSON(p["scope"]) + "\n\nLocal snapshot only; no API calls or target writes. This plan grants no additional authority.\n\n## Files potentially sent to Jev\n")
	for _, f := range keys(obj(p, "files")) {
		b.WriteString("- " + f + "\n")
	}
	b.WriteString("\n## Permitted new files\n")
	for _, f := range stringsOf(p["create_paths"]) {
		b.WriteString("- " + f + "\n")
	}
	b.WriteString("\n## Permitted existing test edits\n")
	for _, f := range stringsOf(p["test_edit_paths"]) {
		b.WriteString("- " + f + "\n")
	}
	b.WriteString("\nOther tests and repository instructions remain read-only.\n")
	b.WriteString("\n## Scoped out before Jev (unjudged)\n")
	for _, f := range keys(obj(p, "scoped_out")) {
		b.WriteString("- " + f + "\n")
	}
	b.WriteString("\n## Excluded\n")
	for _, f := range keys(obj(p, "excluded")) {
		b.WriteString("- " + f + ": " + str(obj(p, "excluded")[f]) + "\n")
	}
	report(out, "PLAN.md", b.String())
}
func loadPlan(dir string) M {
	plan := load(filepath.Join(dir, "plan.json"))
	format := sget(plan, "context_format")
	need(format == "" || format == contextFormat, "Unsupported format")
	v := integer(plan["version"])
	need(v == 1 || v == 2, "Unsupported plan version")
	need(v != 1 || len(array(plan["create_paths"]))+len(array(plan["test_edit_paths"])) == 0, "Change grants need v2")
	files := obj(plan, "files")
	for p, v := range files {
		safePath(absolute(dir), p)
		r := object(v)
		text := str(r["content"])
		need(digest([]byte(text)) == r["sha256"] && eligibility(p) == "" && !isSecret(text) && !strings.ContainsRune(text, 0) && len(text) <= 100000 && integer(r["bytes"]) == len(text), "Plan integrity or eligibility failed")
		mode := integer(r["mode"])
		need(mode >= 0 && mode <= 0777, "Invalid file mode")
	}
	scoped := obj(plan, "scoped_out")
	for p, v := range scoped {
		safePath(str(plan["repo"]), p)
		r := object(v)
		n, m := integer(r["bytes"]), integer(r["mode"])
		need(files[p] == nil && len(r) == 3 && regexp.MustCompile(`^[0-9a-f]{64}$`).MatchString(sget(r, "sha256")) && n >= 0 && n <= 100000 && m >= 0 && m <= 0777 && eligibility(p) == "", "Invalid scoped metadata")
	}
	need(len(files) <= 1500 && sumBytes(files) <= 2000000, "Snapshot bounds exceeded")
	focus := stringsOf(plan["focus_paths"])
	need(len(unique(focus)) == len(focus), "Duplicate focus")
	for _, p := range focus {
		need(files[p] != nil, "Focus outside snapshot")
	}
	if plan["scope"] != nil {
		s := obj(plan, "scope")
		need(s["strategy"] == "local_task_shortlist" && integer(s["eligible_files"]) == len(files)+len(scoped) && integer(s["eligible_bytes"]) == sumBytes(files)+sumBytes(scoped) && integer(s["scoped_out_files"]) == len(scoped) && integer(s["scoped_out_bytes"]) == sumBytes(scoped) && integer(s["planned_calls"]) == len(batches(plan)) && hash(s["focus_paths"]) == hash(focus), "Invalid scope record")
		a, b := integer(s["max_calls"]), integer(s["max_bytes"])
		need(a >= 1 && a <= 24 && b >= 1 && b <= 2000000 && integer(s["planned_calls"]) <= a && sumBytes(files) <= b, "Invalid scope bounds")
	} else {
		need(len(scoped) == 0, "Scope metadata required")
	}
	validateScope(plan)
	return plan
}
func fresh(plan M) {
	repo := str(plan["repo"])
	need(strings.TrimSpace(string(git(repo, "rev-parse", "HEAD"))) == plan["head"] && strings.TrimSpace(string(git(repo, "branch", "--show-current"))) == plan["branch"] && digest(git(repo, "status", "--porcelain=v1", "-z")) == plan["status_sha256"], "Repository changed; replan")
	for p, v := range merge(obj(plan, "files"), obj(plan, "scoped_out")) {
		r := object(v)
		target := safePath(repo, p)
		info := must(os.Stat(target))
		need(info.Mode().IsRegular() && digest(readBytes(target, 100000)) == r["sha256"] && int(info.Mode().Perm()) == integer(r["mode"]), "Repository content changed; replan")
	}
}
func requireExternal(p string) {
	p = absolute(p)
	need(!contains(strings.Split(filepath.ToSlash(p), "/"), ".git"), "Artifact path inside Git")
	probe := p
	for !exists(probe) {
		probe = filepath.Dir(probe)
	}
	if !must(os.Stat(probe)).IsDir() {
		probe = filepath.Dir(probe)
	}
	result := process([]string{"git", "-C", probe, "rev-parse", "--show-toplevel"}, "", childEnv("TYPESAFE_API_KEY"), 15*time.Second, "")
	if integer(result["returncode"]) == 0 {
		need(!within(p, absolute(strings.TrimSpace(str(result["stdout"])))), "Artifacts must stay outside Git")
	}
}
