package harness

import (
	flags "flag"
	"fmt"
	"io"
	"runtime"
	"strings"
)

var Version = "dev"
var Revision = "unknown"

type repeated []string

func (v *repeated) String() string     { return strings.Join(*v, ",") }
func (v *repeated) Set(s string) error { *v = append(*v, s); return nil }
func (r *Runtime) Run(args []string, stdout, stderr io.Writer) (code int) {
	defer func() {
		if p := recover(); p != nil {
			if e, ok := p.(fault); ok {
				fmt.Fprintln(stderr, e.message)
				code = 1
			} else {
				panic(p)
			}
		}
	}()
	if len(args) == 0 || contains([]string{"--help", "-h", "help"}, args[0]) {
		fmt.Fprintln(stdout, "astra-jev: native Go runtime (macOS/Linux)\nCommands: desktop, claude-code, cli, evidence, output, measure, install\nUse <command> --help or <command> <operation> --help. No Python required.")
		return 0
	}
	if args[0] == "version" || args[0] == "--version" {
		fmt.Fprintln(stdout, string(spaced(M{"version": Version, "revision": Revision, "platform": runtime.GOOS + "-" + runtime.GOARCH})))
		return 0
	}
	if args[0] == "platform" {
		fmt.Fprintln(stdout, runtime.GOOS+"-"+runtime.GOARCH)
		return 0
	}
	surface := args[0]
	args = args[1:]
	if surface == "install" {
		return r.installCommand(args, stdout, stderr)
	}
	if surface == "output" {
		return r.outputCommand(args, stdout, stderr)
	}
	if surface == "measure" {
		return r.measureCommand(args, stdout, stderr)
	}
	need(contains([]string{"desktop", "claude-code", "cli", "evidence"}, surface), "Unknown command")
	if len(args) == 0 || args[0] == "--help" || args[0] == "-h" {
		fmt.Fprintln(stdout, "Operations: plan, select, check, read, present, discover, compare (hosts); plan, run, verify, apply (CLI); plan, select, check (evidence)")
		return 0
	}
	operation := args[0]
	args = args[1:]
	fs := flags.NewFlagSet(surface+" "+operation, flags.ContinueOnError)
	fs.SetOutput(stderr)
	var includes, focus, creates, tests, sources, pins, required repeated
	repo, taskFile, out, planDir, selection, cache, evidence, mode, policy, file, directory, runDir, verifyJSON := "", "", "", "", "", "", "", "jev", "batch", "", "", "", ""
	cap, scopeCap, start, end, limit, offset, lines, timeout := 4, 4, 1, 0, 8192, 0, 12, 180
	requireJevFlag := false
	switch operation {
	case "doctor":
		need(surface == "desktop" || surface == "claude-code" || surface == "cli", "Doctor is a host command")
	case "plan":
		fs.StringVar(&repo, "repo", "", "Exact Git root")
		fs.StringVar(&taskFile, "task-file", "", "Explicit task file")
		fs.StringVar(&out, "out", "", "New external artifact directory")
		if surface == "evidence" {
			fs.Var(&sources, "source", "Evidence source")
			fs.Var(&pins, "pin-source", "Mandatory evidence source")
		} else {
			fs.Var(&includes, "include-file", "Explicit untracked file")
			fs.Var(&focus, "focus-file", "Required eligible file")
			fs.IntVar(&scopeCap, "scope-max-calls", 4, "Planned request cap (1..24)")
			if surface == "cli" {
				fs.Var(&creates, "allow-create", "Allowed new file")
				fs.Var(&tests, "allow-test-edit", "Allowed existing test edit")
			}
		}
	case "select":
		need(surface != "cli", "Use CLI run")
		fs.StringVar(&planDir, "plan", "", "Plan directory")
		fs.StringVar(&out, "out", "", "New external selection directory")
		fs.StringVar(&cache, "cache-dir", "", "External exact-request cache")
		fs.IntVar(&cap, "max-calls", 4, "Maximum live calls")
		if surface != "evidence" {
			fs.StringVar(&evidence, "evidence", "", "Matching evidence selection")
			fs.StringVar(&policy, "policy", "batch", "batch or per-file")
			fs.StringVar(&mode, "mode", "jev", "jev, local or auto")
			fs.BoolVar(&requireJevFlag, "require-jev", false, "Require saved Jev judgments")
		}
	case "check", "read", "present", "compare":
		need(surface != "cli", "Invalid CLI operation")
		fs.StringVar(&selection, "selection", "", "Selection directory")
		if operation != "compare" {
			fs.BoolVar(&requireJevFlag, "require-jev", operation == "present", "Require Jev judgments")
		}
		if operation == "read" {
			need(surface != "evidence", "Evidence does not implement source read")
			fs.StringVar(&file, "path", "", "Selected relative path")
			fs.IntVar(&start, "start-line", 1, "First line")
			fs.IntVar(&end, "end-line", 0, "Last line (default 80 lines)")
		}
		if operation == "present" {
			need(surface != "evidence", "Invalid evidence operation")
			fs.IntVar(&limit, "max-bytes", 8192, "Entire JSON output cap")
			fs.IntVar(&offset, "offset", 0, "First retained item")
			fs.IntVar(&lines, "lines-per-file", 12, "Source lines per file")
		}
		if operation == "compare" {
			need(surface != "evidence", "Invalid evidence operation")
			fs.Var(&required, "required-file", "Independent required-file label")
		}
	case "discover":
		need(surface == "desktop" || surface == "claude-code", "Host operation only")
		fs.StringVar(&planDir, "plan", "", "Plan directory")
		fs.StringVar(&directory, "directory", "", "Exact directory from index")
		fs.IntVar(&limit, "max-bytes", 8192, "Entire JSON output cap")
		fs.IntVar(&offset, "offset", 0, "First item")
		fs.IntVar(&lines, "lines-per-file", 4, "Lines per preview")
	case "run":
		need(surface == "cli", "Only CLI generates candidates")
		fs.StringVar(&planDir, "plan", "", "Plan directory")
		fs.StringVar(&out, "out", "", "New external run directory")
		fs.StringVar(&mode, "mode", "auto", "auto, astra or jev")
		fs.StringVar(&verifyJSON, "verify-json", "", "Explicit command argument array")
		fs.IntVar(&timeout, "timeout", 180, "Process timeout seconds")
		fs.StringVar(&cache, "cache-dir", "", "External cache")
		fs.StringVar(&evidence, "evidence", "", "Evidence selection")
	case "verify", "apply":
		need(surface == "cli", "Only CLI verifies or applies")
		fs.StringVar(&runDir, "run", "", "Run directory")
		if operation == "verify" {
			fs.IntVar(&timeout, "timeout", 180, "Process timeout seconds")
		}
	default:
		fail("Unknown operation")
	}
	if err := fs.Parse(args); err != nil {
		if err == flags.ErrHelp {
			return 0
		}
		return 2
	}
	need(len(fs.Args()) == 0, "Unexpected positional arguments")
	need(timeout > 0, "Timeout must be positive")
	var result M
	switch operation {
	case "doctor":
		key, source := r.credential()
		result = M{"surface": surface, "harness_root": r.Root, "key_source": source, "typesafe_key_present": key != "", "runtime": "go"}
		if key == "" {
			code = 1
		}
	case "plan":
		task := readTask(taskFile)
		if surface == "evidence" {
			p := evidenceMakePlan(task, []string(sources), []string(pins), out)
			result = M{"status": "planned", "calls": p["planned_calls"], "fragments": len(array(p["fragments"]))}
		} else {
			var p M
			if surface == "cli" {
				p = snapshot(repo, task, out, []string(includes), []string(focus), []string(creates), []string(tests), scopeCap, 350000)
			} else {
				p = hostMakePlan(surface, repo, task, out, []string(includes), []string(focus), scopeCap)
			}
			result = M{"status": "planned", "files": len(obj(p, "files")), "planned_calls": len(batches(p))}
		}
	case "select":
		if surface == "evidence" {
			record := r.evidenceSelect(planDir, out, cache, cap)
			result = M{"status": record["status"], "attempted_calls": record["attempted_calls"], "candidate_bytes": record["candidate_bytes"], "selected_bytes": record["selected_bytes"]}
		} else {
			need(contains([]string{"auto", "jev", "local"}, mode), "Invalid host mode")
			record := r.hostSelect(surface, planDir, out, policy, cache, evidence, mode, cap, requireJevFlag)
			result = merge(M{"status": record["status"], "selected_files": len(array(record["paths"])), "route": record["route"], "require_jev": record["require_jev"]}, callCounts(record), childFields(surface))
		}
	case "check":
		if surface == "evidence" {
			packet := evidenceCheck(selection)
			result = M{"status": "fresh", "fragments": len(array(packet["fragments"]))}
		} else {
			result = hostCheck(surface, selection, requireJevFlag)
		}
	case "read":
		result = hostRead(surface, selection, file, start, end, requireJevFlag)
	case "present":
		result = hostPresent(surface, selection, limit, offset, lines)
	case "discover":
		hasDirectory := false
		fs.Visit(func(f *flags.Flag) {
			if f.Name == "directory" {
				hasDirectory = true
			}
		})
		result = hostDiscover(surface, planDir, directory, hasDirectory, limit, offset, lines)
	case "compare":
		result = hostCompare(surface, selection, []string(required))
	case "run":
		need(contains([]string{"auto", "astra", "jev"}, mode), "Invalid CLI mode")
		var command []string
		if verifyJSON != "" {
			command = stringsOf(decode([]byte(verifyJSON)))
			validateCommand(command)
		}
		record := r.codingRun(planDir, out, mode, cache, evidence, command, timeout)
		result = M{"status": record["status"], "report": out + "/REPORT.md"}
		if record["status"] != "verified" && record["status"] != "unverified" {
			code = 1
		}
	case "verify":
		record := reverify(runDir, timeout)
		result = M{"status": record["status"]}
		if record["status"] != "verified" {
			code = 1
		}
	case "apply":
		record := applyRun(runDir)
		result = M{"status": record["status"], "applied_files": len(obj(record, "edits")), "git_writes": 0}
	}
	fmt.Fprintln(stdout, string(spaced(result)))
	return code
}
func (r *Runtime) installCommand(args []string, stdout, stderr io.Writer) int {
	fs := flags.NewFlagSet("install", flags.ContinueOnError)
	fs.SetOutput(stderr)
	target := fs.String("target", "codex-desktop", "codex-desktop or claude-code")
	dir := fs.String("skills-dir", "", "Destination Skills directory")
	check := fs.Bool("check", false, "Read-only installation check")
	if err := fs.Parse(args); err != nil {
		if err == flags.ErrHelp {
			return 0
		}
		return 2
	}
	need(len(fs.Args()) == 0, "Unexpected arguments")
	fmt.Fprintln(stdout, string(spaced(r.install(*dir, *check, *target))))
	return 0
}
func (r *Runtime) outputCommand(args []string, stdout, stderr io.Writer) int {
	fs := flags.NewFlagSet("output", flags.ContinueOnError)
	fs.SetOutput(stderr)
	task := fs.String("task-file", "", "Task file")
	out := fs.String("out", "", "New external output directory")
	mode := fs.String("mode", "auto", "auto, jev or local")
	cap := fs.Int("max-calls", 2, "Maximum calls (1..4)")
	var keep repeated
	fs.Var(&keep, "keep-text", "Required literal")
	if err := fs.Parse(args); err != nil {
		if err == flags.ErrHelp {
			return 0
		}
		return 2
	}
	return r.runOutput(fs.Args(), readTask(*task), *out, []string(keep), *cap, *mode, stdout, stderr)
}
func (r *Runtime) measureCommand(args []string, stdout, stderr io.Writer) int {
	fs := flags.NewFlagSet("measure", flags.ContinueOnError)
	fs.SetOutput(stderr)
	var before, after repeated
	fs.Var(&before, "baseline", "Saved baseline receipt")
	fs.Var(&after, "candidate", "Saved candidate receipt")
	prices := fs.String("prices", "", "Explicit model-specific rates")
	if err := fs.Parse(args); err != nil {
		if err == flags.ErrHelp {
			return 0
		}
		return 2
	}
	need(len(before) > 0 && len(after) > 0 && len(fs.Args()) == 0, "Baseline and candidate receipts required")
	var p M
	if *prices != "" {
		p = load(*prices)
	}
	fmt.Fprintln(stdout, string(spaced(measureCompare([]string(before), []string(after), p))))
	return 0
}
