package harness

import (
	"encoding/json"
	"math"
	"math/big"
	"regexp"
	"strings"
)

func nonnegativeInt(v any) bool { ok := false; _ = guarded(func() { ok = integer(v) >= 0 }); return ok }
func cacheCounts(usage M) (any, any, any) {
	if !nonnegativeInt(usage["input_tokens"]) {
		return nil, nil, nil
	}
	total := integer(usage["input_tokens"])
	details, _ := usage["input_tokens_details"].(map[string]any)
	count := func(nested string, aliases ...string) any {
		values := []any{}
		if v, ok := details[nested]; ok {
			values = append(values, v)
		}
		for _, k := range aliases {
			if v, ok := usage[k]; ok {
				values = append(values, v)
			}
		}
		if len(values) == 0 {
			return nil
		}
		for _, v := range values {
			if !nonnegativeInt(v) || integer(v) > total {
				return nil
			}
		}
		n := integer(values[0])
		for _, v := range values {
			if integer(v) != n {
				return nil
			}
		}
		return n
	}
	read := count("cached_tokens", "cached_input_tokens")
	write := count("cache_write_tokens", "cache_write_tokens", "cache_write_input_tokens")
	if read != nil && write != nil {
		if integer(read)+integer(write) > total {
			return nil, nil, nil
		}
		return read, write, total - integer(read) - integer(write)
	}
	return read, write, nil
}
func knownUsage(call M) bool {
	u, ok := call["usage"].(map[string]any)
	return ok && nonnegativeInt(u["input_tokens"]) && nonnegativeInt(u["output_tokens"])
}
func providerSummary(calls []M, attempted any, cacheRequired bool) M {
	live, known, reusedCount := 0, 0, 0
	input, output, read, write, ordinary, cacheMissing := 0, 0, 0, 0, 0, 0
	for _, c := range calls {
		if flag(c["reused"]) {
			reusedCount++
			continue
		}
		live++
		if !knownUsage(c) {
			continue
		}
		known++
		u := obj(c, "usage")
		input += integer(u["input_tokens"])
		output += integer(u["output_tokens"])
		var r, w, o any = 0, 0, u["input_tokens"]
		if cacheRequired {
			r, w, o = cacheCounts(u)
		}
		if r != nil {
			read += integer(r)
		}
		if w != nil {
			write += integer(w)
		}
		if o != nil {
			ordinary += integer(o)
		} else {
			cacheMissing++
		}
	}
	var unknown, cacheUnknown, ordinaryTotal, completeCache any
	complete := false
	if attempted != nil {
		unknown = max(integer(attempted), live) - known
		cacheUnknown = integer(unknown) + cacheMissing
		complete = integer(unknown) == 0
		if integer(cacheUnknown) == 0 {
			ordinaryTotal = ordinary
		}
	}
	if cacheRequired {
		completeCache = cacheUnknown != nil && integer(cacheUnknown) == 0
	}
	return M{"known_cached_input_tokens": read, "known_cache_write_tokens": write, "known_ordinary_input_tokens": ordinary, "ordinary_input_tokens": ordinaryTotal, "unknown_cache_usage_calls": cacheUnknown, "complete_cache_usage": completeCache, "cache_accounting_applicable": cacheRequired, "attempted_calls": attempted, "recorded_live_calls": live, "reused_calls": reusedCount, "unknown_usage_calls": unknown, "known_input_tokens": input, "known_output_tokens": output, "complete_usage": complete}
}
func normalizeRecord(record M) M {
	listField := func(k string) any {
		v, ok := record[k]
		if !ok {
			return []M{}
		}
		return v
	}
	kind, surface := sget(record, "kind"), sget(record, "surface")
	family := "unknown"
	var a, j, ac, jc any = []M{}, []M{}, nil, nil
	switch {
	case kind == "tool-output" && nonnegativeInt(record["version"]) && integer(record["version"]) == 1:
		family, a, j, ac, jc = "tool-output", []M{}, listField("calls"), 0, record["attempted_calls"]
	case kind == "evidence_selection":
		family, a, j, ac, jc = "evidence", []M{}, listField("jev_calls"), 0, record["attempted_calls"]
	case kind == "" && (surface == "desktop" || surface == "claude-code"):
		family, a, j, ac, jc = surface, []M{}, listField("jev_calls"), nil, record["attempted_calls"]
	case kind == "" && (surface == "" || surface == "cli") && record["astra_calls"] != nil:
		family, a, j, ac, jc = "cli", listField("astra_calls"), record["completed_jev_calls"], record["attempted_astra_calls"], record["attempted_jev_calls"]
		if j == nil {
			j = listField("jev_calls")
		}
	}
	clean := func(calls, count any) ([]M, any) {
		if calls == nil {
			return []M{}, nil
		}
		result := []M{}
		err := guarded(func() {
			for _, c := range array(calls) {
				m, ok := c.(map[string]any)
				if !ok {
					m = M{}
				}
				result = append(result, m)
			}
		})
		if err != nil {
			return []M{}, nil
		}
		if !nonnegativeInt(count) {
			count = nil
		}
		return result, count
	}
	aa, ac := clean(a, ac)
	jj, jc := clean(j, jc)
	var seconds any
	if family != "unknown" {
		seconds = record["seconds"]
	}
	status := sget(record, "status")
	if status == "" {
		status = "unknown"
	}
	return M{"kind": family, "astra": aa, "jev": jj, "acount": ac, "jcount": jc, "status": status, "seconds": seconds}
}

