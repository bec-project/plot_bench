//go:build linux && !wayland

package main

// Doctor rejects unverified X11/automatic builds for native Wayland campaigns.
const displayProtocol = "unverified"
