def verify(workspace): return {"passed": (workspace / "tools/recovery.txt").read_text() == "attempt1\nattempt2\n"}
