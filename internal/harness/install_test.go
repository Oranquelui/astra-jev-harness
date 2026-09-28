package harness

import (
	"os"
	"path/filepath"
	"testing"
)

func TestNativeInstallPreservesOtherSkillsAndAuth(t *testing.T) {
	root := t.TempDir()
	for _, p := range []string{"bin", "Codex Desktop/skills/astra-jev-coding", "Claude Code/skills/claude-jev-coding"} {
		need(os.MkdirAll(filepath.Join(root, p), 0700) == nil, "fixture mkdir")
	}
	writeBytes(filepath.Join(root, "bin/astra-jev"), []byte("fixture binary"), 0700)
	for _, p := range []string{"Codex Desktop/skills/astra-jev-coding/SKILL.md", "Claude Code/skills/claude-jev-coding/SKILL.md"} {
		writeBytes(filepath.Join(root, p), []byte("fixture skill"), 0600)
	}
	r := New(root)
	skills := filepath.Join(t.TempDir(), "skills")
	if r.install(skills, true, "codex-desktop")["status"] != "would-install" || exists(skills) {
		t.Fatal("check wrote destination")
	}
	if r.install(skills, false, "codex-desktop")["status"] != "installed" || r.install(skills, false, "codex-desktop")["status"] != "already-installed" {
		t.Fatal("install not idempotent")
	}
	link := filepath.Join(skills, "astra-jev-coding")
	need(os.Remove(link) == nil, "fixture unlink")
	need(os.Symlink(filepath.Join(root, "missing"), link) == nil, "fixture link")
	reject(t, func() { r.install(skills, false, "codex-desktop") })
	if must(os.Readlink(link)) != filepath.Join(root, "missing") {
		t.Fatal("overwrote foreign broken link")
	}
	need(os.Remove(link) == nil, "fixture unlink")
	legacy := filepath.Join(root, "desktop/skills/astra-jev-coding")
	need(os.Symlink(legacy, link) == nil, "fixture link")
	if r.install(skills, true, "codex-desktop")["status"] != "would-update" || must(os.Readlink(link)) != legacy {
		t.Fatal("legacy dry run changed link")
	}
	if r.install(skills, false, "codex-desktop")["status"] != "updated" {
		t.Fatal("legacy migration")
	}
	authRoot := t.TempDir()
	writeBytes(filepath.Join(authRoot, "auth.json"), []byte("fixture auth"), 0600)
	t.Setenv("CODEX_HOME", authRoot)
	r.install("", false, "codex-desktop")
	if readText(filepath.Join(authRoot, "auth.json"), 1000) != "fixture auth" {
		t.Fatal("auth changed")
	}
	if r.install(skills, false, "claude-code")["status"] != "installed" {
		t.Fatal("Claude installation")
	}
}
func TestNativeCredentialGuardUnicodeWhitespace(t *testing.T) {
	for _, s := range []string{"password\u00a0=\u3000'abcdefghijklmnopqrstuvwxyz'", "api_key\t:\t'abcdefghijklmnopqrstuvwxyz'", "ſecret = 'abcdefghijklmnopqrstuvwxyz'", "APİ_KEY = 'abcdefghijklmnopqrstuvwxyz'"} {
		if !isSecret(s) {
			t.Fatalf("Unicode secret guard missed %q", s)
		}
	}
}
