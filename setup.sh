#!/bin/bash

git submodule update --init --recursive --remote --merge
cd CASCExtractor
mkdir build
cd build
cmake ..
make
