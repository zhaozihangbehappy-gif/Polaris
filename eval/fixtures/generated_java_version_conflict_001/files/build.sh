#!/bin/bash
mkdir -p classes
javac -source 11 -target 8 -d classes HelloWorld.java
java -cp classes HelloWorld
