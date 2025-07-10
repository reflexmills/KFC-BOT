#!/bin/bash
# Указываем Cargo использовать /tmp вместо /usr/local/cargo
export CARGO_HOME=/tmp/cargo
mkdir -p $CARGO_HOME

# Устанавливаем зависимости Python (если maturin или другие Rust-зависимости)
pip install --no-build-isolation .
