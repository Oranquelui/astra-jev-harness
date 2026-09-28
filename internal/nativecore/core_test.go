package nativecore

import (
	"encoding/json"
	"reflect"
	"strings"
	"testing"
)

func TestImportsIgnoreStringsAndKeepNestedRelativeAliases(t *testing.T) {
	source := "\"\"\"import fake\"\"\"\n# import fake2\nimport os.path as p, sys\nfrom ..pkg import (one as x, two)\ndef f():\n    import nested\n"
	got, err := PythonImports(source)
	want := []Import{{"", 0, []string{"nested"}}, {"", 0, []string{"os.path", "sys"}}, {"pkg", 2, []string{"one", "two"}}}
	if err != nil || !reflect.DeepEqual(got, want) {
		t.Fatalf("imports = %#v, %v", got, err)
	}
}

func TestMalformedSourceIsNotAnEmptyDependencySet(t *testing.T) {
	if _, err := PythonImports("from pkg import (\n"); err == nil {
		t.Fatal("malformed Python accepted")
	}
}

func TestCanonicalJSONPreservesPythonNumbersAndUnicode(t *testing.T) {
	got, err := CanonicalJSON([]byte(`{"z":1.0,"日本":"<>&\u2028","b":-0.0,"a":9007199254740993,"e":1e-5,"d":1e15}`))
	want := "{\"a\":9007199254740993,\"b\":-0.0,\"d\":1000000000000000.0,\"e\":1e-05,\"z\":1.0,\"日本\":\"<>&\u2028\"}"
	if err != nil || string(got) != want {
		t.Fatalf("got %q, %v; want %q", got, err, want)
	}
	for _, raw := range []string{`{"x":NaN}`, `{"x":1e999}`, `{} {}`, `"\ud800"`} {
		if _, err := CanonicalJSON([]byte(raw)); err == nil {
			t.Errorf("invalid input accepted: %s", raw)
		}
	}
}

func TestCanonicalJSONEscapesAndExtremeNumbers(t *testing.T) {
	for _, tc := range []struct{ raw, want string }{
		{`"\ud83d\ude00"`, `"😀"`}, {`"\\ud800"`, `"\\ud800"`},
		{`-0`, `0`}, {`1e-999`, `0.0`}, {`[1.0,1,1e20]`, `[1.0,1,1e+20]`},
	} {
		got, err := CanonicalJSON([]byte(tc.raw))
		if err != nil || string(got) != tc.want {
			t.Errorf("%s: %s %v", tc.raw, got, err)
		}
	}
	for _, raw := range [][]byte{[]byte(`"\udc00"`), []byte(`"\ud800x"`), {'"', 0xff, '"'}} {
		if _, err := CanonicalJSON(raw); err == nil {
			t.Errorf("invalid Unicode accepted: %q", raw)
		}
	}
}

func TestPagePaginationAndBounds(t *testing.T) {
	items := []map[string]any{}
	for n := 0; n < 6; n++ {
		item, err := Excerpt(strings.Repeat("p", 60), strings.Repeat("a", 100)+"\n", 1, 1)
		if err != nil {
			t.Fatal(err)
		}
		items = append(items, item)
	}
	seen := 0
	offset := 0
	for {
		page, err := Page(map[string]any{"status": "test"}, items, offset, 1024)
		if err != nil {
			t.Fatal(err)
		}
		encoded, err := JSON(page, true)
		if err != nil || len(encoded)+1 > 1024 {
			t.Fatal("exceeded full response cap")
		}
		seen += len(page["items"].([]map[string]any))
		if page["next_offset"] == nil {
			break
		}
		next := page["next_offset"].(int)
		if next <= offset {
			t.Fatal("pagination did not advance")
		}
		offset = next
	}
	if seen != len(items) {
		t.Fatal("lost candidates", seen)
	}
	for _, offset := range []int{-1, 7} {
		if _, err := Page(nil, items, offset, 1024); err == nil {
			t.Fatal("invalid offset accepted")
		}
	}
	if _, err := Page(nil, items, 0, 24001); err == nil {
		t.Fatal("invalid byte cap accepted")
	}
}

func TestImportUnicodeAndWildcard(t *testing.T) {
	got, err := PythonImports("import K\nfrom ... import *\n")
	want := []Import{{"", 0, []string{"K"}}, {"", 3, []string{"*"}}}
	if err != nil || !reflect.DeepEqual(got, want) {
		t.Fatal(got, err)
	}
}

func TestExcerptPreservesOriginalLineTerminators(t *testing.T) {
	got, err := Excerpt("日本.py", "a\r\nb\rc\u2028d\n", 2, 2)
	if err != nil || got["text"] != "b\rc\u2028" || got["total_lines"] != 4 || got["start_line"] != 2 || got["end_line"] != 3 {
		t.Fatalf("%#v %v", got, err)
	}
	if !reflect.DeepEqual(got["unpresented_ranges"], [][2]int{{1, 1}, {4, 4}}) {
		t.Fatal(got)
	}
}

func TestPageLongLineMakesExplicitLeadAndPreservesInput(t *testing.T) {
	item, err := Excerpt("a.py", strings.Repeat("日", 2000)+"\nnext\n", 1, 2)
	if err != nil {
		t.Fatal(err)
	}
	before, _ := json.Marshal(item)
	got, err := Page(map[string]any{"status": "test"}, []map[string]any{item}, 0, 1024)
	if err != nil {
		t.Fatal(err)
	}
	items := got["items"].([]map[string]any)
	if len(items) != 1 || items[0]["text"] != "" || items[0]["reason"] != "source_line_exceeds_output_budget_use_read" {
		t.Fatal(got)
	}
	after, _ := json.Marshal(item)
	if string(before) != string(after) {
		t.Fatal("mutated input")
	}
}
