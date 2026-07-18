// caucus-verify: a standalone verifier for Caucus decision logs (SPEC.md).
//
// An independent implementation in a second language — if this and the
// Python reference agree on every record and every golden vector, the
// format is a standard, not an artifact of one codebase.
//
// Usage: caucus-verify [-head <log.jsonl.head>] <log.jsonl>
// (flags precede the log path — Go flag parsing stops at the first
// positional argument)
package main

import (
	"flag"
	"fmt"
	"io"
	"os"
)

func run(args []string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("caucus-verify", flag.ContinueOnError)
	flags.SetOutput(stderr)
	head := flags.String("head", "", "path to the head checkpoint file")
	if err := flags.Parse(args); err != nil {
		return 2
	}
	if flags.NArg() != 1 {
		fmt.Fprintln(stderr, "usage: caucus-verify [-head <file>] <log.jsonl>")
		return 2
	}
	result := verifyLog(flags.Arg(0), *head)
	if !result.OK {
		if result.BrokenAt >= 0 {
			fmt.Fprintf(stderr, "TAMPERED — record %d: %s\n", result.BrokenAt, result.Reason)
		} else {
			fmt.Fprintf(stderr, "TAMPERED — %s\n", result.Reason)
		}
		return 1
	}
	fmt.Fprintf(stdout, "OK — %d records, chain intact\n", result.Count)
	return 0
}

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}
