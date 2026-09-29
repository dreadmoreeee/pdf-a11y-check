import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# the tool folder (so pdf_a11y_check imports without pip install) and this folder (test helpers)
for p in (HERE.parent, HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
