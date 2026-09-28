// Package nativecore contains offline compatibility primitives. It performs no
// provider calls, repository reads, or decisions about permission or relevance.
package nativecore

type Import struct {
	Module string   `json:"module"`
	Level  int      `json:"level"`
	Names  []string `json:"names"`
}
