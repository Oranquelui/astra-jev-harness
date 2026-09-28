//go:build darwin || linux

package harness

import (
	"bytes"
	"context"
	"os"
	"os/exec"
	"os/signal"
	"syscall"
	"time"
)

func childEnv(remove ...string) []string {
	out := []string{}
	for _, entry := range os.Environ() {
		blocked := false
		for _, key := range remove {
			if len(entry) > len(key) && entry[:len(key)+1] == key+"=" {
				blocked = true
				break
			}
		}
		if !blocked {
			out = append(out, entry)
		}
	}
	return out
}
func process(argv []string, cwd string, env []string, timeout time.Duration, input string) M {
	need(len(argv) > 0, "Missing command")
	parent, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	ctx, cancel := context.WithTimeout(parent, timeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, argv[0], argv[1:]...)
	cmd.Dir = cwd
	cmd.Env = env
	cmd.Stdin = bytes.NewBufferString(input)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	cmd.Cancel = func() error { return syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL) }
	cmd.WaitDelay = 2 * time.Second
	var out, stderr bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &stderr
	err := cmd.Run()
	if ctx.Err() != nil {
		kind := "timeout"
		if parent.Err() != nil {
			kind = "cancelled"
		}
		panic(fault{message: "Process stopped", diagnostic: M{"error_kind": kind}, partial: M{"stdout": out.String(), "stderr": stderr.String()}})
	}
	code := 0
	if err != nil {
		if exit, ok := err.(*exec.ExitError); ok {
			code = exit.ExitCode()
			if code < 0 {
				code = 128 + int(exit.Sys().(syscall.WaitStatus).Signal())
			}
		} else {
			fail("Cannot start process")
		}
	}
	return M{"returncode": code, "stdout": out.String(), "stderr": stderr.String()}
}
func git(repo string, args ...string) []byte {
	p := process(append([]string{"git", "-C", repo}, args...), "", childEnv("TYPESAFE_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY"), 15*time.Second, "")
	need(integer(p["returncode"]) == 0, "Git query failed")
	return []byte(str(p["stdout"]))
}
