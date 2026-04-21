#!/bin/bash
javac Main.java
# Patch class version to trigger UnsupportedClassVersionError
printf '\x00\x99' | dd of=Main.class bs=1 seek=6 count=2 conv=notrunc
