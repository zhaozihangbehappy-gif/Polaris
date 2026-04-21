#!/bin/bash
set -e
mkdir -p bin lib
javac -d lib src/Helper.java
javac -cp lib -d bin src/Main.java
java -cp bin Main
