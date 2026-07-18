// Canonicalization per SPEC.md: an independent implementation of the exact
// serialization profile (sorted keys, compact separators, lowercase \uXXXX
// ASCII escaping, CPython float spelling) proving the format is a standard,
// not a Python artifact.
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"unicode/utf16"
)

var intPattern = regexp.MustCompile(`^-?[0-9]+$`)

const maxSafeInt = int64(1) << 53

// decodeStrict parses one JSON value, rejecting duplicate keys at any level
// (parsers disagree on duplicate resolution, so a duplicate gives one hashed
// record multiple readings) and preserving numbers as literals.
func decodeStrict(dec *json.Decoder) (any, error) {
	tok, err := dec.Token()
	if err != nil {
		return nil, err
	}
	return decodeValue(dec, tok)
}

func decodeValue(dec *json.Decoder, tok json.Token) (any, error) {
	switch t := tok.(type) {
	case json.Delim:
		switch t {
		case '{':
			obj := map[string]any{}
			for dec.More() {
				keyTok, err := dec.Token()
				if err != nil {
					return nil, err
				}
				key, ok := keyTok.(string)
				if !ok {
					return nil, fmt.Errorf("non-string key")
				}
				if _, exists := obj[key]; exists {
					return nil, fmt.Errorf("duplicate key: %s", key)
				}
				valTok, err := dec.Token()
				if err != nil {
					return nil, err
				}
				val, err := decodeValue(dec, valTok)
				if err != nil {
					return nil, err
				}
				obj[key] = val
			}
			if _, err := dec.Token(); err != nil { // consume '}'
				return nil, err
			}
			return obj, nil
		case '[':
			arr := []any{}
			for dec.More() {
				valTok, err := dec.Token()
				if err != nil {
					return nil, err
				}
				val, err := decodeValue(dec, valTok)
				if err != nil {
					return nil, err
				}
				arr = append(arr, val)
			}
			if _, err := dec.Token(); err != nil { // consume ']'
				return nil, err
			}
			return arr, nil
		}
		return nil, fmt.Errorf("unexpected delimiter %v", t)
	default:
		return tok, nil // string, json.Number, bool, nil
	}
}

func parseLine(line []byte) (map[string]any, error) {
	dec := json.NewDecoder(bytes.NewReader(line))
	dec.UseNumber()
	value, err := decodeStrict(dec)
	if err != nil {
		return nil, err
	}
	// A line must be exactly one JSON object — trailing data would let a
	// second, unhashed object ride along on a certified line.
	if _, err := dec.Token(); err != io.EOF {
		return nil, fmt.Errorf("trailing data after JSON object")
	}
	obj, ok := value.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("not a JSON object")
	}
	return obj, nil
}

// canonicalize renders a parsed value in the SPEC profile, excluding the
// top-level "hash" key when skipHash is set.
func canonicalize(value any, buf *bytes.Buffer, skipHash bool) error {
	switch v := value.(type) {
	case map[string]any:
		keys := make([]string, 0, len(v))
		for key := range v {
			if skipHash && key == "hash" {
				continue
			}
			keys = append(keys, key)
		}
		sort.Strings(keys)
		buf.WriteByte('{')
		for i, key := range keys {
			if i > 0 {
				buf.WriteByte(',')
			}
			writePyString(buf, key)
			buf.WriteByte(':')
			if err := canonicalize(v[key], buf, false); err != nil {
				return err
			}
		}
		buf.WriteByte('}')
	case []any:
		buf.WriteByte('[')
		for i, item := range v {
			if i > 0 {
				buf.WriteByte(',')
			}
			if err := canonicalize(item, buf, false); err != nil {
				return err
			}
		}
		buf.WriteByte(']')
	case string:
		writePyString(buf, v)
	case json.Number:
		rendered, err := pyNumber(v)
		if err != nil {
			return err
		}
		buf.WriteString(rendered)
	case bool:
		if v {
			buf.WriteString("true")
		} else {
			buf.WriteString("false")
		}
	case nil:
		buf.WriteString("null")
	default:
		return fmt.Errorf("unsupported value type %T", value)
	}
	return nil
}

// writePyString matches Python json.dumps default escaping: RFC 8259 short
// escapes, \uXXXX (lowercase hex) for everything non-ASCII and control,
// surrogate pairs above the BMP.
func writePyString(buf *bytes.Buffer, s string) {
	buf.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			buf.WriteString(`\"`)
		case '\\':
			buf.WriteString(`\\`)
		case '\n':
			buf.WriteString(`\n`)
		case '\r':
			buf.WriteString(`\r`)
		case '\t':
			buf.WriteString(`\t`)
		case '\b':
			buf.WriteString(`\b`)
		case '\f':
			buf.WriteString(`\f`)
		default:
			switch {
			case r < 0x20 || r > 0x7e && r <= 0xffff:
				fmt.Fprintf(buf, `\u%04x`, r)
			case r > 0xffff:
				hi, lo := utf16.EncodeRune(r)
				fmt.Fprintf(buf, `\u%04x\u%04x`, hi, lo)
			default:
				buf.WriteRune(r)
			}
		}
	}
	buf.WriteByte('"')
}

// pyNumber renders a JSON number literal in CPython repr/json.dumps spelling.
func pyNumber(n json.Number) (string, error) {
	literal := n.String()
	if intPattern.MatchString(literal) {
		value, err := strconv.ParseInt(literal, 10, 64)
		if err != nil {
			return "", fmt.Errorf("integer outside IEEE-754 safe range")
		}
		if value > maxSafeInt || value < -maxSafeInt {
			return "", fmt.Errorf("integer outside IEEE-754 safe range")
		}
		return strconv.FormatInt(value, 10), nil
	}
	f, err := n.Float64()
	if err != nil {
		return "", err
	}
	if math.IsNaN(f) || math.IsInf(f, 0) {
		return "", fmt.Errorf("non-finite number")
	}
	return pyFloatRepr(f), nil
}

func pyFloatRepr(f float64) string {
	if f == 0 {
		if math.Signbit(f) {
			return "-0.0"
		}
		return "0.0"
	}
	// Shortest round-trip in exponent form gives the decimal exponent.
	eForm := strconv.FormatFloat(f, 'e', -1, 64) // e.g. "1e-07", "1.5e+20"
	expIndex := strings.IndexByte(eForm, 'e')
	exponent, _ := strconv.Atoi(eForm[expIndex+1:])
	if exponent >= 16 || exponent <= -5 {
		// Go's 'e' format already matches Python: sign + >=2-digit exponent.
		return eForm
	}
	decimal := strconv.FormatFloat(f, 'f', -1, 64)
	if !strings.ContainsRune(decimal, '.') {
		decimal += ".0"
	}
	return decimal
}
