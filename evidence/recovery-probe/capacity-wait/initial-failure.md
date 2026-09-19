Capacity wait probe stopped before service launch with OSError errno48 at
runtime/service.py socket.bind on port7339. No model/provider call occurred.
lsof found no listener; preceding server cleanup was true. port-diagnosis.json
records plain bind refused while SO_REUSEADDR bind succeeded; other ports were
free. This is stopped-service TCP TIME_WAIT, not a running competing service.
Correction uses ordinary SO_REUSEADDR preflight, never SO_REUSEPORT, and tests
that active listeners remain blocked. Revised fixture output uses a new v2 path;
first evidence is retained. No blind retry of unchanged prerequisites.
