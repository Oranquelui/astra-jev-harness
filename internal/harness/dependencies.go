package harness

import (
	"go/parser"
	"go/token"
	"path"
	"regexp"
	"strconv"
	"strings"

	"github.com/Oranquelui/astra-jev-harness/internal/nativecore"
)

var jsImports = regexp.MustCompile(`(?:from\s+|require\s*\(\s*|import\s*\(?\s*)["']([^"']+)["']`)
var jsonComment = regexp.MustCompile(`"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/`)
var trailingComma = regexp.MustCompile(`"(?:\\.|[^"\\])*"|,\s*[}\]]`)

func jsonc(text string) M {
	text = jsonComment.ReplaceAllStringFunc(text, func(s string) string {
		if s[0] == '"' {
			return s
		}
		return " "
	})
	text = trailingComma.ReplaceAllStringFunc(text, func(s string) string {
		if s[0] == '"' {
			return s
		}
		return s[1:]
	})
	return object(decode([]byte(text)))
}
func normalized(base, s string) string {
	if strings.HasPrefix(s, "/") {
		return ""
	}
	v := path.Clean(path.Join(base, s))
	if v == ".." || strings.HasPrefix(v, "../") {
		return ""
	}
	return v
}
func tsOptions(files M, config string, seen M) M {
	need(seen[config] == nil, "Cyclic tsconfig")
	seen = clone(seen)
	seen[config] = true
	o := jsonc(str(files[config]))
	base := path.Dir(config)
	result := M{}
	if parent := sget(o, "extends"); parent != "" {
		need(strings.HasPrefix(parent, "."), "Unresolved tsconfig")
		parent = normalized(base, parent)
		if files[parent] == nil {
			parent += ".json"
		}
		need(files[parent] != nil, "Missing tsconfig")
		result = tsOptions(files, parent, seen)
	}
	options := obj(o, "compilerOptions")
	if options["baseUrl"] != nil {
		result["base"] = normalized(base, str(options["baseUrl"]))
	}
	if options["paths"] != nil {
		anchor := sget(result, "base")
		if anchor == "" {
			anchor = base
		}
		paths := M{}
		for k, v := range obj(options, "paths") {
			vs := []string{}
			for _, p := range stringsOf(v) {
				vs = append(vs, normalized(anchor, p))
			}
			paths[k] = vs
		}
		result["paths"] = paths
	}
	return result
}
func localCandidates(files M, p, spec string, python bool) []string {
	if python {
		roots := M{".": true}
		for name := range files {
			parts := strings.Split(name, "/")
			for i, part := range parts {
				if part == "src" {
					roots[strings.Join(parts[:i+1], "/")] = true
					break
				}
			}
		}
		out := []string{}
		for _, root := range keys(roots) {
			out = append(out, path.Join(root, spec))
		}
		return out
	}
	parent := path.Dir(p)
	if strings.HasPrefix(spec, ".") {
		return []string{normalized(parent, spec)}
	}
	config := ""
	for d := parent; ; d = path.Dir(d) {
		c := path.Join(d, "tsconfig.json")
		if files[c] != nil {
			config = c
			break
		}
		if d == "." {
			break
		}
	}
	out := []string{}
	if config != "" {
		err := guarded(func() {
			o := tsOptions(files, config, M{})
			for pattern, v := range obj(o, "paths") {
				before, after, star := strings.Cut(pattern, "*")
				match := spec == pattern
				if star {
					match = strings.HasPrefix(spec, before) && strings.HasSuffix(spec, after) && len(spec) >= len(before)+len(after)
				}
				if match {
					for _, t := range stringsOf(v) {
						if t == "" {
							continue
						}
						if star {
							t = strings.ReplaceAll(t, "*", spec[len(before):len(spec)-len(after)])
						}
						out = append(out, t)
					}
				}
			}
			if base := sget(o, "base"); base != "" {
				out = append(out, normalized(base, spec))
			}
		})
		if err != nil {
			scope := path.Dir(config)
			for p := range files {
				if scope == "." || strings.HasPrefix(p, scope+"/") {
					out = append(out, p)
				}
			}
		}
	}
	for name, source := range files {
		if path.Base(name) != "package.json" {
			continue
		}
		var pkg string
		if guarded(func() { pkg = sget(object(decode([]byte(str(source)))), "name") }) != nil {
			continue
		}
		if pkg != "" && (spec == pkg || strings.HasPrefix(spec, pkg+"/")) {
			scope := path.Dir(name)
			for p := range files {
				if scope == "." || strings.HasPrefix(p, scope+"/") {
					out = append(out, p)
				}
			}
		}
	}
	return out
}
func variants(stem string) []string {
	if stem == "" {
		return nil
	}
	stem = path.Clean(stem)
	stems := []string{stem}
	if contains([]string{".js", ".mjs", ".cjs"}, path.Ext(stem)) {
		stems = append(stems, strings.TrimSuffix(stem, path.Ext(stem)))
	}
	out := []string{}
	for _, s := range stems {
		for _, ext := range []string{"", ".py", "/__init__.py", ".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs", "/index.ts", "/index.tsx", "/index.js", "/index.mts"} {
			out = append(out, s+ext)
		}
	}
	return out
}
func dependencies(files M, selected []string) []string {
	keep := set(selected)
	for p := range files {
		base := path.Base(p)
		if isInstruction(p) || contains([]string{"go.mod", "go.work", "package.json", "tsconfig.json", "pyproject.toml", "requirements.txt", "pytest.ini", "setup.cfg", "conftest.py"}, base) || strings.HasPrefix(base, "tsconfig") && strings.HasSuffix(base, ".json") {
			keep[p] = true
		}
	}
	queue := keys(keep)
	add := func(p string) {
		if files[p] != nil && keep[p] == nil {
			keep[p] = true
			queue = append(queue, p)
		}
	}
	for len(queue) > 0 {
		p := queue[len(queue)-1]
		queue = queue[:len(queue)-1]
		source := str(files[p])
		imports := []string{}
		if strings.HasSuffix(p, ".go") {
			for name := range files {
				if strings.HasSuffix(name, ".go") && path.Dir(name) == path.Dir(p) {
					add(name)
				}
			}
			tree, err := parser.ParseFile(token.NewFileSet(), p, source, parser.ImportsOnly)
			if err != nil {
				for name := range files {
					if strings.HasSuffix(name, ".go") {
						add(name)
					}
				}
			} else {
				for _, im := range tree.Imports {
					spec, err := strconv.Unquote(im.Path.Value)
					if err != nil {
						continue
					}
					for name, body := range files {
						if path.Base(name) != "go.mod" {
							continue
						}
						match := regexp.MustCompile(`(?m)^\s*module\s+(\S+)`).FindStringSubmatch(str(body))
						if len(match) != 2 {
							continue
						}
						module := strings.Trim(match[1], `"`)
						if spec != module && !strings.HasPrefix(spec, module+"/") {
							continue
						}
						dir := path.Join(path.Dir(name), strings.TrimPrefix(strings.TrimPrefix(spec, module), "/"))
						for f := range files {
							if strings.HasSuffix(f, ".go") && path.Dir(f) == dir {
								add(f)
							}
						}
					}
				}
			}
		} else if strings.HasSuffix(p, ".py") {
			for d := path.Dir(p); ; d = path.Dir(d) {
				add(path.Join(d, "__init__.py"))
				if d == "." {
					break
				}
			}
			parsed, err := nativecore.PythonImports(source)
			if err != nil {
				// Unknown syntax must not silently prove absence of dependencies. Preserve
				// Python scope conservatively; the parser is not a CPython validator.
				for name := range files {
					if strings.HasSuffix(name, ".py") {
						add(name)
					}
				}
			} else {
				for _, im := range parsed {
					module := strings.ReplaceAll(im.Module, ".", "/")
					if im.Level == 0 && im.Module == "" {
						for _, name := range im.Names {
							imports = append(imports, localCandidates(files, p, strings.ReplaceAll(name, ".", "/"), true)...)
						}
						continue
					}
					base := path.Dir(p)
					for i := 0; i < im.Level-1; i++ {
						base = path.Dir(base)
					}
					bases := []string{}
					if im.Level > 0 {
						bases = []string{path.Join(base, module)}
					} else {
						bases = localCandidates(files, p, module, true)
					}
					imports = append(imports, bases...)
					for _, b := range bases {
						for _, name := range im.Names {
							imports = append(imports, path.Join(b, name))
						}
					}
				}
			}
		} else {
			for _, m := range jsImports.FindAllStringSubmatch(source, -1) {
				imports = append(imports, localCandidates(files, p, m[1], false)...)
			}
		}
		for _, stem := range imports {
			for _, dep := range variants(stem) {
				add(dep)
			}
		}
	}
	return keys(keep)
}
