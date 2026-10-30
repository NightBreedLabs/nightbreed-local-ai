# Contributing

NightBreedLabs Local AI Toolkit is a local-first, standard-library-only Linux utility.

1. Open an issue explaining a bug or proposed improvement before undertaking major changes.
2. Keep the default Ollama API restricted to loopback. Do not introduce hidden telemetry, automatic model pulls, or changes to the user's Ollama installation.
3. Do not commit personal Antigravity profiles, model files, secrets, API tokens, or generated indexes.
4. Run `python3 -m unittest discover -s tests -v` and `bash -n install.sh uninstall.sh scripts/publish-to-github.sh` before opening a pull request.
5. Describe Linux distributions tested and whether you used a real or mocked Ollama server.

By contributing, you agree that your contributions are licensed under the repository's MIT License.
