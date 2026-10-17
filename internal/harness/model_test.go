package harness

import "testing"

func TestNativeFixedModelAndVersionedCache(t *testing.T) {
	repo, root := fixtureRepo(t)
	plan := hostMakePlan("desktop", repo, "Implement src/app.py value behavior", root+"/plan", []string{}, []string{}, 4)
	cat := units(plan)
	payloads := map[string]M{
		"context":  jevPayload(plan, batches(plan)[0], cat),
		"evidence": evidencePayload("Check behavior", []M{{"id": "e0", "text": "Preserve behavior."}}),
		"output":   outputPayload("Check tests", "", []M{{"id": "c0", "text": "Progress only."}}),
	}
	for name, payload := range payloads {
		t.Run(name, func(t *testing.T) {
			if payload["model"] != "jev-1.14.0" {
				t.Fatalf("new requests must pin Jev 1.14.0: %v", payload["model"])
			}
			answers := M{}
			for k := range obj(payload, "questions") {
				answers[k] = M{"type": "noul", "noul": .9}
			}
			current := M{"model": "jev-1.14.0", "answers": answers}
			legacyPayload := clone(payload)
			legacyPayload["model"] = "jev-1.13.0"
			legacy := M{"model": "jev-1.13.0", "answers": answers}
			cache := t.TempDir()
			writeCache(legacyPayload, legacy, cache)
			if readCache(payload, cache) != nil {
				t.Fatal("a 1.13 cache entry must not satisfy a 1.14 request")
			}
			for _, model := range []string{"jev-1.13.0", "jev-latest", "jev-preview"} {
				reject(t, func() { validateResponse(payload, M{"model": model, "answers": answers}) })
			}
			writeCache(payload, current, cache)
			value := readCache(payload, cache)
			if hash(value) != hash(current) || reused(payload, value)["model"] != "jev-1.14.0" {
				t.Fatal("matching 1.14 cache result was not reused truthfully")
			}
			if hash(readCache(legacyPayload, cache)) != hash(legacy) {
				t.Fatal("the upgrade must preserve the historical 1.13 cache entry")
			}
		})
	}
}
