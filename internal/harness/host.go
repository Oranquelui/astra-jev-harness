package harness

import (
	"path"
	"path/filepath"
	"sort"
	"time"

	"github.com/Oranquelui/astra-jev-harness/internal/nativecore"
)

func childFields(host string) M {
	if host == "desktop" {
		return M{"astra_child_calls": 0}
	}
	return M{"child_generation_calls": 0}
}
func hostPlan(dir, host string) M {
	p := loadPlan(dir)
	need(p["surface"] == host, "Wrong host plan")
	return p
}
func hostRecord(dir, host string, statuses []string) M {
	r := load(filepath.Join(dir, "selection.json"))
	need(r["surface"] == host && contains(statuses, sget(r, "status")), "Unexpected selection record; inspect attempts before retry")
	return r
}
func hostMakePlan(host, repo, task, out string, includes, focus []string, cap int) M {
	p := snapshot(repo, task, out, includes, focus, []string{}, []string{}, cap, 2000000)
	p["surface"] = host
	save(filepath.Join(out, "plan.json"), p)
	return p
}
func (r *Runtime) hostSelect(host, planDir, out, policy, cache, evidence, mode string, cap int, required bool) M {
	planDir, out = absolute(planDir), absolute(out)
	p := hostPlan(planDir, host)
	fresh(p)
	var packet M
	if evidence != "" {
		packet = evidenceCheck(evidence)
		need(packet["task"] == p["task"], "Evidence task differs")
	}
	need(!within(out, str(p["repo"])) && !exists(out), "Use new output outside repository")
	if cache != "" {
		need(!within(absolute(cache), str(p["repo"])), "Cache inside repository")
	}
	need(policy == "batch" || policy == "per-file", "Unknown policy")
	route := selectionRoute(p, mode)
	if required {
		need(route == "jev" && len(batches(p)) > 0, "Jev selection required; use --mode jev")
	}
	needed := 0
	if route == "jev" {
		needed = requiredCalls(p, cache)
	}
	need(cap >= 1 && cap <= 24 && needed <= cap, "Jev request cap is insufficient")
	key := ""
	if needed > 0 {
		key, _ = r.credential()
		need(key != "", "Jev credential unavailable")
	}
	newDirectory(out)
	recordedRoute := route
	if route == "astra" && host == "claude-code" {
		recordedRoute = "local"
	}
	record := merge(M{"version": 1, "surface": host, "status": "selecting", "plan_dir": planDir, "plan_sha256": digest(readBytes(filepath.Join(planDir, "plan.json"), 40000000)), "max_calls": cap, "planned_calls": needed, "attempted_calls": 0, "policy": policy, "jev_calls": []M{}, "selection_mode": mode, "route": recordedRoute, "require_jev": required}, childFields(host))
	resultPath := filepath.Join(out, "selection.json")
	save(resultPath, record)
	start := time.Now()
	err := guarded(func() {
		selected := r.selectFiles(p, route, policy, cache, key, cap, func() { record["attempted_calls"] = integer(record["attempted_calls"]) + 1; save(resultPath, record) }, func(c M) { record["jev_calls"] = append(maps(record["jev_calls"]), c); save(resultPath, record) })
		if required {
			requireJev(p, record)
		}
		fresh(p)
		need(digest(readBytes(filepath.Join(planDir, "plan.json"), 40000000)) == record["plan_sha256"], "Plan changed during selection")
		files := M{}
		for _, f := range stringsOf(selected["paths"]) {
			files[f] = object(obj(p, "files")[f])["content"]
		}
		context := M{"task": p["task"], "repo": p["repo"], "head": p["head"], "files": files}
		if packet != nil {
			evidenceCheck(evidence)
			context["evidence"] = packet
			record["evidence_selection_dir"] = absolute(evidence)
		}
		save(filepath.Join(out, "context.json"), context)
		record["status"] = "selected"
		for _, k := range []string{"paths", "decisions", "metrics", "unjudged_paths", "fragment_decisions", "reason"} {
			record[k] = selected[k]
		}
		record["context_sha256"] = digest(readBytes(filepath.Join(out, "context.json"), 40000000))
	})
	record["seconds"] = time.Since(start).Seconds()
	if err != nil {
		record["status"] = "failed"
		record["failure"] = failure(err, "context_selection")
	}
	save(resultPath, record)
	if err != nil {
		panic(err)
	}
	report(out, "REPORT.md", "# Context selected\n\n"+fmtJSON(merge(callCounts(record), M{"attempted_calls": record["attempted_calls"], "metrics": record["metrics"]}))+"\n\nSelection is not implementation or verification. Read bounded ranges after check. Bytes are not tokens or savings.\n")
	return record
}
func hostCheck(host, dir string, required bool) M {
	dir = absolute(dir)
	record := hostRecord(dir, host, []string{"selected"})
	planDir := str(record["plan_dir"])
	need(digest(readBytes(filepath.Join(planDir, "plan.json"), 40000000)) == record["plan_sha256"], "Context plan changed")
	need(digest(readBytes(filepath.Join(dir, "context.json"), 40000000)) == record["context_sha256"], "Selected context changed")
	p := hostPlan(planDir, host)
	fresh(p)
	required = required || flag(record["require_jev"])
	result := merge(M{"status": "fresh", "target_writes": 0}, childFields(host))
	if required {
		requireJev(p, record)
		result = merge(result, M{"require_jev": true}, callCounts(record))
	}
	if e := sget(record, "evidence_selection_dir"); e != "" {
		evidenceCheck(e)
	}
	return result
}
func hostRead(host, dir, p string, start, end int, required bool) M {
	hostCheck(host, dir, required)
	if end == 0 {
		end = start + 79
	}
	need(start >= 1 && end >= start && end-start < 200, "Read at most 200 lines")
	record := hostRecord(dir, host, []string{"selected"})
	need(contains(stringsOf(record["paths"]), p), "Path outside selected context")
	context := load(filepath.Join(dir, "context.json"))
	text := str(obj(context, "files")[p])
	lines := nativecore.SplitLines(text)
	need(start <= max(1, len(lines)), "Start line outside file")
	ex := must(nativecore.Excerpt(p, text, start, end-start+1))
	delete(ex, "unpresented_ranges")
	var next any
	if integer(ex["end_line"]) < len(lines) {
		next = integer(ex["end_line"]) + 1
	}
	size := len(str(ex["text"]))
	need(size <= 24000, "Read exceeds 24KB; narrow range")
	return merge(ex, M{"next_start_line": next, "returned_bytes": size, "provider_calls": 0})
}
func hostCompare(host, dir string, required []string) M {
	record := hostRecord(dir, host, []string{"selected", "failed", "selecting"})
	planDir := str(record["plan_dir"])
	need(digest(readBytes(filepath.Join(planDir, "plan.json"), 40000000)) == record["plan_sha256"], "Recorded plan changed")
	p := hostPlan(planDir, host)
	need(len(unique(required)) == len(required), "Duplicate labels")
	missingScope, inScope := []string{}, []string{}
	for _, f := range required {
		need(obj(p, "files")[f] != nil || obj(p, "scoped_out")[f] != nil, "Required label outside plan")
		if obj(p, "scoped_out")[f] != nil {
			missingScope = append(missingScope, f)
		} else {
			inScope = append(inScope, f)
		}
	}
	sort.Strings(missingScope)
	recall := func(missing, total int) any {
		if total == 0 {
			return nil
		}
		return 1 - float64(missing)/float64(total)
	}
	policies := M{}
	for _, policy := range []string{"batch", "per-file"} {
		s := resolveSelection(p, maps(record["jev_calls"]), policy)
		kept := set(stringsOf(s["paths"]))
		missing := []string{}
		inside := 0
		for _, f := range required {
			if kept[f] == nil {
				missing = append(missing, f)
				if contains(inScope, f) {
					inside++
				}
			}
		}
		sort.Strings(missing)
		policies[policy] = merge(obj(s, "metrics"), M{"paths": s["paths"], "unjudged_paths": s["unjudged_paths"], "missing_required_paths": missing, "required_recall": recall(len(missing), len(required)), "within_scope_required_recall": recall(inside, len(inScope))})
	}
	additional := []string{}
	for _, f := range stringsOf(obj(policies, "batch")["paths"]) {
		if !contains(stringsOf(obj(policies, "per-file")["paths"]), f) {
			additional = append(additional, f)
		}
	}
	basis := "unlabeled_no_quality_claim"
	if len(required) > 0 {
		basis = "caller_supplied_required_files"
	}
	return M{"status": "historical_comparison", "source_status": record["status"], "additional_provider_calls": 0, "required_paths": required, "quality_basis": basis, "scope_required_recall": recall(len(missingScope), len(required)), "missing_in_scope": missingScope, "policies": policies, "additional_omitted_paths": additional, "additional_omitted_bytes": integer(obj(policies, "batch")["selected_bytes"]) - integer(obj(policies, "per-file")["selected_bytes"])}
}
func score(d M) float64 {
	p := d["probability"]
	if v, ok := d["max_fragment_probability"]; ok {
		p = v
	}
	if p == nil {
		return -1
	}
	return number(p)
}
func viewBounds(limit, offset, lines int) {
	need(limit >= 1024 && limit <= 24000 && offset >= 0 && lines >= 1 && lines <= 200, "Invalid view bounds")
}
func hostPresent(host, dir string, limit, offset, lines int) M {
	viewBounds(limit, offset, lines)
	hostCheck(host, dir, true)
	record := hostRecord(dir, host, []string{"selected"})
	p := hostPlan(str(record["plan_dir"]), host)
	context := load(filepath.Join(dir, "context.json"))
	paths := stringsOf(record["paths"])
	focus := set(stringsOf(p["focus_paths"]))
	decisions := obj(record, "decisions")
	sort.Slice(paths, func(i, j int) bool {
		a, b := paths[i], paths[j]
		if isInstruction(a) != isInstruction(b) {
			return isInstruction(a)
		}
		if (focus[a] != nil) != (focus[b] != nil) {
			return focus[a] != nil
		}
		x, y := score(obj(decisions, a)), score(obj(decisions, b))
		if x != y {
			return x > y
		}
		return a < b
	})
	items := []M{}
	total := 0
	cat := units(p)
	for _, f := range paths {
		start := 1
		best := -2.
		if !isInstruction(f) && focus[f] == nil {
			for _, k := range cat.Keys {
				fragment := obj(obj(record, "fragment_decisions"), k)
				if fragment["path"] == f && score(fragment) > best {
					best = score(fragment)
					if fragment["start_line"] != nil {
						start = integer(fragment["start_line"])
					}
				}
			}
		}
		text := str(obj(context, "files")[f])
		total += len(text)
		item := must(nativecore.Excerpt(f, text, start, lines))
		item["reasons"] = array(obj(decisions, f)["reasons"])
		items = append(items, item)
	}
	result := must(nativecore.Page(M{"status": "presentation", "retained_files": len(paths), "retained_source_bytes": total, "scoped_out_files": len(obj(p, "scoped_out")), "coverage": "excerpts_only_full_sources_remain_in_context", "reading_leads": "Use read for unpresented_ranges; next_offset visits further retained files."}, items, offset, limit))
	hostCheck(host, dir, true)
	return result
}
func hostDiscover(host, dir, directory string, hasDirectory bool, limit, offset, lines int) M {
	viewBounds(limit, offset, lines)
	p := hostPlan(dir, host)
	fresh(p)
	omitted := obj(p, "scoped_out")
	branches := M{}
	for f := range omitted {
		d := path.Dir(f)
		branches[d] = append(stringsOf(branches[d]), f)
	}
	base := M{"status": "discovery", "judgment": "unjudged", "scoped_out_files": len(omitted), "next_step": "Review branches, then make a new plan with existing focus plus discovered --focus-file; select/check before edits."}
	items := []M{}
	if !hasDirectory {
		for _, d := range keys(branches) {
			size := 0
			for _, f := range stringsOf(branches[d]) {
				size += integer(object(omitted[f])["bytes"])
			}
			items = append(items, M{"directory": d, "files": len(array(branches[d])), "source_bytes": size})
		}
	} else {
		need(branches[directory] != nil, "Choose exact directory from index")
		base["directory"] = directory
		for _, f := range unique(stringsOf(branches[directory])) {
			text := readText(safePath(str(p["repo"]), f), 100000)
			need(digest([]byte(text)) == object(omitted[f])["sha256"] && !isSecret(text), "Discovery source changed")
			item := must(nativecore.Excerpt(f, text, 1, lines))
			item["judgment"] = "unjudged"
			items = append(items, item)
		}
	}
	result := must(nativecore.Page(base, items, offset, limit))
	fresh(p)
	return result
}
