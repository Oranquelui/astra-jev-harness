package nativecore

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
)

// Execute runs one offline operation; no file or environment is accessed.
func Execute(raw []byte) (any, error) {
	value, err := Decode(raw)
	if err != nil {
		return nil, err
	}
	request, ok := value.(map[string]any)
	if !ok {
		return nil, errors.New("request must be an object")
	}
	op, _ := request["op"].(string)
	switch op {
	case "imports":
		source, ok := request["source"].(string)
		if !ok || len(source) > 100000 {
			return nil, errors.New("source must be at most 100000 UTF-8 bytes")
		}
		imports, err := PythonImports(source)
		if err != nil {
			return nil, err
		}
		items := []map[string]any{}
		for _, item := range imports {
			items = append(items, map[string]any{"module": item.Module, "level": item.Level, "names": item.Names})
		}
		return items, nil
	case "hash":
		payload, ok := request["value"]
		if !ok {
			return nil, errors.New("missing hash value")
		}
		canonical, err := JSON(payload, false)
		if err != nil {
			return nil, err
		}
		hash := sha256.Sum256(canonical)
		return map[string]any{"canonical_json": string(canonical), "sha256": hex.EncodeToString(hash[:])}, nil
	case "excerpt":
		path, ok1 := request["path"].(string)
		source, ok2 := request["text"].(string)
		start, ok3 := integer(request["start_line"])
		count, ok4 := integer(request["lines"])
		if !ok1 || !ok2 || !ok3 || !ok4 {
			return nil, errors.New("invalid excerpt arguments")
		}
		return Excerpt(path, source, start, count)
	case "page":
		base, ok1 := request["base"].(map[string]any)
		entries, ok2 := request["items"].([]any)
		offset, ok3 := integer(request["offset"])
		limit, ok4 := integer(request["max_bytes"])
		if !ok1 || !ok2 || !ok3 || !ok4 {
			return nil, errors.New("invalid page arguments")
		}
		items := []map[string]any{}
		for _, entry := range entries {
			item, ok := entry.(map[string]any)
			if !ok {
				return nil, errors.New("invalid page item")
			}
			items = append(items, item)
		}
		return Page(base, items, offset, limit)
	default:
		return nil, errors.New("unknown offline operation")
	}
}
