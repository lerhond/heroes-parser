#!/bin/bash

git submodule update --init --recursive
cd CASCExtractor
mkdir build
cd build
cmake ..
make
