#!/usr/bin/env bash
# Construye la capa de dependencias del autorizador (PyJWT + cryptography)
# para Lambda Python 3.12 x86_64, sin necesidad de Docker.
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf layers/deps && mkdir -p layers/deps/python
python3 -m pip install --quiet \
  --platform manylinux2014_x86_64 --implementation cp --python-version 3.12 \
  --only-binary=:all: --target layers/deps/python "PyJWT[crypto]>=2.8,<3"
echo "Capa lista en layers/deps"
