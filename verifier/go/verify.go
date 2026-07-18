// Record and chain verification per SPEC.md — mirrors the Python reference.
package main

import (
	"bufio"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"regexp"
	"strings"
	"time"
	"unicode/utf8"
)

const genesisHash = "0000000000000000000000000000000000000000000000000000000000000000"

var hexHash = regexp.MustCompile(`^[0-9a-f]{64}$`)

var requiredFields = []string{
	"schema_version", "timestamp", "subject", "positions", "decision",
	"dissent", "confidence", "evidence", "prev_hash", "hash",
}

type VerifyResult struct {
	OK       bool
	Count    int
	BrokenAt int
	Reason   string
}

func fail(count, index int, reason string) VerifyResult {
	return VerifyResult{OK: false, Count: count, BrokenAt: index, Reason: reason}
}

func contentHash(payload map[string]any) (string, error) {
	var buf bytes.Buffer
	if err := canonicalize(payload, &buf, true); err != nil {
		return "", err
	}
	sum := sha256.Sum256(buf.Bytes())
	return hex.EncodeToString(sum[:]), nil
}

func verifyLog(path string, headPath string) VerifyResult {
	file, err := os.Open(path)
	if err != nil {
		return fail(0, -1, fmt.Sprintf("cannot open log: %v", err))
	}
	defer file.Close()

	prev := genesisHash
	count := 0
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 0, 1024*1024), 16*1024*1024)
	for scanner.Scan() {
		line := scanner.Bytes()
		if len(bytes.TrimSpace(line)) == 0 {
			continue
		}
		if !utf8.Valid(line) {
			return fail(count, count, "invalid encoding")
		}
		payload, err := parseLine(line)
		if err != nil {
			if strings.Contains(err.Error(), "duplicate key") {
				return fail(count, count, "duplicate key")
			}
			return fail(count, count, "malformed record")
		}
		if reason := recordViolation(payload); reason != "" {
			return fail(count, count, reason)
		}
		if payload["prev_hash"].(string) != prev {
			return fail(count, count, "broken chain link")
		}
		computed, err := contentHash(payload)
		if err != nil {
			return fail(count, count, err.Error())
		}
		if computed != payload["hash"].(string) {
			return fail(count, count, "content hash mismatch")
		}
		prev = payload["hash"].(string)
		count++
	}
	if err := scanner.Err(); err != nil {
		return fail(count, count, "invalid encoding")
	}
	if headPath != "" {
		if reason := checkHead(headPath, count, prev); reason != "" {
			return fail(count, -1, reason)
		}
	}
	return VerifyResult{OK: true, Count: count, BrokenAt: -1}
}

func checkHead(path string, count int, head string) string {
	raw, err := os.ReadFile(path)
	if err != nil {
		return "malformed head checkpoint"
	}
	payload, err := parseLine(bytes.TrimSpace(raw))
	if err != nil {
		return "malformed head checkpoint"
	}
	expectedCount, ok := intField(payload, "count")
	if !ok || expectedCount < 0 {
		return "malformed head checkpoint"
	}
	expectedHash, ok := payload["head_hash"].(string)
	if !ok || !hexHash.MatchString(expectedHash) {
		return "malformed head checkpoint"
	}
	// head is genesisHash for an empty log, so the comparison holds for
	// count == 0 too — a mismatched checkpoint must never pass on emptiness.
	if int(expectedCount) != count || expectedHash != head {
		return "head checkpoint mismatch (possible truncation)"
	}
	return ""
}

func recordViolation(payload map[string]any) string {
	for _, field := range requiredFields {
		if _, ok := payload[field]; !ok {
			return "malformed record"
		}
	}
	version, ok := payload["schema_version"].(string)
	if !ok {
		return "invalid schema_version type"
	}
	if version != "0.1" && version != "0.2" {
		return "unsupported schema version"
	}
	_, hasRounds := payload["rounds"]
	if version == "0.2" && !hasRounds {
		return "schema 0.2 requires rounds"
	}
	if version == "0.1" && hasRounds {
		return "rounds not allowed in schema 0.1"
	}
	if reason := numericViolation(payload); reason != "" {
		return reason
	}
	for _, field := range []string{"subject", "decision", "timestamp"} {
		if _, ok := payload[field].(string); !ok {
			return fmt.Sprintf("invalid %s type", field)
		}
	}
	for _, field := range []string{"positions", "dissent"} {
		entries, ok := payload[field].([]any)
		if !ok {
			return fmt.Sprintf("invalid %s structure", field)
		}
		for _, entry := range entries {
			if reason := positionViolation(entry, field); reason != "" {
				return reason
			}
		}
	}
	if hasRounds {
		rounds, ok := payload["rounds"].([]any)
		if !ok {
			return "invalid rounds structure"
		}
		for _, roundValue := range rounds {
			positions, ok := roundValue.([]any)
			if !ok {
				return "invalid rounds structure"
			}
			for _, entry := range positions {
				if reason := positionViolation(entry, "rounds"); reason != "" {
					return "invalid rounds entry"
				}
			}
		}
	}
	evidence, ok := payload["evidence"].([]any)
	if !ok {
		return "invalid evidence structure"
	}
	for _, item := range evidence {
		entry, ok := item.(map[string]any)
		if !ok {
			return "invalid evidence structure"
		}
		if _, ok := entry["source"].(string); !ok {
			return "invalid evidence entry"
		}
		if _, ok := entry["ref"].(string); !ok {
			return "invalid evidence entry"
		}
	}
	if !validConfidence(payload["confidence"]) {
		return "invalid confidence"
	}
	for _, field := range []string{"hash", "prev_hash"} {
		value, ok := payload[field].(string)
		if !ok || !hexHash.MatchString(value) {
			return fmt.Sprintf("invalid %s format", field)
		}
	}
	timestamp := payload["timestamp"].(string)
	parsed, err := time.Parse(time.RFC3339, strings.Replace(timestamp, " ", "T", 1))
	if err != nil {
		return "invalid timestamp"
	}
	if _, offset := parsed.Zone(); offset != 0 {
		return "timestamp not UTC"
	}
	return ""
}

func positionViolation(value any, field string) string {
	entry, ok := value.(map[string]any)
	if !ok {
		return fmt.Sprintf("invalid %s entry", field)
	}
	for _, key := range []string{"agent", "stance", "summary"} {
		if _, ok := entry[key].(string); !ok {
			return fmt.Sprintf("invalid %s entry", field)
		}
	}
	if !validConfidence(entry["confidence"]) {
		return fmt.Sprintf("invalid %s entry", field)
	}
	return ""
}

func validConfidence(value any) bool {
	number, ok := value.(json.Number)
	if !ok {
		return false
	}
	f, err := number.Float64()
	if err != nil {
		return false
	}
	return f >= 0 && f <= 1
}

func numericViolation(value any) string {
	switch v := value.(type) {
	case map[string]any:
		for _, item := range v {
			if reason := numericViolation(item); reason != "" {
				return reason
			}
		}
	case []any:
		for _, item := range v {
			if reason := numericViolation(item); reason != "" {
				return reason
			}
		}
	case json.Number:
		if _, err := pyNumber(v); err != nil {
			return err.Error()
		}
	}
	return ""
}

func intField(payload map[string]any, key string) (int64, bool) {
	number, ok := payload[key].(json.Number)
	if !ok {
		return 0, false
	}
	if !intPattern.MatchString(number.String()) {
		return 0, false
	}
	value, err := number.Int64()
	if err != nil {
		return 0, false
	}
	return value, true
}
