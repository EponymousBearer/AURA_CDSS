"""
Root package initialization for app module.
"""

from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).parent.parent
MODEL_DIR = BASE_DIR / "model"

__all__ = ['BASE_DIR', 'MODEL_DIR']
