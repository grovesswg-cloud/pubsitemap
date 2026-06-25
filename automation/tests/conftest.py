"""Pytest configuration — adds automation/ to sys.path so provider imports resolve."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
