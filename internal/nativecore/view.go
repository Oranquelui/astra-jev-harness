package nativecore

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"unicode/utf8"
)

func splitLines(s string) []string {
	lines := []string{}
	start := 0
	skipLF := false
	for pos, r := range s {
		if skipLF && r == '\n' {
			start = pos + 1
			skipLF = false
			continue
		}
		skipLF = false
		if strings.ContainsRune("\n\r\v\f\x1c\x1d\x1e\u0085\u2028\u2029", r) {
			end := pos + utf8.RuneLen(r)
			if r == '\r' && end < len(s) && s[end] == '\n' {
				end++
				skipLF = true
			}
			lines = append(lines, s[start:end])
			start = end
		}
	}
	if start < len(s) {
		lines = append(lines, s[start:])
	}
	return lines
}

func Excerpt(path, text string, start, count int) (map[string]any, error) {
	if start < 1 || count < 1 || count > 200 || !utf8.ValidString(text) || !utf8.ValidString(path) {
		return nil, errors.New("invalid excerpt arguments")
	}
	lines := splitLines(text)
	total := len(lines)
	start = min(start, max(1, total))
	end := min(start-1+count, total)
	hash := sha256.Sum256([]byte(text))
	return map[string]any{"path": path, "source_sha256": hex.EncodeToString(hash[:]), "start_line": start, "end_line": end, "total_lines": total,
		"text": strings.Join(lines[start-1:end], ""), "unpresented_ranges": missing(start, end, total)}, nil
}

func missing(start, end, total int) [][2]int {
	ranges := [][2]int{}
	if start > 1 {
		ranges = append(ranges, [2]int{1, start - 1})
	}
	if end < total {
		ranges = append(ranges, [2]int{end + 1, total})
	}
	return ranges
}

func copyMap(src map[string]any) map[string]any {
	dst := make(map[string]any, len(src))
	for k, v := range src {
		dst[k] = v
	}
	return dst
}

func Page(base map[string]any, candidates []map[string]any, offset, limit int) (map[string]any, error) {
	if offset < 0 || offset > len(candidates) || limit < 1024 || limit > 24000 {
		return nil, errors.New("invalid page bounds")
	}
	result := copyMap(base)
	result["items"] = []map[string]any{}
	result["offset"] = offset
	result["total_items"] = len(candidates)
	result["next_offset"] = nil
	result["output_limit_bytes"] = limit
	result["provider_calls"] = 0
	for index := offset; index < len(candidates); index++ {
		item := copyMap(candidates[index])
		var next any
		if index+1 < len(candidates) {
			next = index + 1
		}
		for {
			trial := copyMap(result)
			items := result["items"].([]map[string]any)
			trial["items"] = append(append([]map[string]any{}, items...), item)
			trial["next_offset"] = next
			encoded, err := JSON(trial, true)
			if err != nil {
				return nil, err
			}
			if len(encoded)+1 <= limit {
				result = trial
				break
			}
			if len(items) > 0 {
				result["next_offset"] = index
				return result, nil
			}
			text, ok := item["text"].(string)
			if !ok || text == "" {
				return nil, errors.New("metadata exceeds output budget")
			}
			start, ok1 := integer(item["start_line"])
			end, ok2 := integer(item["end_line"])
			total, ok3 := integer(item["total_lines"])
			if !ok1 || !ok2 || !ok3 || start < 1 || end < start || end > total {
				return nil, errors.New("invalid source range")
			}
			lines := splitLines(text)
			item["text"] = strings.Join(lines[:len(lines)-1], "")
			item["end_line"] = end - 1
			item["unpresented_ranges"] = missing(start, end-1, total)
			if item["text"] == "" {
				item["reason"] = "source_line_exceeds_output_budget_use_read"
			}
		}
	}
	encoded, err := JSON(result, true)
	if err != nil {
		return nil, err
	}
	if len(encoded)+1 > limit {
		return nil, errors.New("metadata exceeds output budget")
	}
	return result, nil
}
