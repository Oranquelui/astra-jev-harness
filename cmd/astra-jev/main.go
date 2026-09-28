package main

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/Oranquelui/astra-jev-harness/internal/harness"
)

func main() {
	args := os.Args[1:]
	exe, err := os.Executable()
	if err != nil {
		fmt.Fprintln(os.Stderr, "Cannot resolve executable")
		os.Exit(1)
	}
	exe, err = filepath.EvalSymlinks(exe)
	if err != nil {
		fmt.Fprintln(os.Stderr, "Cannot resolve executable symlink")
		os.Exit(1)
	}
	root := filepath.Dir(filepath.Dir(exe))
	if len(args) > 0 && args[0] == "--harness-root" {
		if len(args) < 2 {
			fmt.Fprintln(os.Stderr, "--harness-root requires a path")
			os.Exit(2)
		}
		root = args[1]
		args = args[2:]
	}
	os.Exit(harness.New(root).Run(args, os.Stdout, os.Stderr))
}
