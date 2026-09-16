package gl

import (
	"image"
	"image/draw"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/canvas"
)

// Image uploads always use tightly packed RGBA8. Conversion precedes the storage
// size check, so a change of Go image type does not imply a GPU format change.
type imageTextureState struct {
	texture       Texture
	width, height int
	dirty         bool
}

// Refresh invalidates content without destroying storage. Free retains its
// original destructive meaning for eviction and canvas/context teardown.
// The canvas calls this on the rendering thread while the GL context is current.
func (p *painter) Refresh(obj fyne.CanvasObject) {
	if img, ok := obj.(*canvas.Image); ok {
		if state := p.imageTextures[img]; state != nil {
			state.dirty = true
			return
		}
	}
	p.Free(obj)
}

func (p *painter) updateImageTexture(img *canvas.Image, pixels image.Image) Texture {
	bounds := pixels.Bounds()
	width, height := bounds.Dx(), bounds.Dy()
	if width <= 0 || height <= 0 {
		p.freeTexture(img)
		return noTexture
	}
	rgba, ok := pixels.(*image.RGBA)
	if !ok || rgba.Stride != width*4 {
		rgba = image.NewRGBA(image.Rect(0, 0, width, height))
		draw.Draw(rgba, rgba.Bounds(), pixels, bounds.Min, draw.Src)
	}
	if p.imageTextures == nil {
		p.imageTextures = make(map[*canvas.Image]*imageTextureState)
	}
	state := p.imageTextures[img]
	if state == nil {
		state = &imageTextureState{texture: p.newTexture(img.ScaleMode)}
		p.imageTextures[img] = state
	}
	p.ctx.ActiveTexture(texture0)
	p.ctx.BindTexture(texture2D, state.texture)
	filter := img.ScaleMode
	if int(filter) >= len(textureFilterToGL) {
		filter = canvas.ImageScaleSmooth
	}
	p.ctx.TexParameteri(texture2D, textureMinFilter, textureFilterToGL[filter])
	p.ctx.TexParameteri(texture2D, textureMagFilter, textureFilterToGL[filter])
	if state.width != width || state.height != height {
		p.ctx.TexImage2D(texture2D, 0, width, height, colorFormatRGBA, unsignedByte, rgba.Pix[:width*height*4])
	} else {
		p.ctx.TexSubImage2D(texture2D, 0, 0, 0, width, height, colorFormatRGBA, unsignedByte, rgba.Pix[:width*height*4])
	}
	p.logError()
	state.width, state.height, state.dirty = width, height, false
	return state.texture
}
