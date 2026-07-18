// caucus-verify: a standalone verifier for Caucus decision logs (SPEC.md).
//
// An independent implementation in a second language — if this and the
// Python reference agree on every record and every golden vector, the
// format is a standard, not an artifact of one codebase.
//
// Usage: caucus-verify <log.jsonl> [-head <log.jsonl.head>]
package main

import (
	"flag"
	"fmt"
	"os"
)

func main() {
	head := flag.String("head", "", "path to the head checkpoint file")
	flag.Parse()
	if flag.NArg() != 1 {
		fmt.Fprintln(os.Stderr, "usage: caucus-verify <log.jsonl> [-head <file>]")
		os.Exit(2)
	}
	result := verifyLog(flag.Arg(0), *head)
	if !result.OK {
		if result.BrokenAt >= 0 {
			fmt.Fprintf(os.Stderr, "TAMPERED — record %d: %s\n", result.BrokenAt, result.Reason)
		} else {
			fmt.Fprintf(os.Stderr, "TAMPERED — %s\n", result.Reason)
		}
		os.Exit(1)
	}
	fmt.Printf("OK — %d records, chain intact\n", result.Count)
}
