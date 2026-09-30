"""The pinned Codex CLI (D047): one place for its version, host path and sha256.

Every launch of Codex reads its path here - the startup chain (scripts/probe_bridge.worker_command, and through it the
exec and app-server routes), the sandbox commands and the web profiles - and so do the activator's check that the
workplace measured this very program (scripts/model_choice.measured) and the issuer's read table. The version's own
directory also holds the code-mode host it may start, so two versions never share one. A new pin measures again into
its own evidence directory with scripts/measure_codex_shapes.py; the previous version's copy stays as the previous
release's way back. A new path changes the AP-10 command, which the automatic look always leaves to the owner.
"""
VERSION = '0.159.2'
BINARY = '.runtime/bin/codex-0.159.2/codex'
SHA256 = '16593cc2f422d5f398a8e40f550ebbaf1245392528957be342c295920a300704'
EVIDENCE = 'evidence/codex-' + VERSION
