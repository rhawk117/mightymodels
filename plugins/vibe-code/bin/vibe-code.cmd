@echo off
uv tool run --python ">=3.12" --with msgspec==0.22.0 --with pyyaml==6.0.3 python "%~dp0vibe-code" %*
