"""Print the JetBot's IP on the laptop's current network (see sentry/net/discover.py).

    python -m tools.find_jetbot
"""
from sentry.net.discover import find, resolve  # noqa: F401  (resolve is re-exported for the tools)

if __name__ == "__main__":
    print(resolve("auto"))
