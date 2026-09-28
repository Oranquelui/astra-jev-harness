package harness

import "math"

func selectionRoute(plan M, mode string) string {
	need(contains([]string{"auto", "astra", "jev", "local"}, mode), "Unknown selection mode")
	size := 0
	for _, v := range obj(plan, "files") {
		size += len(str(object(v)["content"]))
	}
	if mode == "astra" || mode == "local" || mode == "auto" && size < 12000 {
		return "astra"
	}
	return "jev"
}
func resolveSelection(plan M, calls []M, policy string) M {
	need(policy == "batch" || policy == "per-file", "Unknown policy")
	files := contents(plan)
	cat := units(plan)
	if sget(plan, "context_format") != contextFormat {
		cat = catalog{keys(files), M{}}
		for p := range files {
			cat.Units[p] = M{"path": p}
		}
	}
	probabilities, reasons, chosen := M{}, M{}, M{}
	for p := range files {
		reasons[p] = []string{}
	}
	reason := func(p, r string) { reasons[p] = append(stringsOf(reasons[p]), r) }
	for _, call := range calls {
		scores := obj(call, "probabilities")
		need(len(scores) > 0, "Missing recorded probabilities")
		uncertain := false
		for k, v := range scores {
			n := number(v)
			need(cat.Units[k] != nil && probabilities[k] == nil && !math.IsNaN(n) && !math.IsInf(n, 0) && n >= 0 && n <= 1, "Invalid recorded probability")
			uncertain = uncertain || n > .2 && n < .8
		}
		for k, v := range scores {
			probabilities[k] = v
			p := str(object(cat.Units[k])["path"])
			n := number(v)
			if n > .2 {
				chosen[p] = true
				if n >= .8 {
					reason(p, "relevant")
				} else {
					reason(p, "uncertain")
				}
			} else if policy == "batch" && uncertain {
				chosen[p] = true
				reason(p, "batch_uncertainty")
			}
		}
	}
	unjudgedUnits, unjudged := M{}, M{}
	for _, k := range cat.Keys {
		if probabilities[k] == nil {
			unjudgedUnits[k] = true
			unjudged[str(object(cat.Units[k])["path"])] = true
		}
	}
	for p := range unjudged {
		chosen[p] = true
		reason(p, "unjudged")
	}
	for _, p := range stringsOf(plan["focus_paths"]) {
		chosen[p] = true
		reason(p, "explicit_focus")
	}
	if len(chosen) == 0 {
		for p := range files {
			chosen[p] = true
			reason(p, "global_no_match")
		}
	}
	selected := dependencies(files, keys(chosen))
	kept := set(selected)
	for _, p := range selected {
		if chosen[p] == nil {
			reason(p, "guidance_or_dependency")
		}
	}
	decisions, fragments := M{}, M{}
	for _, k := range cat.Keys {
		u := clone(object(cat.Units[k]))
		delete(u, "text")
		u["probability"] = probabilities[k]
		fragments[k] = u
	}
	before, after, unjudgedBytes := 0, 0, 0
	for p, text := range files {
		size := len(str(text))
		before += size
		if kept[p] != nil {
			after += size
		}
		if unjudged[p] != nil {
			unjudgedBytes += size
		}
		ks := []string{}
		var maximum any
		for _, k := range cat.Keys {
			if object(cat.Units[k])["path"] == p {
				ks = append(ks, k)
				if v := probabilities[k]; v != nil && (maximum == nil || number(v) > number(maximum)) {
					maximum = v
				}
			}
		}
		value := maximum
		if unjudged[p] != nil {
			value = nil
		}
		judgment := "unjudged"
		if value != nil {
			n := number(value)
			judgment = "uncertain"
			if n >= .8 {
				judgment = "relevant"
			} else if n <= .2 {
				judgment = "irrelevant"
			}
		}
		rs := unique(stringsOf(reasons[p]))
		if len(rs) == 0 {
			rs = []string{"confidently_irrelevant"}
		}
		d := M{"probability": value, "judgment": judgment, "kept": kept[p] != nil, "reasons": rs}
		if len(ks) > 1 {
			d["probability"] = nil
			d["fragment_ids"] = ks
			d["max_fragment_probability"] = maximum
			d["fully_judged"] = unjudged[p] == nil
		}
		decisions[p] = d
	}
	scoped := obj(plan, "scoped_out")
	var ratio any
	if before > 0 {
		ratio = float64(after) / float64(before)
	}
	return M{"paths": selected, "policy": policy, "decisions": decisions, "unjudged_paths": keys(unjudged), "fragment_decisions": fragments, "metrics": M{"candidate_files": len(files), "selected_files": len(selected), "judged_files": len(files) - len(unjudged), "unjudged_files": len(unjudged), "candidate_fragments": len(cat.Keys), "judged_fragments": len(probabilities), "unjudged_fragments": len(unjudgedUnits), "unjudged_bytes": unjudgedBytes, "excluded_files": len(obj(plan, "excluded")), "candidate_bytes": before, "selected_bytes": after, "omitted_bytes": before - after, "retained_byte_ratio": ratio, "prefiltered_files": len(scoped), "prefiltered_bytes": sumBytes(scoped), "eligible_files": len(files) + len(scoped), "eligible_bytes": before + sumBytes(scoped)}}
}
func requireJev(plan, record M) {
	need(record["route"] == "jev" && len(array(record["jev_calls"])) > 0, "Jev selection required; local handoff is not Jev usage")
	replay := resolveSelection(plan, maps(record["jev_calls"]), sget(record, "policy"))
	need(integer(obj(replay, "metrics")["judged_fragments"]) > 0, "Jev judgments required")
}
func callCounts(record M) M {
	live, cached := 0, 0
	for _, c := range maps(record["jev_calls"]) {
		if flag(c["reused"]) {
			cached++
		} else {
			live++
		}
	}
	return M{"jev_completed_calls": live, "jev_reused_calls": cached}
}
