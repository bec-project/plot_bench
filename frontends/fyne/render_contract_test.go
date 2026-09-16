package main

import (
	"fyne.io/fyne/v2"
	"testing"
)

func TestDataAreaContract(t *testing.T) {
	for _, c := range []struct {
		n             int
		width, height float32
	}{{1, 952, 480}, {2, 418, 480}, {4, 418, 172}, {6, 240, 172}} {
		got := dataSlot(fyne.NewSize(1100, 820), c.n, false)
		if got != fyne.NewSize(c.width, c.height) {
			t.Fatalf("count %d: %v", c.n, got)
		}
	}
}

func TestCompactImageSlots(t *testing.T) {
	for _, c := range []struct {
		n             int
		width, height float32
	}{{1, 956, 500}, {2, 502, 584}, {4, 502, 276}, {6, 324, 276}} {
		if got := dataSlot(fyne.NewSize(1100, 820), c.n, true); got != fyne.NewSize(c.width, c.height) {
			t.Fatalf("count %d: %v", c.n, got)
		}
	}
}
