package harness

import (
	"bufio"
	"context"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

var runtimeArgs = []string{"--disable", "plugins", "--disable", "apps", "--disable", "memories", "--disable", "hooks", "-c", "skills.max_context_tokens=1000"}

func modelSettings(config M) M {
	need(config["model_provider"] == nil || config["model_provider"] == "openai", "Custom providers unsupported")
	need(sget(config, "profile") == "", "Profiles unsupported")
	model, effort := config["model"], config["model_reasoning_effort"]
	if model != nil {
		need(regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$`).MatchString(str(model)), "Invalid model identifier")
	}
	if effort != nil {
		need(contains([]string{"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}, str(effort)), "Invalid reasoning effort")
	}
	return M{"model": model, "reasoning": effort}
}
func modelArguments(settings M) []string {
	out := []string{}
	if settings["model"] != nil {
		out = append(out, "--model", str(settings["model"]))
	}
	if settings["reasoning"] != nil {
		out = append(out, "-c", "model_reasoning_effort="+string(wire(settings["reasoning"])))
	}
	return out
}
func readModelSettings(repo string) M {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	dir := must(os.MkdirTemp("", "codex-config-"))
	defer os.RemoveAll(dir)
	cmd := exec.CommandContext(ctx, "codex", append([]string{"app-server", "--stdio"}, runtimeArgs...)...)
	cmd.Dir = dir
	cmd.Env = childEnv("TYPESAFE_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY")
	cmd.Stderr = io.Discard
	in := must(cmd.StdinPipe())
	out := must(cmd.StdoutPipe())
	need(cmd.Start() == nil, "Cannot start configuration reader")
	defer func() { _ = in.Close(); _ = cmd.Process.Kill(); _ = cmd.Wait(); _ = out.Close() }()
	responses := make(chan []byte, 64)
	go func() {
		defer close(responses)
		scan := bufio.NewScanner(out)
		scan.Buffer(make([]byte, 65536), 2000001)
		for scan.Scan() {
			raw := append([]byte{}, scan.Bytes()...)
			select {
			case responses <- raw:
			case <-ctx.Done():
				return
			default:
				return
			}
		}
	}()
	send := func(v M) { _, err := in.Write(append(wire(v), '\n')); need(err == nil, "Configuration write failed") }
	response := func(id int) M {
		for {
			select {
			case <-ctx.Done():
				fail("Configuration read timed out; no model call made")
			case raw, ok := <-responses:
				need(ok, "Invalid configuration response")
				value := object(decode(raw))
				if nonnegativeInt(value["id"]) && integer(value["id"]) == id {
					need(value["error"] == nil && value["result"] != nil, "Configuration read failed; no model call made")
					return object(value["result"])
				}
			}
		}
	}
	send(M{"id": 1, "method": "initialize", "params": M{"clientInfo": M{"name": "astra_jev_config", "version": "1"}}})
	response(1)
	send(M{"method": "initialized", "params": M{}})
	send(M{"id": 2, "method": "config/read", "params": M{"includeLayers": false, "cwd": absolute(repo)}})
	return modelSettings(obj(response(2), "config"))
}
func parseCodexEvents(raw string) M {
	result := M{"usage": nil, "failed": false, "completed": false, "contaminated": false, "runtime_warnings": []string{}}
	for _, line := range strings.Split(raw, "\n") {
		var e M
		if guarded(func() { e = object(decode([]byte(line))) }) != nil {
			continue
		}
		switch sget(e, "type") {
		case "turn.completed":
			result["usage"] = e["usage"]
			result["completed"] = true
		case "turn.failed", "error":
			result["failed"] = true
		}
		item := obj(e, "item")
		kind := sget(item, "type")
		if kind == "error" {
			msg := sget(item, "message")
			if msg == "" {
				msg = "unspecified item error"
			}
			result["runtime_warnings"] = append(stringsOf(result["runtime_warnings"]), msg)
		}
		if contains([]string{"command_execution", "mcp_tool_call", "web_search", "file_change", "collab_tool_call"}, kind) {
			result["contaminated"] = true
		}
	}
	return result
}
func (r *Runtime) generate(plan M, paths []string, folder string, timeout int, settings M) (M, M, M) {
	prompt, schema := generationPrompt(plan, paths)
	need(len(prompt) <= 500000, "Generation prompt exceeds 500KB")
	need(os.Mkdir(folder, 0700) == nil, "Generation folder exists")
	save(filepath.Join(folder, "schema.json"), schema)
	report(folder, "prompt.txt", prompt)
	cwd := must(os.MkdirTemp("", "astra-coding-"))
	defer os.RemoveAll(cwd)
	argv := append([]string{"codex", "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check"}, runtimeArgs...)
	argv = append(argv, "--sandbox", "read-only")
	argv = append(argv, modelArguments(settings)...)
	argv = append(argv, "--json", "--color", "never", "--output-schema", filepath.Join(folder, "schema.json"), "--output-last-message", filepath.Join(folder, "answer.json"), "-")
	identity := M{"requested_model": settings["model"], "requested_reasoning": settings["reasoning"], "model_settings_source": "codex_config", "model": nil, "reasoning": nil}
	start := time.Now()
	var proc M
	err := guarded(func() {
		proc = process(argv, cwd, childEnv("TYPESAFE_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY"), time.Duration(timeout)*time.Second, prompt)
	})
	if err != nil {
		partial := M{"stdout": "", "stderr": ""}
		if f, ok := err.(fault); ok && f.partial != nil {
			partial = f.partial
		}
		report(folder, "events.jsonl", str(partial["stdout"]))
		report(folder, "stderr.txt", str(partial["stderr"]))
		save(filepath.Join(folder, "metadata.json"), merge(parseCodexEvents(str(partial["stdout"])), identity, M{"seconds": time.Since(start).Seconds(), "failed": true, "failure": failure(err, "astra_generation")}))
		panic(err)
	}
	report(folder, "events.jsonl", str(proc["stdout"]))
	report(folder, "stderr.txt", str(proc["stderr"]))
	meta := merge(parseCodexEvents(str(proc["stdout"])), identity, M{"seconds": time.Since(start).Seconds(), "prompt_bytes": len(prompt)})
	save(filepath.Join(folder, "metadata.json"), meta)
	need(integer(proc["returncode"]) == 0 && !flag(meta["failed"]) && flag(meta["completed"]) && !flag(meta["contaminated"]), "Generation failed or used tools")
	answer := load(filepath.Join(folder, "answer.json"))
	need(len(answer) == 3 && answer["summary"] != nil && answer["needs_context"] != nil && answer["files"] != nil, "Invalid generation output")
	str(answer["summary"])
	needed := stringsOf(answer["needs_context"])
	files := obj(plan, "files")
	for _, p := range needed {
		need(files[p] != nil || obj(plan, "scoped_out")[p] != nil, "Requested context outside snapshot")
		need(obj(plan, "scoped_out")[p] == nil, "Requested context was scoped out; replan")
	}
	edits := M{}
	seen := M{}
	allowed := set(editable(plan, paths))
	for _, item := range maps(answer["files"]) {
		need(len(item) == 2, "Invalid edit entry")
		p, text := str(item["path"]), str(item["content"])
		need(allowed[p] != nil && seen[p] == nil && !strings.ContainsRune(text, 0) && len(text) <= 100000 && !isSecret(text), "Invalid edit")
		seen[p] = true
		if files[p] == nil || object(files[p])["content"] != text {
			edits[p] = text
		}
	}
	need(len(needed) == 0 || len(edits) == 0, "Cannot mix edits and missing context")
	return edits, answer, meta
}
