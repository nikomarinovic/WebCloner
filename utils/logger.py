"""utils/logger.py — coloured console logger"""
import logging, sys

COLOURS = {
    logging.DEBUG:    "\033[90m",
    logging.INFO:     "\033[96m",
    logging.WARNING:  "\033[93m",
    logging.ERROR:    "\033[91m",
}

class _Fmt(logging.Formatter):
    def format(self, r):
        c = COLOURS.get(r.levelno, "")
        return f"{c}[{r.levelname[0]}]\033[0m {super().format(r)}"

def setup_logger(name: str) -> logging.Logger:
    lg = logging.getLogger(name)
    if not lg.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(_Fmt("%(message)s"))
        lg.addHandler(h)
    lg.setLevel(logging.DEBUG)
    lg.propagate = False
    return lg
