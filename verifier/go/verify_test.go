package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

// The SPEC.md golden vector: reproducing this hash proves profile conformance.
const goldenCanonical = `{"confidence":0.8,"decision":"yes","dissent":[],"evidence":[{"ref":"SPEC.md","source":"spec"}],"positions":[{"agent":"a1","confidence":1.0,"stance":"yes","summary":"ready"}],"prev_hash":"0000000000000000000000000000000000000000000000000000000000000000","schema_version":"0.1","subject":"Ship v0.1? — héllo","timestamp":"2026-07-11T00:00:00+00:00"}`

const goldenHash = "06624a603d2f031db60ad142d28addd8f3483d08ebfc2be16e140753d9bc221d"

func TestGoldenVector(t *testing.T) {
	record := `{"subject": "Ship v0.1? — héllo", "decision": "yes", "confidence": 0.8,` +
		`"positions": [{"agent": "a1", "stance": "yes", "summary": "ready", "confidence": 1.0}],` +
		`"dissent": [], "evidence": [{"source": "spec", "ref": "SPEC.md"}],` +
		`"timestamp": "2026-07-11T00:00:00+00:00", "schema_version": "0.1",` +
		`"prev_hash": "0000000000000000000000000000000000000000000000000000000000000000", "hash": "x"}`
	payload, err := parseLine([]byte(record))
	if err != nil {
		t.Fatal(err)
	}
	var buf bytes.Buffer
	if err := canonicalize(payload, &buf, true); err != nil {
		t.Fatal(err)
	}
	expected := mustUnescape(t, goldenCanonical)
	if buf.String() != expected {
		t.Fatalf("canonical mismatch:\n got: %s\nwant: %s", buf.String(), expected)
	}
	hash, err := contentHash(payload)
	if err != nil {
		t.Fatal(err)
	}
	if hash != goldenHash {
		t.Fatalf("hash mismatch: got %s want %s", hash, goldenHash)
	}
}

// goldenCanonical above uses Go escapes; the canonical string itself contains
// the literal backslash-u sequences, so rebuild it byte-exactly.
func mustUnescape(t *testing.T, s string) string {
	return `{"confidence":0.8,"decision":"yes","dissent":[],"evidence":[{"ref":"SPEC.md","source":"spec"}],"positions":[{"agent":"a1","confidence":1.0,"stance":"yes","summary":"ready"}],"prev_hash":"0000000000000000000000000000000000000000000000000000000000000000","schema_version":"0.1","subject":"Ship v0.1? \u2014 h\u00e9llo","timestamp":"2026-07-11T00:00:00+00:00"}`
}

func TestFloatSpellingVectors(t *testing.T) {
	vectors := map[string]string{
		"0.8":     "0.8",
		"1.0":     "1.0",
		"1e-07":   "1e-07",
		"1e20":    "1e+20",
		"-0.0":    "-0.0",
		"0.0001":  "0.0001",
		"0.00001": "1e-05",
		"1e15":    "1000000000000000.0",
	}
	for literal, expected := range vectors {
		got, err := pyNumber(json.Number(literal))
		if err != nil {
			t.Fatalf("%s: %v", literal, err)
		}
		if got != expected {
			t.Errorf("%s: got %s want %s", literal, got, expected)
		}
	}
}

func writeLog(t *testing.T, lines ...string) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "decisions.jsonl")
	content := ""
	for _, line := range lines {
		content += line + "\n"
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
	return path
}

func record(t *testing.T, overrides map[string]any, prev string) string {
	t.Helper()
	payload := map[string]any{
		"schema_version": "0.1",
		"timestamp":      "2026-07-18T00:00:00+00:00",
		"subject":        "q",
		"positions":      []any{},
		"decision":       "yes",
		"dissent":        []any{},
		"confidence":     json.Number("0.7"),
		"evidence":       []any{},
		"prev_hash":      prev,
	}
	for key, value := range overrides {
		payload[key] = value
	}
	hash, err := contentHash(payload)
	if err != nil {
		t.Fatal(err)
	}
	payload["hash"] = hash
	encoded, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	return string(encoded)
}

func TestChainVerifies(t *testing.T) {
	first := record(t, nil, genesisHash)
	var parsed map[string]any
	if err := json.Unmarshal([]byte(first), &parsed); err != nil {
		t.Fatal(err)
	}
	second := record(t, map[string]any{"subject": "q2"}, parsed["hash"].(string))
	path := writeLog(t, first, second)
	result := verifyLog(path, "")
	if !result.OK || result.Count != 2 {
		t.Fatalf("expected clean verify, got %+v", result)
	}
}

func TestTamperDetected(t *testing.T) {
	first := record(t, nil, genesisHash)
	tampered := bytes.Replace([]byte(first), []byte(`"yes"`), []byte(`"no"`), 1)
	path := writeLog(t, string(tampered))
	result := verifyLog(path, "")
	if result.OK || result.Reason != "content hash mismatch" {
		t.Fatalf("expected content hash mismatch, got %+v", result)
	}
}

