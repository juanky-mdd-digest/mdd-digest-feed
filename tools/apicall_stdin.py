#!/usr/bin/env python3
# Runs apicall in-process with argv read from stdin JSON (avoids OS arg-length limits).
import json, sys, runpy
sys.argv = ["apicall"] + json.load(sys.stdin)
runpy.run_path("/usr/local/bin/apicall", run_name="__main__")
