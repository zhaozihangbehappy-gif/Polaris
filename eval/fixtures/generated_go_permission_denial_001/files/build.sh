#!/bin/bash
set -e
tmpdir=$(mktemp -d)
trap "rm -rf '$tmpdir'" EXIT
chmod 000 "$tmpdir"
GOBIN="$tmpdir" go install .