func TestSchemaBoundaries(t *testing.T) {
	rounds := []any{[]any{map[string]any{
		"agent": "a", "stance": "for", "summary": "s", "confidence": json.Number("0.5"),
	}}}
	cases := []struct {
		name      string
		overrides map[string]any
		reason    string
	}{
		{"rounds under 0.1", map[string]any{"rounds": rounds}, "rounds not allowed in schema 0.1"},
		{"0.2 without rounds", map[string]any{"schema_version": "0.2"}, "schema 0.2 requires rounds"},
		{"valid 0.2", map[string]any{"schema_version": "0.2", "rounds": rounds}, ""},
	}
	for _, tc := range cases {
		path := writeLog(t, record(t, tc.overrides, genesisHash))
		result := verifyLog(path, "")
		if tc.reason == "" && !result.OK {
			t.Errorf("%s: expected ok, got %+v", tc.name, result)
		}
		if tc.reason != "" && (result.OK || result.Reason != tc.reason) {
			t.Errorf("%s: expected %q, got %+v", tc.name, tc.reason, result)
		}
	}
}

func TestDuplicateKeysRejected(t *testing.T) {
	first := record(t, nil, genesisHash)
	smuggled := `{"decision":"altered",` + first[1:]
	path := writeLog(t, smuggled)
	result := verifyLog(path, "")
	if result.OK || result.Reason != "duplicate key" {
		t.Fatalf("expected duplicate key, got %+v", result)
	}
}

func TestUnsafeIntegerRejected(t *testing.T) {
	// Inject the unsafe integer AFTER hashing — the canonicalizer itself
	// refuses to serialize it, so it can't be part of a valid record.
	valid := record(t, nil, genesisHash)
	tampered := bytes.Replace(
		[]byte(valid),
		[]byte(`"evidence":[]`),
		[]byte(`"evidence":[{"source":"x","ref":"y","weight":10000000000000000000000000}]`),
		1,
	)
	path := writeLog(t, string(tampered))
	result := verifyLog(path, "")
	if result.OK || result.Reason != "integer outside IEEE-754 safe range" {
		t.Fatalf("expected unsafe-integer rejection, got %+v", result)
	}
}

func TestTrailingDataRejected(t *testing.T) {
	first := record(t, nil, genesisHash)
	path := writeLog(t, first+` {"extra":true}`)
	result := verifyLog(path, "")
	if result.OK || result.Reason != "malformed record" {
		t.Fatalf("expected malformed record for trailing object, got %+v", result)
	}
	path = writeLog(t, first+" 42")
	result = verifyLog(path, "")
	if result.OK {
		t.Fatalf("expected rejection for trailing scalar, got %+v", result)
	}
}

func TestEmptyLogCheckpointHashChecked(t *testing.T) {
	dir := t.TempDir()
	logPath := filepath.Join(dir, "empty.jsonl")
	if err := os.WriteFile(logPath, []byte(""), 0o644); err != nil {
		t.Fatal(err)
	}
	headPath := filepath.Join(dir, "empty.jsonl.head")
	bogus := `{"count": 0, "head_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}`
	if err := os.WriteFile(headPath, []byte(bogus), 0o644); err != nil {
		t.Fatal(err)
	}
	result := verifyLog(logPath, headPath)
	if result.OK {
		t.Fatalf("expected mismatch for bogus empty-log checkpoint, got %+v", result)
	}
	genesis := `{"count": 0, "head_hash": "` + genesisHash + `"}`
	if err := os.WriteFile(headPath, []byte(genesis), 0o644); err != nil {
		t.Fatal(err)
	}
	result = verifyLog(logPath, headPath)
	if !result.OK {
		t.Fatalf("expected genesis checkpoint to verify an empty log, got %+v", result)
	}
}

func TestLoneSurrogatesRejected(t *testing.T) {
	first := record(t, nil, genesisHash)
	lone := bytes.Replace([]byte(first), []byte(`"q"`), []byte(`"q \ud800"`), 1)
	path := writeLog(t, string(lone))
	result := verifyLog(path, "")
	if result.OK || result.Reason != "lone surrogate in string" {
		t.Fatalf("expected lone-surrogate rejection, got %+v", result)
	}
	// A valid pair and a literal backslash-u (escaped backslash) both pass the scan.
	if loneSurrogateEscape([]byte(`"emoji 😀 ok"`)) {
		t.Fatal("valid surrogate pair wrongly flagged")
	}
	if loneSurrogateEscape([]byte(`"literal \\ud800 text"`)) {
		t.Fatal("escaped backslash wrongly flagged")
	}
	if !loneSurrogateEscape([]byte(`"low first \udc00"`)) {
		t.Fatal("lone low surrogate missed")
	}
}

func TestRunUsageAndVerify(t *testing.T) {
	first := record(t, nil, genesisHash)
	path := writeLog(t, first)
	var out, errOut bytes.Buffer
	if code := run([]string{path}, &out, &errOut); code != 0 {
		t.Fatalf("expected success, got %d: %s", code, errOut.String())
	}
	out.Reset()
	errOut.Reset()
	// The documented order (flags first) works with a head file too.
	if code := run([]string{"-head", path + ".missing", path}, &out, &errOut); code != 1 {
		t.Fatalf("expected checkpoint failure exit 1, got %d", code)
	}
	if code := run([]string{}, &out, &errOut); code != 2 {
		t.Fatalf("expected usage exit 2, got %d", code)
	}
}
