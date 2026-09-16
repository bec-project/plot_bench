//go:build !ci && !wasm && !mobile && !android && !ios

package gl

import (
	"bytes"
	"image"
	"image/color"
	"testing"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/canvas"
	"fyne.io/fyne/v2/internal/cache"
)

type uploadSpy struct {
	context
	creates, deletes, allocations, updates int
	width, height                          int
	pixels                                 []byte
	params                                 []int32
}

func (s *uploadSpy) GetError() uint32                   { return 0 }
func (s *uploadSpy) CreateTexture() Texture             { s.creates++; return Texture(s.creates) }
func (s *uploadSpy) DeleteTexture(Texture)              { s.deletes++ }
func (s *uploadSpy) ActiveTexture(uint32)               {}
func (s *uploadSpy) BindTexture(uint32, Texture)        {}
func (s *uploadSpy) TexParameteri(_, _ uint32, v int32) { s.params = append(s.params, v) }
func (s *uploadSpy) TexImage2D(_ uint32, _ int, w, h int, _, _ uint32, b []byte) {
	s.allocations++
	s.width, s.height = w, h
	s.pixels = append([]byte(nil), b...)
}
func (s *uploadSpy) TexSubImage2D(_ uint32, _, _, _, w, h int, _, _ uint32, b []byte) {
	s.updates++
	s.width, s.height = w, h
	s.pixels = append([]byte(nil), b...)
}

func TestImageTextureReuseLifecycle(t *testing.T) {
	spy := &uploadSpy{}
	p := &painter{ctx: spy, pixScale: 1}
	pixels := image.NewRGBA(image.Rect(0, 0, 3, 2))
	img := canvas.NewImageFromImage(pixels)
	img.Resize(fyne.NewSize(3, 2))
	img.ScaleMode = canvas.ImageScalePixels
	first, err := p.getTexture(img, p.newGlImageTexture)
	if err != nil {
		t.Fatal(err)
	}
	if spy.creates != 1 || spy.allocations != 1 || spy.updates != 0 {
		t.Fatal("initial allocation missing")
	}
	replacement := image.NewRGBA(pixels.Bounds())
	replacement.SetRGBA(1, 1, color.RGBA{33, 44, 55, 255})
	img.Image = replacement
	p.Refresh(img)
	p.Refresh(img)
	if spy.deletes != 0 || spy.updates != 0 {
		t.Fatal("refresh touched GL storage")
	}
	second, err := p.getTexture(img, p.newGlImageTexture)
	if err != nil || second != first || spy.updates != 1 || spy.allocations != 1 || !bytes.Equal(spy.pixels, replacement.Pix) {
		t.Fatal("same-size refresh failed", err)
	}
	p.getTexture(img, p.newGlImageTexture)
	if spy.updates != 1 {
		t.Fatal("clean texture reuploaded")
	}
	img.Image = image.NewRGBA(image.Rect(0, 0, 5, 4))
	img.ScaleMode = canvas.ImageScaleFastest
	p.Refresh(img)
	p.getTexture(img, p.newGlImageTexture)
	if spy.allocations != 2 || spy.creates != 1 || spy.width != 5 || spy.height != 4 {
		t.Fatal("resize did not redefine existing storage")
	}
	if spy.params[len(spy.params)-1] != textureFilterToGL[canvas.ImageScaleFastest] {
		t.Fatal("filter not updated")
	}
	p.Free(img)
	if spy.deletes != 1 || len(p.imageTextures) != 0 {
		t.Fatal("texture cleanup failed")
	}
	if _, ok := cache.GetTexture(img); ok {
		t.Fatal("cache entry survived")
	}
	p.Free(img)
	if spy.deletes != 1 {
		t.Fatal("double delete")
	}
	p.getTexture(img, p.newGlImageTexture)
	if spy.creates != 2 {
		t.Fatal("freed texture reused")
	}
	p.Free(img)
}

func TestImageTexturePacksSubimageAndConvertsFormats(t *testing.T) {
	spy := &uploadSpy{}
	p := &painter{ctx: spy}
	img := &canvas.Image{}
	parent := image.NewRGBA(image.Rect(0, 0, 5, 5))
	parent.SetRGBA(2, 2, color.RGBA{12, 34, 56, 255})
	sub := parent.SubImage(image.Rect(2, 2, 4, 4)).(*image.RGBA)
	p.updateImageTexture(img, sub)
	if len(spy.pixels) != 16 || !bytes.Equal(spy.pixels[:4], []byte{12, 34, 56, 255}) {
		t.Fatal("subimage was not packed")
	}
	gray := image.NewGray(image.Rect(0, 0, 2, 2))
	gray.SetGray(0, 0, color.Gray{99})
	p.updateImageTexture(img, gray)
	if spy.updates != 1 || !bytes.Equal(spy.pixels[:4], []byte{99, 99, 99, 255}) {
		t.Fatal("image type change was not converted to RGBA8")
	}
	// Direct helper uploads are normally registered by getTexture.
	cache.SetTexture(img, cache.TextureType(p.imageTextures[img].texture), nil)
	p.updateImageTexture(img, image.NewRGBA(image.Rect(0, 0, 0, 0)))
	if spy.deletes != 1 || len(p.imageTextures) != 0 {
		t.Fatal("empty image retained old storage")
	}
}
