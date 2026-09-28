package nativecore

import (
	"errors"
	"sort"
	"strings"
	"unicode/utf8"

	ts "github.com/tree-sitter/go-tree-sitter"
	python "github.com/tree-sitter/tree-sitter-python/bindings/go"
	"golang.org/x/text/unicode/norm"
)

// PythonImports extracts static imports without executing code. A grammar error
// is never an empty dependency set. This parser is not a CPython validator.
func PythonImports(source string) ([]Import, error) {
	if !utf8.ValidString(source) || strings.ContainsRune(source, 0) {
		return nil, errors.New("invalid Python source")
	}
	p := ts.NewParser()
	defer p.Close()
	if err := p.SetLanguage(ts.NewLanguage(python.Language())); err != nil {
		return nil, err
	}
	tree := p.Parse([]byte(source), nil)
	if tree == nil {
		return nil, errors.New("Python parsing failed")
	}
	defer tree.Close()
	root := tree.RootNode()
	if root.HasError() {
		return nil, errors.New("unsupported or invalid Python syntax")
	}
	result := []Import{}
	queue := []*ts.Node{root}
	for len(queue) > 0 {
		n := queue[len(queue)-1]
		queue = queue[:len(queue)-1]
		switch n.Kind() {
		case "print_statement", "exec_statement":
			return nil, errors.New("Python 2 syntax is unsupported")
		case "import_statement", "import_from_statement", "future_import_statement":
			item := Import{Names: []string{}}
			if n.Kind() == "future_import_statement" {
				item.Module = "__future__"
			}
			if module := n.ChildByFieldName("module_name"); module != nil {
				// Assemble identifiers from the grammar, not whitespace-sensitive text.
				for i := uint(0); i < module.NamedChildCount(); i++ {
					child := module.NamedChild(i)
					if child.Kind() == "import_prefix" {
						item.Level = strings.Count(child.Utf8Text([]byte(source)), ".")
					}
					if child.Kind() == "dotted_name" {
						item.Module = dotted(child, source)
					}
				}
				if module.Kind() == "dotted_name" {
					item.Module = dotted(module, source)
				}
			}
			for i := uint(0); i < n.NamedChildCount(); i++ {
				child := n.NamedChild(i)
				if n.FieldNameForNamedChild(uint32(i)) == "name" {
					if child.Kind() == "aliased_import" {
						child = child.ChildByFieldName("name")
					}
					item.Names = append(item.Names, dotted(child, source))
				} else if child.Kind() == "wildcard_import" {
					item.Names = append(item.Names, "*")
				}
			}
			sort.Strings(item.Names)
			result = append(result, item)
		}
		for i := uint(0); i < n.NamedChildCount(); i++ {
			queue = append(queue, n.NamedChild(i))
		}
	}
	// Import traversal order is irrelevant to dependency closure; retain duplicates.
	sort.SliceStable(result, func(i, j int) bool {
		a, b := result[i], result[j]
		if a.Module != b.Module {
			return a.Module < b.Module
		}
		if a.Level != b.Level {
			return a.Level < b.Level
		}
		return strings.Join(a.Names, "\x00") < strings.Join(b.Names, "\x00")
	})
	return result, nil
}

func dotted(n *ts.Node, source string) string {
	if n == nil {
		return ""
	}
	names := []string{}
	for i := uint(0); i < n.NamedChildCount(); i++ {
		child := n.NamedChild(i)
		if child.Kind() == "identifier" {
			names = append(names, norm.NFKC.String(child.Utf8Text([]byte(source))))
		}
	}
	return strings.Join(names, ".")
}
