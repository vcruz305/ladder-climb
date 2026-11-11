"""Allow python -m ladder_climb without installing console scripts."""
from .cli import main

raise SystemExit(main())
