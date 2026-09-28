package nativecore

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"reflect"
	"sort"
	"strconv"
	"strings"
	"unicode/utf8"
)

// Decode preserves integer precision and the Python distinction between 1 and
// 1.0. Unpaired surrogates are rejected instead of silently replacing source.
func Decode(raw []byte) (any, error) {
	if !utf8.Valid(raw) || !json.Valid(raw) {
		return nil, errors.New("invalid JSON")
	}
	for i := 0; i < len(raw); i++ {
		if raw[i] != '\\' {
			continue
		}
		i++
		if raw[i] != 'u' {
			continue
		}
		n, _ := strconv.ParseUint(string(raw[i+1:i+5]), 16, 16)
		i += 4
		if n >= 0xdc00 && n <= 0xdfff {
			return nil, errors.New("unpaired Unicode surrogate")
		}
		if n >= 0xd800 && n <= 0xdbff {
			if i+6 >= len(raw) || string(raw[i+1:i+3]) != "\\u" {
				return nil, errors.New("unpaired Unicode surrogate")
			}
			low, _ := strconv.ParseUint(string(raw[i+3:i+7]), 16, 16)
			if low < 0xdc00 || low > 0xdfff {
				return nil, errors.New("unpaired Unicode surrogate")
			}
			i += 6
		}
	}
	d := json.NewDecoder(bytes.NewReader(raw))
	d.UseNumber()
	var value any
	if err := d.Decode(&value); err != nil {
		return nil, err
	}
	return value, nil
}

func CanonicalJSON(raw []byte) ([]byte, error) {
	v, err := Decode(raw)
	if err != nil {
		return nil, err
	}
	return JSON(v, false)
}

// JSON follows the existing Python JSON serialization for supported JSON types.
// Sorting keys does not alter the serialized size of presentation objects.
func JSON(value any, spaced bool) ([]byte, error) {
	var out bytes.Buffer
	err := encodeJSON(&out, reflect.ValueOf(value), spaced)
	return out.Bytes(), err
}

func encodeJSON(out *bytes.Buffer, v reflect.Value, spaced bool) error {
	if !v.IsValid() {
		out.WriteString("null")
		return nil
	}
	if v.Kind() == reflect.Interface {
		if v.IsNil() {
			out.WriteString("null")
			return nil
		}
		return encodeJSON(out, v.Elem(), spaced)
	}
	if v.Type() == reflect.TypeOf(json.Number("")) {
		n := v.Interface().(json.Number).String()
		if strings.ContainsAny(n, ".eE") {
			f, err := strconv.ParseFloat(n, 64)
			if err != nil || math.IsInf(f, 0) || math.IsNaN(f) {
				return errors.New("nonfinite number")
			}
			out.WriteString(pythonFloat(f))
		} else {
			if !json.Valid([]byte(n)) {
				return errors.New("invalid number")
			}
			if n == "-0" {
				n = "0"
			}
			out.WriteString(n)
		}
		return nil
	}
	separator, colon := ",", ":"
	if spaced {
		separator, colon = ", ", ": "
	}
	switch v.Kind() {
	case reflect.Bool:
		out.WriteString(strconv.FormatBool(v.Bool()))
	case reflect.String:
		return quoteJSON(out, v.String())
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64:
		out.WriteString(strconv.FormatInt(v.Int(), 10))
	case reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64:
		out.WriteString(strconv.FormatUint(v.Uint(), 10))
	case reflect.Float32, reflect.Float64:
		f := v.Float()
		if math.IsNaN(f) || math.IsInf(f, 0) {
			return errors.New("nonfinite number")
		}
		out.WriteString(pythonFloat(f))
	case reflect.Map:
		if v.Type().Key().Kind() != reflect.String {
			return errors.New("JSON object keys must be strings")
		}
		keys := v.MapKeys()
		sort.Slice(keys, func(i, j int) bool { return keys[i].String() < keys[j].String() })
		out.WriteByte('{')
		for i, key := range keys {
			if i > 0 {
				out.WriteString(separator)
			}
			if err := quoteJSON(out, key.String()); err != nil {
				return err
			}
			out.WriteString(colon)
			if err := encodeJSON(out, v.MapIndex(key), spaced); err != nil {
				return err
			}
		}
		out.WriteByte('}')
	case reflect.Slice, reflect.Array:
		out.WriteByte('[')
		for i := 0; i < v.Len(); i++ {
			if i > 0 {
				out.WriteString(separator)
			}
			if err := encodeJSON(out, v.Index(i), spaced); err != nil {
				return err
			}
		}
		out.WriteByte(']')
	default:
		return errors.New("unsupported JSON type")
	}
	return nil
}

func pythonFloat(f float64) string {
	e := strconv.FormatFloat(f, 'e', -1, 64)
	exponent, _ := strconv.Atoi(e[strings.LastIndexByte(e, 'e')+1:])
	if exponent >= -4 && exponent < 16 {
		s := strconv.FormatFloat(f, 'f', -1, 64)
		if !strings.Contains(s, ".") {
			s += ".0"
		}
		return s
	}
	return e
}

func quoteJSON(out *bytes.Buffer, s string) error {
	if !utf8.ValidString(s) {
		return errors.New("invalid UTF-8")
	}
	out.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"', '\\':
			out.WriteByte('\\')
			out.WriteRune(r)
		case '\b':
			out.WriteString(`\b`)
		case '\f':
			out.WriteString(`\f`)
		case '\n':
			out.WriteString(`\n`)
		case '\r':
			out.WriteString(`\r`)
		case '\t':
			out.WriteString(`\t`)
		default:
			if r < 0x20 {
				fmt.Fprintf(out, `\u%04x`, r)
			} else {
				out.WriteRune(r)
			}
		}
	}
	out.WriteByte('"')
	return nil
}

func integer(v any) (int, bool) {
	switch n := v.(type) {
	case int:
		return n, true
	case json.Number:
		i, err := strconv.Atoi(n.String())
		return i, err == nil
	default:
		return 0, false
	}
}
