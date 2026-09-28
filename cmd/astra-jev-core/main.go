// astra-jev-core is an offline migration/compatibility executable, not a host
// context handoff. It cannot select, authorize, or read repository context.
package main

import (
	"bufio"
	"fmt"
	"io"
	"os"

	"github.com/Oranquelui/astra-jev-harness/internal/nativecore"
)

func run(input io.Reader, output io.Writer) int {
	scanner := bufio.NewScanner(input)
	scanner.Buffer(make([]byte, 65536), 2_000_000)
	status := 0
	for scanner.Scan() {
		value, err := nativecore.Execute(scanner.Bytes())
		if err != nil {
			status = 2
			value = map[string]any{"status": "error", "error": err.Error()}
		}
		encoded, err := nativecore.JSON(value, true)
		if err != nil {
			status = 2
			encoded = []byte(`{"status":"error","error":"serialization failed"}`)
		}
		if _, err = fmt.Fprintln(output, string(encoded)); err != nil {
			return 2
		}
	}
	if scanner.Err() != nil {
		fmt.Fprintln(output, `{"status":"error","error":"input read failed or line exceeds limit"}`)
		return 2
	}
	return status
}

func main() {
	if len(os.Args) > 1 {
		if len(os.Args) == 2 && (os.Args[1] == "--help" || os.Args[1] == "-h") {
			fmt.Println("Offline Go migration core: JSON-lines stdin; operations imports, hash, excerpt, page. No Python, provider calls, repository reads or host handoff validation. Not the full Harness.")
			return
		}
		fmt.Fprintln(os.Stderr, "Use --help or JSON-lines stdin")
		os.Exit(2)
	}
	os.Exit(run(os.Stdin, os.Stdout))
}
