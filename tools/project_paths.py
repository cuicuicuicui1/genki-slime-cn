"""Portable source configuration. ROM is never downloaded or committed."""
import os
from pathlib import Path
SOURCE_PATH=Path(os.environ.get('GENKI_SOURCE_ROM','local-input/source.gba'))
