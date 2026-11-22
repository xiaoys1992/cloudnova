"""Put the repo root on sys.path so `import src.agent...` works under pytest."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
