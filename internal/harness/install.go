package harness

import (
	"os"
	"path/filepath"
	"strings"
)

func defaultSkills(target string) string {
	home := must(os.UserHomeDir())
	if target == "claude-code" {
		return filepath.Join(home, ".claude", "skills")
	}
	root := os.Getenv("CODEX_HOME")
	if root == "" {
		root = filepath.Join(home, ".codex")
	}
	return filepath.Join(root, "skills")
}
func (r *Runtime) install(skills string, check bool, target string) M {
	need(target == "codex-desktop" || target == "claude-code", "Unknown install target")
	relative, name, legacy := "Codex Desktop/skills/astra-jev-coding", "astra-jev-coding", "desktop/skills/astra-jev-coding"
	if target == "claude-code" {
		relative, name, legacy = "Claude Code/skills/claude-jev-coding", "claude-jev-coding", ""
	}
	root := absolute(r.Root)
	source := filepath.Join(root, relative)
	need(exists(filepath.Join(source, "SKILL.md")), "Keep complete checkout; Skill source missing")
	need(exists(filepath.Join(root, "bin", "astra-jev")), "Build the native binary before installing")
	if skills == "" {
		skills = defaultSkills(target)
	}
	if skills == "~" || strings.HasPrefix(skills, "~/") {
		skills = filepath.Join(must(os.UserHomeDir()), strings.TrimPrefix(strings.TrimPrefix(skills, "~"), "/"))
	}
	link := filepath.Join(absolute(skills), name)
	status := "installed"
	info, err := os.Lstat(link)
	if err == nil && info.Mode()&os.ModeSymlink != 0 {
		resolved, resolveErr := filepath.EvalSymlinks(link)
		if resolveErr == nil && resolved == source {
			return M{"status": "already-installed", "path": link}
		}
		if legacy != "" {
			raw := must(os.Readlink(link))
			if !filepath.IsAbs(raw) {
				raw = filepath.Join(filepath.Dir(link), raw)
			}
			old := filepath.Join(root, legacy)
			if absolute(raw) == old && !exists(old) {
				if check {
					return M{"status": "would-update", "path": link}
				}
				dir := must(os.MkdirTemp(filepath.Dir(link), ".astra-jev-install-"))
				defer os.RemoveAll(dir)
				replacement := filepath.Join(dir, name)
				need(os.Symlink(source, replacement) == nil && os.Rename(replacement, link) == nil, "Cannot migrate legacy link")
				return M{"status": "updated", "path": link}
			}
		}
	}
	need(os.IsNotExist(err), "A different Skill exists; leave it intact and choose another directory")
	if check {
		status = "would-install"
	} else {
		need(os.MkdirAll(filepath.Dir(link), 0755) == nil && os.Symlink(source, link) == nil, "Cannot install Skill link")
	}
	return M{"status": status, "path": link}
}
