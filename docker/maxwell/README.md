# Experimental GTX 750 Ti / Maxwell deployment

This optional deployment preserves the default Nightingale setup. It uses the
published image digest tested on a GTX 750 Ti (2 GB), NVIDIA driver 470.256.02,
and NVIDIA Container Toolkit. It does not build the current source checkout;
newer images and other cards have not been validated with this policy.

UVR **Karaoke** separation uses PyTorch 2.7.1 + CUDA 11.8, float32 math attention,
segment size 128, batch size 1 and overlap 4. Transcription uses CPU int8 and
alignment uses CPU. CTranslate2's installed CUDA 12 build cannot run this setup.
Smaller separation segments can affect quality near chunk boundaries.

The compatibility module disables ONNX Runtime CUDA DLL preloading (which can
load incompatible CUDA 12 libraries), flash attention, cuDNN and compilation.
It deserializes Roformer on CPU and releases nested separator models after use.
A Demucs memory fallback is included, but select **Karaoke** for UVR.

## Prepare from an existing installation

Finish normal Nightingale dependency setup first. These commands assume its
existing data folder contains `vendor/venv`, `vendor/uv`, `vendor/ffmpeg` and the
analyzer. Use absolute paths for the two variables below. Run commands from this
directory. Do not run two analyzers against the same data folder or GPU at once.

```sh
export NIGHTINGALE_DATA_DIR=/absolute/path/to/nightingale-data
export NIGHTINGALE_MUSIC_DIR=/absolute/path/to/music
mkdir -p vendor
cp -a "$NIGHTINGALE_DATA_DIR/vendor/." vendor/
# The container's nightingale user must be able to write the vendor directory.
# This pinned image uses UID/GID 999; adjust ownership if needed.
docker compose run --rm --no-deps --user root -e NIGHTINGALE_GPU_COMPAT=0 \
  --entrypoint chown nightingale-maxwell -R 999:999 /data/vendor
docker compose run --rm --no-deps -e NIGHTINGALE_GPU_COMPAT=0 \
  --entrypoint /data/vendor/uv nightingale-maxwell \
  pip install --python /data/vendor/venv/bin/python \
  torch==2.7.1 torchaudio==2.7.1 torchvision==0.22.1 \
  --index-url https://download.pytorch.org/whl/cu118
docker compose up -d
```

Open port 64449 (override with `NIGHTINGALE_PORT`) and select **Karaoke** in
separator settings. Settings, database, models and results remain in the existing
data directory. Only the copied Python dependencies are overlaid from `vendor/`.
An `.env` file can persist the path variables; it is excluded from Git.
Do not run the app's dependency updater without rechecking the CUDA pins.

## Validation

On the tested host, a 20-second Chinese music excerpt completed UVR separation,
large-v3 CPU int8 transcription, alignment and transcript saving through the
persistent analyzer protocol. Peak allocated VRAM was 1073 MiB and returned to
8 MiB after cleanup. A 386-second song subsequently completed UVR separation
in approximately 15 minutes. Its remaining CPU stages were still running when
this deployment was documented. These measurements are not speed guarantees.

To check your installation, put a short clip at `test-output/input.wav`, stop
other analysis using this data directory, and run:

```sh
mkdir -p test-output
docker compose run --rm --no-deps \
  -e TEST_AUDIO=/gpu-test/input.wav -e TEST_LANGUAGE=zh \
  -v "$PWD/analyzer_test.py:/analyzer_test.py:ro" \
  -v "$PWD/test-output:/gpu-test" \
  --entrypoint /data/vendor/venv/bin/python nightingale-maxwell \
  /analyzer_test.py --full karaoke
```

Set `TEST_LANGUAGE` to the clip's language, or omit it for automatic detection.
The container user must be able to write `test-output`. Omit `--full` for a
separation-only test. The protocol test does not warm up CUDA before separation,
so it exercises the library loading order used by the application. Logs and
outputs stay local. Music, databases, models and dependencies are never committed.
