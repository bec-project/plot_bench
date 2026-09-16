package main

import (
	"fyne.io/fyne/v2"
	"testing"
)

func TestDataAreaContract(t *testing.T) {
	for _, c := range []struct {
		n             int
		width, height float32
	}{{1, 932, 340}, {2, 398, 340}, {4, 398, 92}, {6, 220, 92}} {
		got := dataSlot(fyne.NewSize(1100, 820), c.n)
		if got != fyne.NewSize(c.width, c.height) {
			t.Fatalf("count %d: %v", c.n, got)
		}
	}
}
