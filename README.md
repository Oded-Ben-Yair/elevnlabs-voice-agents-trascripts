# ElevenLabs Voice Isolation & Arabic Transcription Pipeline

This project provides a local, end-to-end workflow for cleaning noisy audio with the
[ElevenLabs Audio Isolation API](https://elevenlabs.io/) and generating Arabic
speech-to-text transcripts as Word documents. The pipeline is designed for local
execution—no Azure resources are required.

## Repository structure

```
.
├── requirements.txt        # Python dependencies
├── src/
│   └── pipeline.py         # CLI entry-point orchestrating isolation & transcription
└── *.mp3                   # Example input files (replace with your recordings)
```

Running the pipeline produces an `outputs/` directory containing:

- `isolated_audio/`: cleaned audio returned by ElevenLabs (`*_isolated.wav`).
- `transcripts/`: plain-text transcripts.
- `word_docs/`: `.docx` files with timestamped segments and metadata.

## Prerequisites

- Python 3.10 or later.
- An ElevenLabs API key with access to the Audio Isolation feature.
- `ffmpeg` installed on your system (required by Whisper/faster-whisper to decode audio).
  - Debian/Ubuntu: `sudo apt-get install ffmpeg`
  - macOS (Homebrew): `brew install ffmpeg`

The speech-to-text step uses the open-source [faster-whisper](https://github.com/guillaumekln/faster-whisper)
library, so no additional cloud credentials are required.

## Setup

1. **Create and activate a virtual environment (recommended).**

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   .venv\\Scripts\\activate   # Windows PowerShell
   ```

2. **Install Python dependencies.**

   ```bash
   pip install -r requirements.txt
   ```

3. **Provide your ElevenLabs API key.**

   ```bash
   export ELEVENLABS_API_KEY="your-key-here"  # Linux/macOS
   setx ELEVENLABS_API_KEY "your-key-here"    # Windows (new shell required)
   ```

4. **Place your audio files in a folder.**
   By default the pipeline scans the current directory, but you can point it to any
   folder containing `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, or `.webm` files.

## Running the pipeline

Execute the CLI with Python's module syntax:

```bash
python -m src.pipeline --input-dir ./ --output-dir ./outputs
```

The first run downloads the selected Whisper model (default: `small`) from Hugging Face;
this can take several minutes depending on the model size. Subsequent runs use the
cached model.

### Useful CLI options

- `--model-size`: Whisper model variant (`tiny`, `base`, `small`, `medium`, `large-v2`, ...).
- `--device`: set to `cuda` if a GPU is available; defaults to CPU.
- `--compute-type`: quantization for Whisper inference (`int8`, `int8_float16`, `float16`, `float32`).
- `--language`: override the transcription language (default: `ar` for Arabic).
- `--model-dir`: choose a custom cache directory for Whisper models.
- `--no-skip-existing`: re-run the isolation step even if an isolated file already exists.
- `--verbose`: enable debug logging for troubleshooting.

Run `python -m src.pipeline --help` to see the full list of options.

## Output

For each input file the pipeline will:

1. Upload the audio to ElevenLabs and download the cleaned version as `*_isolated.wav`.
2. Transcribe the isolated audio locally in Arabic using faster-whisper.
3. Save a plain-text transcript and a `.docx` document with timestamped segments,
   detected language, and audio duration metadata.

If any step fails the script logs an error message and moves on to the next file.

## Troubleshooting

- **Missing API key:** ensure `ELEVENLABS_API_KEY` is exported in your shell before running the script.
- **ffmpeg not found:** install `ffmpeg` and verify it is on your `PATH`.
- **Model download takes too long:** choose a smaller Whisper model (e.g., `--model-size tiny`).
- **CUDA errors:** if you do not have a GPU, stick to the default `--device cpu` and `--compute-type int8`.

## Next steps

- Extend the pipeline with batching, retries, or resumable downloads if you process large volumes.
- Customize the Word report (branding, formatting) by editing `TranscriptWriter` in `src/pipeline.py`.
