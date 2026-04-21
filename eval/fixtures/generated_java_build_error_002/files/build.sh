#!/bin/bash
set -e
mkdir -p bin
javac -d bin -source 8 -target 8 src/Main.java