var decimalPattern = regexp.MustCompile(`^[+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$`)

func rate(v any) *big.Rat {
	var s string
	switch x := v.(type) {
	case string:
		s = x
	case json.Number:
		s = string(x)
	case int:
		s = string(wire(x))
	case float64:
		s = string(wire(x))
	default:
		fail("Invalid price")
	}
	need(len(s) <= 1000 && decimalPattern.MatchString(s), "Prices must be finite and nonnegative")
	n, ok := new(big.Rat).SetString(s)
	need(ok && n.Sign() >= 0 && n.Num().BitLen() <= 10000 && n.Denom().BitLen() <= 10000, "Invalid price")
	return n
}
func validatePrices(prices M) {
	for _, v := range prices {
		for k, x := range object(v) {
			need(contains([]string{"input", "output", "cache_read", "cache_write"}, k), "Unknown price component")
			rate(x)
		}
	}
}
func decimalString(r *big.Rat) string {
	den := new(big.Int).Set(r.Denom())
	scale := 0
	two, five := big.NewInt(2), big.NewInt(5)
	a, b := 0, 0
	for new(big.Int).Mod(den, two).Sign() == 0 {
		den.Div(den, two)
		a++
	}
	for new(big.Int).Mod(den, five).Sign() == 0 {
		den.Div(den, five)
		b++
	}
	need(den.Cmp(big.NewInt(1)) == 0, "Non-decimal cost")
	scale = max(a, b)
	s := r.FloatString(scale)
	if strings.Contains(s, ".") {
		s = strings.TrimRight(strings.TrimRight(s, "0"), ".")
	}
	return s
}
func estimateCost(calls []M, attempted any, prices M, cacheRequired bool) M {
	subtotal := new(big.Rat)
	live, priced := 0, 0
	for _, c := range calls {
		if flag(c["reused"]) {
			continue
		}
		live++
		if !knownUsage(c) {
			continue
		}
		rates := obj(prices, sget(c, "model"))
		if rates["input"] == nil || rates["output"] == nil {
			continue
		}
		usage := obj(c, "usage")
		var ordinary, cached, written any = usage["input_tokens"], 0, 0
		if cacheRequired {
			cached, written, ordinary = cacheCounts(usage)
			if ordinary == nil || rates["cache_read"] == nil || rates["cache_write"] == nil {
				continue
			}
		}
		amount := new(big.Rat)
		add := func(n any, p any) {
			amount.Add(amount, new(big.Rat).Mul(new(big.Rat).SetInt64(int64(integer(n))), rate(p)))
		}
		add(ordinary, rates["input"])
		add(usage["output_tokens"], rates["output"])
		if cacheRequired {
			add(cached, rates["cache_read"])
			add(written, rates["cache_write"])
		}
		amount.Quo(amount, new(big.Rat).SetInt64(1000000))
		subtotal.Add(subtotal, amount)
		priced++
	}
	var unknown, estimated any
	complete := false
	if attempted != nil {
		unknown = max(integer(attempted), live) - priced
		complete = integer(unknown) == 0
		if complete {
			estimated = decimalString(subtotal)
		}
	}
	return M{"estimated_usd": estimated, "known_subtotal_usd": decimalString(subtotal), "unpriced_or_unknown_calls": unknown, "complete": complete, "basis": "supplied_model_rates_not_invoice_or_subscription_usage"}
}
func summarize(paths []string, prices M) M {
	if prices != nil {
		validatePrices(prices)
	}
	seen := M{}
	records := []M{}
	for _, p := range paths {
		p = absolute(p)
		if seen[p] != nil {
			continue
		}
		seen[p] = true
		records = append(records, normalizeRecord(load(p)))
	}
	astra, jev := []M{}, []M{}
	var acount, jcount any = 0, 0
	seconds := 0.
	knownSeconds, hasCLI := true, false
	statuses, kinds := []string{}, []string{}
	for _, r := range records {
		astra = append(astra, maps(r["astra"])...)
		jev = append(jev, maps(r["jev"])...)
		if acount == nil || r["acount"] == nil {
			acount = nil
		} else {
			acount = integer(acount) + integer(r["acount"])
		}
		if jcount == nil || r["jcount"] == nil {
			jcount = nil
		} else {
			jcount = integer(jcount) + integer(r["jcount"])
		}
		err := guarded(func() {
			n := number(r["seconds"])
			need(!math.IsNaN(n) && !math.IsInf(n, 0) && n >= 0, "Invalid duration")
			seconds += n
		})
		knownSeconds = knownSeconds && err == nil
		hasCLI = hasCLI || r["kind"] == "cli"
		statuses = append(statuses, str(r["status"]))
		kinds = append(kinds, str(r["kind"]))
	}
	if !hasCLI {
		acount = nil
	}
	var duration any
	if knownSeconds {
		duration = seconds
	}
	result := M{"record_count": len(records), "statuses": statuses, "record_kinds": kinds, "astra": providerSummary(astra, acount, true), "jev": providerSummary(jev, jcount, false), "summed_run_seconds": duration, "quality": "not_established_by_usage_or_exit_status", "dollar_cost": nil}
	if prices != nil {
		a, j := estimateCost(astra, acount, prices, true), estimateCost(jev, jcount, prices, false)
		result["cost_estimates"] = M{"astra": a, "jev": j}
		if flag(a["complete"]) && flag(j["complete"]) {
			result["dollar_cost"] = decimalString(new(big.Rat).Add(rate(a["estimated_usd"]), rate(j["estimated_usd"])))
		}
	}
	return result
}
func measureCompare(baseline, candidate []string, prices M) M {
	left, right := summarize(baseline, prices), summarize(candidate, prices)
	complete := flag(obj(left, "astra")["complete_usage"]) && flag(obj(right, "astra")["complete_usage"])
	before, after := integer(obj(left, "astra")["known_input_tokens"]), integer(obj(right, "astra")["known_input_tokens"])
	var reduction any
	if complete && before > 0 {
		reduction = float64(before-after) / float64(before)
	}
	return M{"baseline": left, "candidate": right, "astra_input_reduction": reduction, "comparable_task_and_acceptance": "must_be_checked_independently", "different_provider_tokens_are_not_added": true}
}
