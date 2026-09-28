package harness

import (
	"bytes"
	"context"
	"errors"
	"io"
	"math"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

type Runtime struct {
	Root       string
	client     *http.Client
	endpoint   string
	credential func() (string, string)
}

func New(root string) *Runtime {
	return &Runtime{Root: root, client: &http.Client{Timeout: 30 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return errors.New("redirect refused") }}, endpoint: "https://api.typesafe.ai/v1/systemone", credential: credentials}
}
func credentials() (string, string) {
	if key := os.Getenv("TYPESAFE_API_KEY"); key != "" {
		return key, "environment"
	}
	if runtime.GOOS == "darwin" {
		ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
		defer cancel()
		cmd := exec.CommandContext(ctx, "/usr/bin/security", "find-generic-password", "-s", "astra-jev-harness", "-a", "TYPESAFE_API_KEY", "-w")
		out, err := cmd.Output()
		if ctx.Err() != nil {
			return "", "keychain_timeout"
		}
		if err == nil && strings.TrimSpace(string(out)) != "" {
			return strings.TrimSpace(string(out)), "keychain"
		}
		if e, ok := err.(*exec.ExitError); !ok || e.ExitCode() != 44 {
			return "", "keychain_unavailable"
		}
	}
	return "", "absent"
}
func validateResponse(payload, value M) {
	need(value["model"] == payload["model"], "Unexpected Jev model")
	answers := obj(value, "answers")
	questions := obj(payload, "questions")
	need(len(answers) == len(questions), "Unexpected answer count")
	for k := range questions {
		a := object(answers[k])
		need(a["type"] == "noul", "Invalid probability type")
		v := number(a["noul"])
		need(!math.IsNaN(v) && !math.IsInf(v, 0) && v >= 0 && v <= 1, "Invalid probability")
	}
}
func readCache(payload M, dir string) M {
	if dir == "" {
		return nil
	}
	p := filepath.Join(dir, hash(payload)+".json")
	info, err := os.Lstat(p)
	if os.IsNotExist(err) {
		return nil
	}
	need(err == nil && info.Mode()&os.ModeSymlink == 0, "Cache symlink or read failure")
	r := load(p)
	need(r["request_sha256"] == hash(payload), "Cache request mismatch")
	v := obj(r, "response")
	validateResponse(payload, v)
	need(hash(v) == r["response_sha256"], "Cache response changed")
	return v
}
func writeCache(payload, value M, dir string) {
	if dir == "" {
		return
	}
	need(os.MkdirAll(dir, 0700) == nil, "Cannot create cache")
	save(filepath.Join(dir, hash(payload)+".json"), M{"request_sha256": hash(payload), "response": value, "response_sha256": hash(value)})
}
func (r *Runtime) request(payload M, key string) (M, M) {
	need(key != "", "Jev credential unavailable")
	started := time.Now()
	bad := func(kind string, status any) {
		panic(fault{message: "TypeSafe request failed; no automatic retry", diagnostic: M{"error_kind": kind, "http_status": status, "seconds": time.Since(started).Seconds(), "request_sha256": hash(payload)}})
	}
	body := spaced(payload)
	req, err := http.NewRequest(http.MethodPost, r.endpoint, bytes.NewReader(body))
	need(err == nil, "Invalid provider configuration")
	req.Header.Set("Authorization", "Bearer "+key)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", "astra-jev-harness/0.7.0 (+https://github.com/Oranquelui/astra-jev-harness)")
	res, err := r.client.Do(req)
	if err != nil {
		kind := "connection_error"
		var n net.Error
		if errors.As(err, &n) && n.Timeout() {
			kind = "timeout"
		}
		bad(kind, nil)
	}
	defer res.Body.Close()
	if res.StatusCode < 200 || res.StatusCode >= 300 {
		bad("http_error", res.StatusCode)
	}
	raw, err := io.ReadAll(io.LimitReader(res.Body, 4_000_001))
	if err != nil {
		bad("connection_error", nil)
	}
	if len(raw) > 4_000_000 {
		bad("invalid_response", nil)
	}
	var value M
	if guarded(func() { value = object(decode(raw)) }) != nil {
		bad("invalid_json", nil)
	}
	if guarded(func() { validateResponse(payload, value) }) != nil {
		bad("invalid_response", nil)
	}
	return value, M{"seconds": time.Since(started).Seconds(), "model": value["model"], "usage": value["usage"], "request_sha256": hash(payload), "reused": false}
}
func reused(payload, value M) M {
	return M{"model": value["model"], "request_sha256": hash(payload), "reused": true, "usage": nil, "seconds": 0}
}
func selectContext(b batch, value M) M {
	answers := obj(value, "answers")
	need(len(answers) == len(b.Keys), "Unexpected answers")
	probs := M{}
	selected := []string{}
	uncertain := false
	for i, k := range b.Keys {
		v := number(object(answers[fieldName("f", i)])["noul"])
		probs[k] = object(answers[fieldName("f", i)])["noul"]
		if v >= .8 {
			selected = append(selected, k)
		}
		uncertain = uncertain || v > .2 && v < .8
	}
	var reason any
	if uncertain || len(selected) == 0 {
		selected = b.Keys
		reason = "uncertain_or_empty"
	}
	return M{"paths": selected, "fallback": reason, "probabilities": probs}
}
func requiredCalls(plan M, cache string) int {
	n := 0
	cat := units(plan)
	for _, b := range batches(plan) {
		if readCache(jevPayload(plan, b, cat), cache) == nil {
			n++
		}
	}
	return n
}
func (r *Runtime) selectFiles(plan M, mode, policy, cache, key string, maxCalls int, onAttempt func(), onCall func(M)) M {
	route := selectionRoute(plan, mode)
	need(policy == "batch" || policy == "per-file", "Unknown policy")
	calls := []M{}
	reason := "explicit_or_small_context"
	if route == "jev" {
		need(maxCalls >= 1 && maxCalls <= 24 && requiredCalls(plan, cache) <= maxCalls, "Jev request budget exceeded")
		if cache != "" {
			need(!within(absolute(cache), str(plan["repo"])), "Cache must be outside source repository")
		}
		cat := units(plan)
		for _, b := range batches(plan) {
			payload := jevPayload(plan, b, cat)
			value := readCache(payload, cache)
			var meta M
			if value == nil {
				if onAttempt != nil {
					onAttempt()
				}
				value, meta = r.request(payload, key)
				writeCache(payload, value, cache)
			} else {
				meta = reused(payload, value)
			}
			call := merge(selectContext(b, value), meta)
			calls = append(calls, call)
			if onCall != nil {
				onCall(call)
			}
		}
		reason = "explicit_or_large_context"
	}
	return merge(resolveSelection(plan, calls, policy), M{"route": route, "reason": reason, "jev_calls": calls})
}
