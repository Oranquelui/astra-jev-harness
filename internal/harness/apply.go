package harness

import (
	"bytes"
	"os"
	"path/filepath"
)

type installFileFunc func(string, string, bool) error

func installFile(temp, target string, isNew bool) error {
	if isNew {
		return os.Link(temp, target)
	}
	return os.Rename(temp, target)
}
func applyRun(dir string) M { return applyWith(dir, installFile) }
func applyWith(dir string, install installFileFunc) M {
	dir = absolute(dir)
	result := load(filepath.Join(dir, "result.json"))
	need(result["status"] == "verified" && integer(result["verification_exit_code"]) == 0 && len(obj(result, "edits")) > 0 && len(obj(result, "candidate_hashes")) > 0, "Only verified nonempty edits can be applied")
	if e := sget(result, "evidence_selection_dir"); e != "" {
		evidenceCheck(e)
	}
	planDir := str(result["plan"])
	need(digest(readBytes(filepath.Join(planDir, "plan.json"), 40000000)) == result["plan_sha256"], "Plan changed since verification")
	p := cliPlan(planDir)
	repo := absolute(str(p["repo"]))
	checkDestinations(p)
	fresh(p)
	candidate := filepath.Join(dir, "candidate")
	need(hash(candidateHashes(candidate, candidatePaths(p, result))) == hash(result["candidate_hashes"]), "Candidate changed since verification")
	originals, replacements := map[string][]byte{}, map[string][]byte{}
	allowed := set(editable(p, keys(obj(p, "files"))))
	for f, checksum := range obj(result, "edits") {
		need(allowed[f] != nil, "Edit outside scope")
		data := readBytes(safePath(candidate, f), 100000)
		need(digest(data) == checksum, "Candidate changed")
		if obj(p, "files")[f] != nil {
			originals[f] = readBytes(safePath(repo, f), 100000)
		} else {
			originals[f] = nil
		}
		replacements[f] = data
	}
	changed, createdDirs := []string{}, []string{}
	err := guarded(func() {
		for _, f := range keys(obj(result, "edits")) {
			data := replacements[f]
			target := safePath(repo, f)
			if originals[f] != nil {
				need(bytes.Equal(readBytes(target, 100000), originals[f]), "Source changed during apply")
			}
			missing := []string{}
			for parent := filepath.Dir(target); !exists(parent); parent = filepath.Dir(parent) {
				missing = append(missing, parent)
			}
			for i := len(missing) - 1; i >= 0; i-- {
				need(os.Mkdir(missing[i], 0755) == nil, "Cannot create source parent")
				createdDirs = append(createdDirs, missing[i])
			}
			func() {
				temp := must(os.CreateTemp(filepath.Dir(target), ".astra-jev-*"))
				name := temp.Name()
				defer os.Remove(name)
				defer temp.Close()
				_, writeErr := temp.Write(data)
				need(writeErr == nil, "Cannot write replacement")
				mode := 0644
				if obj(p, "files")[f] != nil {
					mode = integer(object(obj(p, "files")[f])["mode"])
				}
				need(temp.Chmod(os.FileMode(mode)) == nil && temp.Close() == nil, "Cannot prepare replacement")
				need(install(name, target, originals[f] == nil) == nil, "Cannot install replacement")
				changed = append(changed, f)
			}()
		}
	})
	if err != nil {
		recovered, incomplete := []string{}, []string{}
		for i := len(changed) - 1; i >= 0; i-- {
			f := changed[i]
			err := guarded(func() {
				target := safePath(repo, f)
				need(bytes.Equal(readBytes(target, 100000), replacements[f]), "Concurrent source change; cannot rollback")
				if originals[f] == nil {
					need(os.Remove(target) == nil, "Cannot remove created file")
				} else {
					writeBytes(target, originals[f], 0600)
				}
			})
			if err == nil {
				recovered = append(recovered, f)
			} else {
				incomplete = append(incomplete, f)
			}
		}
		for i := len(createdDirs) - 1; i >= 0; i-- {
			_ = os.Remove(createdDirs[i])
		}
		result["status"] = "apply_failed"
		result["applied_before_failure"] = changed
		result["rolled_back"] = recovered
		result["recovery_incomplete"] = incomplete
		save(filepath.Join(dir, "result.json"), result)
		fail("Apply failed; rollback attempted. Inspect result.json for incomplete recovery")
	}
	result["status"] = "applied"
	save(filepath.Join(dir, "result.json"), result)
	report(dir, "REPORT.md", "# Coding run\n\nStatus: applied\n\n"+sget(result, "summary")+"\n\nExplicit apply completed. No commit or push.\n")
	return result
}
